//! ADR-0024 D4, CLI half: what a `vz` run applies in the guest, resolved
//! BEFORE any VM boots, for the foreground (memo) and detached paths alike.
//!
//! Docker precedence, as on the `ns` engine path (`paths::run_engine`):
//! - argv: `--entrypoint` (which also drops the image CMD), else image
//!   ENTRYPOINT + (CLI command, else image CMD);
//! - env: image `ENV` < `-e`/`--env-file` (the engine prepends `GUEST_PATH`);
//! - user: `-u` > image `USER`; workdir: `-w` > image `WORKDIR`.
//!
//! The image config and `/etc/passwd`/`/etc/group` are read straight from the
//! ref's manifest (no hydration), so the memo key is computed before a HIT
//! and an unresolvable `-u` fails before any VM or supervisor exists. The
//! engine resolves the user again against the hydrated rootfs it boots.

use lightr_core::{Entry, LightrError, Manifest, Result};
use lightr_store::Store;

/// The effective guest-facing inputs of one vz run.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) struct VzGuestRun {
    pub argv: Vec<String>,
    /// Image `ENV` < CLI `-e`, without `GUEST_PATH`/`HOME` (engine adds them).
    pub env: Vec<(String, String)>,
    pub user: Option<String>,
    pub workdir: Option<String>,
}

/// Resolve `ref_name`'s image config against the CLI inputs, and check the
/// user resolves inside the image. Errors are usage-class (exit 2).
pub(super) fn resolve_vz_guest(
    store: &Store,
    ref_name: &str,
    command: &[String],
    entrypoint: Option<&[String]>,
    env_explicit: &[(String, String)],
    user: Option<&str>,
    workdir: Option<&str>,
) -> Result<VzGuestRun> {
    let manifest = ref_manifest(store, ref_name)?;
    let cfg = image_config(store, ref_name, &manifest)?;
    let argv = match entrypoint {
        Some(ep) => ep.iter().chain(command).cloned().collect(),
        None => lightr_build::effective_argv(&cfg, command),
    };
    let run = VzGuestRun {
        argv,
        env: super::paths::merge_image_env(&cfg.env, env_explicit),
        user: user.map(String::from).or(cfg.user),
        workdir: workdir.map(String::from).or(cfg.workdir),
    };
    if let Some(user) = &run.user {
        lightr_engine::engine::vzguest::resolve_guest_user(
            user,
            image_text(store, &manifest, "etc/passwd")?.as_deref(),
            image_text(store, &manifest, "etc/group")?.as_deref(),
        )?;
    }
    Ok(run)
}

/// `-v HOST:GUEST[:ro]` host binds as engine mounts (the guest mounts them as
/// virtiofs volumes; named volumes are refused by `policy_vz`).
pub(super) fn host_volumes(runflags: &super::RunFlags) -> Vec<lightr_engine::ResolvedMount> {
    runflags
        .volumes
        .iter()
        .map(|v| lightr_engine::ResolvedMount {
            kind: lightr_engine::MountKind::HostBind,
            source: Some(v.source.clone()),
            target: v.target.clone(),
            readonly: v.readonly,
        })
        .collect()
}

fn ref_manifest(store: &Store, ref_name: &str) -> Result<Manifest> {
    let rec = store
        .ref_get(ref_name)?
        .ok_or_else(|| LightrError::RefNotFound(ref_name.to_string()))?;
    Manifest::decode(&store.get_bytes(&rec.root)?)
}

/// The `lightr build` sidecar wins (Lightr image semantics); else the OCI
/// config retained at import; else none. A malformed config fails closed.
fn image_config(
    store: &Store,
    ref_name: &str,
    manifest: &Manifest,
) -> Result<lightr_build::ImageConfig> {
    if let Some(bytes) = image_file(store, manifest, super::paths::IMAGE_CONFIG_FILE)? {
        return serde_json::from_slice(&bytes).map_err(|e| {
            LightrError::InvalidManifest(format!("{ref_name}: image config sidecar: {e}"))
        });
    }
    match store.image_config_get(ref_name)? {
        Some(bytes) => super::paths::image_config_from_oci(&bytes),
        None => Ok(lightr_build::ImageConfig::default()),
    }
}

/// A regular file of the image by its root-relative path. A symlink is
/// refused (it could point outside the image once hydrated).
fn image_file(store: &Store, manifest: &Manifest, path: &str) -> Result<Option<Vec<u8>>> {
    match manifest.entries.iter().find(|e| e.path() == path) {
        None | Some(Entry::Dir { .. }) => Ok(None),
        Some(Entry::File { digest, .. }) => store.get_bytes(digest).map(Some),
        Some(Entry::Symlink { .. }) => Err(LightrError::InvalidRef(format!(
            "vz: the image's /{path} is a symlink; refusing to resolve it"
        ))),
    }
}

fn image_text(store: &Store, manifest: &Manifest, path: &str) -> Result<Option<String>> {
    image_file(store, manifest, path)?
        .map(|bytes| {
            String::from_utf8(bytes)
                .map_err(|_| LightrError::InvalidRef(format!("vz: /{path} is not UTF-8")))
        })
        .transpose()
}

#[cfg(test)]
#[path = "vz_guest_tests.rs"]
mod tests;
