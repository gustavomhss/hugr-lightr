//! Platform-neutral layer operations. Backends own confinement mechanics.

use lightr_core::{LightrError, Result};
use std::{
    collections::HashSet,
    ffi::OsString,
    io::Read,
    path::{Component, Path},
    time::Instant,
};

pub(super) type LayerPath = Vec<OsString>;

pub(super) enum LayerOp {
    Directory(LayerPath),
    Whiteout {
        parent: LayerPath,
        name: Option<OsString>,
    },
    Regular {
        dest: LayerPath,
        data: Vec<u8>,
        mode: u32,
    },
    Symlink {
        dest: LayerPath,
        target: OsString,
    },
    Hardlink {
        dest: LayerPath,
        target: LayerPath,
    },
}

/// Platform boundary. Implementations must never re-resolve an untrusted
/// descendant by staging-root pathname after checking it.
pub(super) trait LayerFs {
    fn apply(&mut self, op: &LayerOp) -> Result<()>;
}

fn layer_path(path: &Path) -> Result<LayerPath> {
    let components: LayerPath = path
        .components()
        .filter_map(|component| match component {
            Component::CurDir => None,
            Component::Normal(name) => Some(Ok(name.to_os_string())),
            _ => Some(Err(LightrError::InvalidManifest(format!(
                "unsafe layer path: {}",
                path.display()
            )))),
        })
        .collect::<Result<_>>()?;
    if components.is_empty() {
        return Err(LightrError::InvalidManifest("empty layer path".into()));
    }
    Ok(components)
}

pub(super) fn collect_ops<R: Read>(
    archive: &mut tar::Archive<R>,
    deadline: Instant,
    entry_count: &mut u64,
    timeout_secs: u64,
) -> Result<(Vec<LayerOp>, HashSet<LayerPath>)> {
    let mut ops = Vec::new();
    let mut whited_out = HashSet::new();
    for entry_result in archive.entries().map_err(LightrError::Io)? {
        *entry_count += 1;
        if *entry_count & 0xFF == 0 && Instant::now() >= deadline {
            return Err(LightrError::InvalidManifest(format!(
                "layer extraction timed out after {timeout_secs} s (LIGHTR_LAYER_TIMEOUT_SECS)"
            )));
        }
        let mut entry = entry_result.map_err(LightrError::Io)?;
        let path = layer_path(&entry.path().map_err(LightrError::Io)?)?;
        let name = path.last().expect("non-empty checked path").clone();
        let parent = path[..path.len() - 1].to_vec();
        let is_whiteout = name
            .to_string_lossy()
            .strip_prefix(".wh.")
            .map(OsString::from);
        if let Some(name) = is_whiteout {
            let opaque = name == ".wh..opq";
            if !opaque {
                let mut target = parent.clone();
                target.push(name.clone());
                whited_out.insert(target);
            }
            ops.push(LayerOp::Whiteout {
                parent,
                name: (!opaque).then_some(name),
            });
            continue;
        }
        use tar::EntryType;
        match entry.header().entry_type() {
            EntryType::Directory => ops.push(LayerOp::Directory(path)),
            EntryType::Regular | EntryType::Continuous => {
                let mode = entry.header().mode().map_err(LightrError::Io)?;
                let mut data = Vec::new();
                entry.read_to_end(&mut data).map_err(LightrError::Io)?;
                ops.push(LayerOp::Regular {
                    dest: path,
                    data,
                    mode,
                });
            }
            EntryType::Symlink => {
                // OCI permits absolute and dangling link text. It is data, not a host path.
                let target = entry
                    .header()
                    .link_name()
                    .map_err(LightrError::Io)?
                    .map(|p| p.into_owned().into_os_string())
                    .unwrap_or_default();
                ops.push(LayerOp::Symlink { dest: path, target });
            }
            EntryType::Link => {
                let target = entry
                    .header()
                    .link_name()
                    .map_err(LightrError::Io)?
                    .map(|p| p.into_owned())
                    .ok_or_else(|| {
                        LightrError::InvalidManifest("hardlink target missing".into())
                    })?;
                ops.push(LayerOp::Hardlink {
                    dest: path,
                    target: layer_path(&target)?,
                });
            }
            _ => {
                return Err(LightrError::Unsupported(format!(
                    "unsupported OCI layer entry type: {:?}",
                    entry.header().entry_type()
                )))
            }
        }
    }
    Ok((ops, whited_out))
}

pub(super) fn apply_ops(
    fs: &mut dyn LayerFs,
    ops: &[LayerOp],
    whited_out: &HashSet<LayerPath>,
) -> Result<()> {
    for op in ops.iter().filter(|op| matches!(op, LayerOp::Directory(_))) {
        fs.apply(op)?;
    }
    for op in ops
        .iter()
        .filter(|op| matches!(op, LayerOp::Whiteout { .. }))
    {
        fs.apply(op)?;
    }
    for op in ops
        .iter()
        .filter(|op| matches!(op, LayerOp::Regular { .. } | LayerOp::Symlink { .. }))
    {
        let dest = match op {
            LayerOp::Regular { dest, .. } | LayerOp::Symlink { dest, .. } => dest,
            _ => unreachable!(),
        };
        if !whited_out.contains(dest) {
            fs.apply(op)?;
        }
    }
    for op in ops
        .iter()
        .filter(|op| matches!(op, LayerOp::Hardlink { .. }))
    {
        let dest = match op {
            LayerOp::Hardlink { dest, .. } => dest,
            _ => unreachable!(),
        };
        if !whited_out.contains(dest) {
            fs.apply(op)?;
        }
    }
    Ok(())
}
