//! ADR-0024 D4, host half: turn an [`ExecSpec`] into the guest [`InitSpec`]
//! the vz engine writes to `CMD_FILE`, before any VM boots.
//!
//! Host-portable (no cfg gate) so the CLI can key the vz memo on exactly what
//! the guest applies, and so every rule is unit-tested on any host:
//!
//! - **env** ([`guest_env`]): `GUEST_PATH` first, then the caller's pairs
//!   (image `ENV`, then `-e`, already merged); a later key replaces an earlier
//!   one in place. `HOME` defaults to the user's passwd home (Docker), else `/`.
//! - **user** ([`resolve_guest_user`]): `uid|name[:gid|group]` resolved
//!   against the IMAGE's `/etc/passwd` and `/etc/group` (never the host's). A
//!   name that does not resolve fails before boot. Supplementary groups come
//!   from `/etc/group` only when no group is given (runc's rule).
//! - **workdir**: `ExecSpec.workdir`, else `/`.
//! - **volumes**: host-bind directories only (VZ shares directories), tags
//!   `vol0..N`; anything else fails before boot.

use std::path::{Component, Path, PathBuf};

use lightr_core::{LightrError, Result};
use lightr_init::{GuestUser, GuestVolume, InitSpec, GUEST_PATH};

use super::spec::{ExecSpec, MountKind};

/// One extra virtiofs share for the shim: `host` dir under `tag`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct VzVolumeShare {
    pub host: PathBuf,
    pub tag: String,
    pub readonly: bool,
}

/// A resolved `-u`: the numeric identity plus the passwd home (for `HOME`).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ResolvedUser {
    pub user: GuestUser,
    pub home: String,
}

/// The guest env before `HOME`: `PATH=GUEST_PATH`, then `env` in order, a
/// later key overriding an earlier one in place. The vz memo key hashes this.
pub fn guest_env(env: &[(String, String)]) -> Vec<(String, String)> {
    let mut out = vec![("PATH".to_string(), GUEST_PATH.to_string())];
    for (key, value) in env {
        match out.iter_mut().find(|(k, _)| k == key) {
            Some(slot) => slot.1 = value.clone(),
            None => out.push((key.clone(), value.clone())),
        }
    }
    out
}

/// The `init_abi` a spec needs: 2 when it carries a field an ABI-1 init would
/// silently ignore (`user`, `volumes`, `shm_size`), else 1. ABI 1 already
/// applied `env` and `cwd`.
pub fn required_init_abi(spec: &InitSpec) -> u32 {
    if spec.user.is_some() || !spec.volumes.is_empty() || spec.shm_size.is_some() {
        lightr_init::INIT_ABI
    } else {
        1
    }
}

/// Build the guest spec and the volume shares for a vz boot of `rootfs` (the
/// hydrated host dir). Every refusal happens here, before the VM exists.
pub fn build_init_spec(spec: &ExecSpec, rootfs: &Path) -> Result<(InitSpec, Vec<VzVolumeShare>)> {
    let passwd = read_image_db(rootfs, "passwd")?;
    let user = spec
        .user
        .map(|u| {
            resolve_guest_user(
                u,
                passwd.as_deref(),
                read_image_db(rootfs, "group")?.as_deref(),
            )
        })
        .transpose()?;
    let home = match &user {
        Some(resolved) => resolved.home.clone(),
        None => passwd_home(passwd.as_deref(), 0),
    };
    let mut env = guest_env(spec.env);
    if !env.iter().any(|(k, _)| k == "HOME") {
        env.push(("HOME".to_string(), home));
    }
    let cwd = match spec.workdir {
        Some(dir) if dir.starts_with('/') => dir.to_string(),
        Some(dir) => {
            return Err(LightrError::InvalidRef(format!(
                "vz: working directory {dir:?} must be an absolute guest path"
            )))
        }
        None => "/".to_string(),
    };
    let shares = volume_shares(spec)?;
    let init = InitSpec {
        command: spec.command.to_vec(),
        cwd,
        env,
        net: spec.net,
        suspend_gate: false,
        user: user.map(|r| r.user),
        volumes: shares
            .iter()
            .zip(spec.mounts)
            .map(|(share, m)| GuestVolume {
                tag: share.tag.clone(),
                target: m.target.clone(),
                readonly: share.readonly,
            })
            .collect(),
        shm_size: spec.shm_size,
    };
    Ok((init, shares))
}

/// Resolve `-u` against the image's passwd/group text (`None` = file absent).
pub fn resolve_guest_user(
    spec: &str,
    passwd: Option<&str>,
    group: Option<&str>,
) -> Result<ResolvedUser> {
    let (user_part, group_part) = match spec.split_once(':') {
        Some((u, g)) => (u, Some(g)),
        None => (spec, None),
    };
    if user_part.is_empty() || group_part == Some("") {
        return Err(LightrError::InvalidRef(format!(
            "-u {spec:?}: expected uid|name[:gid|group]"
        )));
    }
    let users = passwd_rows(passwd);
    let entry = match user_part.parse::<u32>() {
        // A numeric uid need not exist in the image (Docker): gid 0, home `/`.
        Ok(uid) => users
            .iter()
            .find(|r| r.uid == uid)
            .cloned()
            .unwrap_or(PasswdRow {
                name: String::new(),
                uid,
                gid: 0,
                home: String::new(),
            }),
        Err(_) => users
            .iter()
            .find(|r| r.name == user_part)
            .cloned()
            .ok_or_else(|| {
                LightrError::InvalidRef(format!(
                    "-u {spec:?}: no user {user_part:?} in the image's /etc/passwd"
                ))
            })?,
    };
    let groups_db = group_rows(group);
    let gid = match group_part {
        None => entry.gid,
        Some(g) => match g.parse::<u32>() {
            Ok(gid) => gid,
            Err(_) => groups_db
                .iter()
                .find(|r| r.name == g)
                .map(|r| r.gid)
                .ok_or_else(|| {
                    LightrError::InvalidRef(format!(
                        "-u {spec:?}: no group {g:?} in the image's /etc/group"
                    ))
                })?,
        },
    };
    let mut groups = vec![gid];
    if group_part.is_none() && !entry.name.is_empty() {
        for row in groups_db.iter().filter(|r| r.members.contains(&entry.name)) {
            if !groups.contains(&row.gid) {
                groups.push(row.gid);
            }
        }
    }
    Ok(ResolvedUser {
        user: GuestUser {
            uid: entry.uid,
            gid,
            groups,
        },
        home: home_or_root(entry.home),
    })
}

/// `HOME` for `uid` from passwd text, else `/` (Docker's fallback).
fn passwd_home(passwd: Option<&str>, uid: u32) -> String {
    home_or_root(
        passwd_rows(passwd)
            .into_iter()
            .find(|r| r.uid == uid)
            .map(|r| r.home)
            .unwrap_or_default(),
    )
}

fn home_or_root(home: String) -> String {
    if home.is_empty() {
        "/".to_string()
    } else {
        home
    }
}

/// `name:x:uid:gid:gecos:home:shell`; malformed rows are skipped.
#[derive(Clone)]
struct PasswdRow {
    name: String,
    uid: u32,
    gid: u32,
    home: String,
}

/// `name:x:gid:member,member`; malformed rows are skipped.
struct GroupRow {
    name: String,
    gid: u32,
    members: Vec<String>,
}

fn columns(text: Option<&str>) -> impl Iterator<Item = Vec<&str>> {
    text.unwrap_or("")
        .lines()
        .filter(|l| !l.trim_start().starts_with('#'))
        .map(|l| l.split(':').collect())
}

fn passwd_rows(text: Option<&str>) -> Vec<PasswdRow> {
    columns(text)
        .filter_map(|c| {
            Some(PasswdRow {
                name: c[0].to_string(),
                uid: c.get(2)?.parse().ok()?,
                gid: c.get(3)?.parse().ok()?,
                home: c.get(5).map(|h| h.to_string()).unwrap_or_default(),
            })
        })
        .collect()
}

fn group_rows(text: Option<&str>) -> Vec<GroupRow> {
    columns(text)
        .filter_map(|c| {
            Some(GroupRow {
                name: c[0].to_string(),
                gid: c.get(2)?.parse().ok()?,
                members: c
                    .get(3)
                    .map(|m| {
                        m.split(',')
                            .filter(|s| !s.is_empty())
                            .map(String::from)
                            .collect()
                    })
                    .unwrap_or_default(),
            })
        })
        .collect()
}

/// Read `<rootfs>/etc/<name>` without following a symlink out of the image.
/// `Ok(None)` when absent.
pub fn read_image_db(rootfs: &Path, name: &str) -> Result<Option<String>> {
    for path in [rootfs.join("etc"), rootfs.join("etc").join(name)] {
        match std::fs::symlink_metadata(&path) {
            Ok(meta) if meta.file_type().is_symlink() => {
                return Err(LightrError::InvalidRef(format!(
                    "vz -u: {} is a symlink; refusing to resolve users outside the image",
                    path.display()
                )))
            }
            Ok(_) => {}
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(e) => return Err(LightrError::Io(e)),
        }
    }
    std::fs::read_to_string(rootfs.join("etc").join(name))
        .map(Some)
        .map_err(LightrError::Io)
}

fn volume_shares(spec: &ExecSpec) -> Result<Vec<VzVolumeShare>> {
    spec.mounts
        .iter()
        .enumerate()
        .map(|(i, m)| {
            let source = match (m.kind, m.source.as_deref()) {
                (MountKind::HostBind, Some(source)) => source,
                _ => {
                    return Err(LightrError::Unsupported(format!(
                        "vz -v {}: only host directory binds are shared into the guest",
                        m.target
                    )))
                }
            };
            let target = Path::new(&m.target);
            if !target.is_absolute()
                || target.parent().is_none()
                || target.components().any(|c| c == Component::ParentDir)
            {
                return Err(LightrError::InvalidRef(format!(
                    "vz -v {source}:{}: the guest target must be an absolute path below /",
                    m.target
                )));
            }
            let host = std::fs::canonicalize(source).map_err(|e| {
                LightrError::InvalidRef(format!("vz -v {source}: host source unavailable: {e}"))
            })?;
            if !host.is_dir() {
                return Err(LightrError::InvalidRef(format!(
                    "vz -v {source}: not a directory (vz shares directories only)"
                )));
            }
            Ok(VzVolumeShare {
                host,
                tag: format!("vol{i}"),
                readonly: m.readonly,
            })
        })
        .collect()
}

#[cfg(test)]
#[path = "vzguest_tests.rs"]
mod tests;
