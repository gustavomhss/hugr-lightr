//! Descriptor-confined Unix implementation of [`super::apply::LayerFs`].

use super::apply::{LayerFs, LayerOp};
use lightr_core::{Digest, Entry, LightrError, Manifest, Result};
use lightr_index::SnapshotSource;
use rustix::fs::{self, AtFlags, Dir, FileType, Mode, OFlags};
use std::{
    collections::BTreeMap,
    ffi::OsString,
    fs::File,
    io::{Read, Write},
    os::unix::{
        ffi::{OsStrExt, OsStringExt},
        fs::FileExt,
    },
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc,
    },
};

#[cfg(test)]
use std::path::PathBuf;

static NEXT: AtomicU64 = AtomicU64::new(0);

fn invalid(error: rustix::io::Errno) -> LightrError {
    LightrError::InvalidManifest(format!("confined layer apply failed: {error}"))
}
fn identity(stat: rustix::fs::Stat) -> (u64, u64) {
    #[allow(clippy::unnecessary_cast)]
    (stat.st_dev as u64, stat.st_ino)
}
fn open_dir(parent: &File, component: &std::ffi::OsStr) -> Result<File> {
    let fd = fs::openat(
        parent,
        component,
        OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )
    .map_err(invalid)?;
    Ok(File::from(fd))
}
fn mkdir_open(parent: &File, component: &std::ffi::OsStr) -> Result<File> {
    match fs::mkdirat(parent, component, Mode::from_raw_mode(0o755)) {
        Ok(()) => (),
        Err(rustix::io::Errno::EXIST) => (),
        Err(error) => return Err(invalid(error)),
    }
    open_dir(parent, component)
}
fn ensure(root: &File, path: &[OsString]) -> Result<File> {
    let mut dir = root.try_clone().map_err(LightrError::Io)?;
    for part in path {
        dir = mkdir_open(&dir, part)?;
    }
    Ok(dir)
}
fn existing(root: &File, path: &[OsString]) -> Result<File> {
    let mut dir = root.try_clone().map_err(LightrError::Io)?;
    for part in path {
        dir = open_dir(&dir, part)?;
    }
    Ok(dir)
}
fn open_regular(parent: &File, component: &std::ffi::OsStr) -> Result<File> {
    let fd = fs::openat(
        parent,
        component,
        OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )
    .map_err(invalid)?;
    let file = File::from(fd);
    if FileType::from_raw_mode(fs::fstat(&file).map_err(invalid)?.st_mode) != FileType::RegularFile
    {
        return Err(LightrError::InvalidManifest(
            "confined layer source is not regular".into(),
        ));
    }
    Ok(file)
}
fn unlink_one(parent: &File, component: &std::ffi::OsStr) -> Result<()> {
    let stat = match fs::statat(parent, component, AtFlags::SYMLINK_NOFOLLOW) {
        Ok(stat) => stat,
        Err(rustix::io::Errno::NOENT) => return Ok(()),
        Err(error) => return Err(invalid(error)),
    };
    let directory = FileType::from_raw_mode(stat.st_mode) == FileType::Directory;
    if directory {
        let child = open_dir(parent, component)?;
        clear(&child)?;
    }
    fs::unlinkat(
        parent,
        component,
        if directory {
            AtFlags::REMOVEDIR
        } else {
            AtFlags::empty()
        },
    )
    .map_err(invalid)
}
fn clear(dir: &File) -> Result<()> {
    let entries = Dir::read_from(dir).map_err(invalid)?;
    for entry in entries {
        let entry = entry.map_err(invalid)?;
        let name = entry.file_name();
        if name.to_bytes() != b"." && name.to_bytes() != b".." {
            unlink_one(dir, std::ffi::OsStr::from_bytes(name.to_bytes()))?;
        }
    }
    Ok(())
}

pub(super) struct UnixLayerFs {
    root: File,
    #[cfg(test)]
    path: PathBuf,
    parent: File,
    stage_name: OsString,
    identity: (u64, u64),
}

/// Reader over a pinned descriptor. `read_at` leaves descriptor offset untouched,
/// so every SnapshotSource open has an independent position.
struct PositionalReader {
    file: Arc<File>,
    offset: u64,
}
impl Read for PositionalReader {
    fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
        let read = self.file.read_at(buf, self.offset)?;
        self.offset += read as u64;
        Ok(read)
    }
}

pub(super) struct UnixSnapshotSource {
    files: BTreeMap<String, Arc<File>>,
}
impl SnapshotSource for UnixSnapshotSource {
    fn open(&self, relative: &str) -> Result<Box<dyn Read>> {
        let file = self.files.get(relative).ok_or_else(|| {
            LightrError::InvalidManifest(format!("captured OCI file missing: {relative}"))
        })?;
        Ok(Box::new(PositionalReader {
            file: Arc::clone(file),
            offset: 0,
        }))
    }
}

fn name_string(name: &std::ffi::OsStr) -> Result<&str> {
    name.to_str()
        .ok_or_else(|| LightrError::InvalidManifest("OCI layer path is not valid UTF-8".into()))
}
fn capture_dir(
    dir: &File,
    prefix: &str,
    entries: &mut Vec<Entry>,
    files: &mut BTreeMap<String, Arc<File>>,
) -> Result<()> {
    let mut names = Vec::new();
    for entry in Dir::read_from(dir).map_err(invalid)? {
        let entry = entry.map_err(invalid)?;
        let name = entry.file_name();
        if name.to_bytes() != b"." && name.to_bytes() != b".." {
            names.push(OsString::from_vec(name.to_bytes().to_vec()));
        }
    }
    names.sort();
    let empty = names.is_empty();
    for name in names {
        let path = if prefix.is_empty() {
            name_string(&name)?.to_owned()
        } else {
            format!("{prefix}/{}", name_string(&name)?)
        };
        let stat = fs::statat(dir, &name, AtFlags::SYMLINK_NOFOLLOW).map_err(invalid)?;
        match FileType::from_raw_mode(stat.st_mode) {
            FileType::Directory => {
                let child = open_dir(dir, &name)?;
                capture_dir(&child, &path, entries, files)?;
            }
            FileType::RegularFile => {
                let file = Arc::new(open_regular(dir, &name)?);
                let pinned = fs::fstat(&*file).map_err(invalid)?;
                let size = u64::try_from(pinned.st_size).map_err(|_| {
                    LightrError::InvalidManifest("OCI file has negative size".into())
                })?;
                let mut reader = PositionalReader {
                    file: Arc::clone(&file),
                    offset: 0,
                };
                let (digest, captured_size) = Digest::of_reader(&mut reader)?;
                if captured_size != size {
                    return Err(LightrError::InvalidManifest(
                        "OCI file changed during descriptor capture".into(),
                    ));
                }
                entries.push(Entry::File {
                    path: path.clone(),
                    #[allow(clippy::useless_conversion)]
                    mode: u32::from(pinned.st_mode & 0o7777),
                    size,
                    digest,
                });
                files.insert(path, file);
            }
            FileType::Symlink => {
                let target = fs::readlinkat(dir, &name, Vec::new())
                    .map_err(invalid)?
                    .to_str()
                    .map_err(|_| {
                        LightrError::InvalidManifest("OCI link target is not valid UTF-8".into())
                    })?
                    .to_owned();
                entries.push(Entry::Symlink { path, target });
            }
            _ => {
                return Err(LightrError::Unsupported(
                    "unsupported OCI staging entry type".into(),
                ))
            }
        }
    }
    if !prefix.is_empty() && empty {
        entries.push(Entry::Dir {
            path: prefix.to_owned(),
        });
    }
    Ok(())
}
impl UnixLayerFs {
    pub(super) fn new() -> Result<Self> {
        // `/tmp` is sticky: other UIDs cannot rename or remove this import's stage.
        // Same-UID filesystem races are outside ADR-0021's stated threat model.
        let parent = File::open("/tmp").map_err(LightrError::Io)?;
        let parent_stat = fs::fstat(&parent).map_err(invalid)?;
        if FileType::from_raw_mode(parent_stat.st_mode) != FileType::Directory
            || parent_stat.st_mode & 0o1000 == 0
        {
            return Err(LightrError::Unsupported(
                "OCI staging requires sticky /tmp parent".into(),
            ));
        }
        for _ in 0..32 {
            let stage = OsString::from(format!(
                "lightr-oci-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            match fs::mkdirat(&parent, &stage, Mode::from_raw_mode(0o700)) {
                Ok(()) => {
                    let root = open_dir(&parent, &stage)?;
                    fs::fchmod(&root, Mode::from_raw_mode(0o700)).map_err(invalid)?;
                    let stat = fs::fstat(&root).map_err(invalid)?;
                    return Ok(Self {
                        root,
                        #[cfg(test)]
                        path: std::path::Path::new("/tmp").join(&stage),
                        parent,
                        stage_name: stage,
                        identity: identity(stat),
                    });
                }
                Err(rustix::io::Errno::EXIST) => (),
                Err(error) => return Err(invalid(error)),
            }
        }
        Err(LightrError::InvalidManifest(
            "private OCI staging reservation exhausted 32 candidates".into(),
        ))
    }
    pub(super) fn snapshot_source(&self) -> Result<(UnixSnapshotSource, Manifest)> {
        let mut entries = Vec::new();
        let mut files = BTreeMap::new();
        capture_dir(&self.root, "", &mut entries, &mut files)?;
        entries.sort_by(|left, right| left.path().cmp(right.path()));
        let total_size = entries
            .iter()
            .filter_map(|entry| match entry {
                Entry::File { size, .. } => Some(*size),
                _ => None,
            })
            .sum();
        Ok((
            UnixSnapshotSource { files },
            Manifest {
                version: 1,
                total_size,
                entries,
            },
        ))
    }
    #[cfg(test)]
    pub(super) fn path(&self) -> &std::path::Path {
        &self.path
    }
    pub(super) fn cleanup(&mut self) -> Result<()> {
        // Only recurse through descriptor-pinned contents after confirming this
        // import still owns named stage. Different named object stays untouched.
        let named = fs::statat(&self.parent, &self.stage_name, AtFlags::SYMLINK_NOFOLLOW)
            .map_err(invalid)?;
        if identity(named) != self.identity {
            return Err(LightrError::InvalidManifest(
                "OCI staging name replaced before cleanup".into(),
            ));
        }
        clear(&self.root)?;
        fs::unlinkat(&self.parent, &self.stage_name, AtFlags::REMOVEDIR).map_err(invalid)
    }
}
impl Drop for UnixLayerFs {
    fn drop(&mut self) {
        let _ = self.cleanup();
    }
}
impl LayerFs for UnixLayerFs {
    fn apply(&mut self, op: &LayerOp) -> Result<()> {
        match op {
            LayerOp::Directory(path) => {
                ensure(&self.root, path)?;
            }
            LayerOp::Whiteout {
                parent,
                name: Some(name),
            } => {
                let parent = ensure(&self.root, parent)?;
                unlink_one(&parent, name)?;
            }
            LayerOp::Whiteout { parent, name: None } => {
                let dir = ensure(&self.root, parent)?;
                clear(&dir)?;
            }
            LayerOp::Regular { dest, data, mode } => {
                let (parents, leaf) = dest.split_at(dest.len() - 1);
                let parent = ensure(&self.root, parents)?;
                unlink_one(&parent, &leaf[0])?;
                let fd = fs::openat(
                    &parent,
                    &leaf[0],
                    OFlags::WRONLY
                        | OFlags::CREATE
                        | OFlags::EXCL
                        | OFlags::NOFOLLOW
                        | OFlags::CLOEXEC,
                    Mode::from_raw_mode(*mode as _),
                )
                .map_err(invalid)?;
                let mut file = File::from(fd);
                file.write_all(data).map_err(LightrError::Io)?;
                fs::fchmod(&file, Mode::from_raw_mode(*mode as _)).map_err(invalid)?;
            }
            LayerOp::Symlink { dest, target } => {
                let (parents, leaf) = dest.split_at(dest.len() - 1);
                let parent = ensure(&self.root, parents)?;
                unlink_one(&parent, &leaf[0])?;
                fs::symlinkat(target, &parent, &leaf[0]).map_err(invalid)?;
            }
            LayerOp::Hardlink { dest, target } => {
                let (source_parents, source_leaf) = target.split_at(target.len() - 1);
                let source_parent = existing(&self.root, source_parents)?;
                let source = open_regular(&source_parent, &source_leaf[0]).map_err(|_| {
                    LightrError::InvalidManifest("hardlink target not found".into())
                })?;
                let source_identity = fs::fstat(&source).map_err(invalid)?;
                let (parents, leaf) = dest.split_at(dest.len() - 1);
                let parent = ensure(&self.root, parents)?;
                unlink_one(&parent, &leaf[0])?;
                fs::linkat(
                    &source_parent,
                    &source_leaf[0],
                    &parent,
                    &leaf[0],
                    AtFlags::empty(),
                )
                .map_err(invalid)?;
                let linked = open_regular(&parent, &leaf[0])?;
                let linked_identity = fs::fstat(&linked).map_err(invalid)?;
                if (linked_identity.st_dev, linked_identity.st_ino)
                    != (source_identity.st_dev, source_identity.st_ino)
                {
                    let _ = fs::unlinkat(&parent, &leaf[0], AtFlags::empty());
                    return Err(LightrError::InvalidManifest(
                        "hardlink source changed during link".into(),
                    ));
                }
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use lightr_index::{hydrate, prepare_snapshot_from_source};
    use lightr_store::Store;

    fn path(parts: &[&str]) -> Vec<OsString> {
        parts.iter().map(OsString::from).collect()
    }

    // Test-only teardown, including assertion failure during mutation probes.
    struct StageGuard(PathBuf);
    impl Drop for StageGuard {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn hardlink_preserves_inode_identity() {
        let mut fs = UnixLayerFs::new().unwrap();
        fs.apply(&LayerOp::Regular {
            dest: path(&["source"]),
            data: b"data".to_vec(),
            mode: 0o644,
        })
        .unwrap();
        fs.apply(&LayerOp::Hardlink {
            dest: path(&["copy"]),
            target: path(&["source"]),
        })
        .unwrap();
        let source = std::fs::metadata(fs.path().join("source")).unwrap();
        let copy = std::fs::metadata(fs.path().join("copy")).unwrap();
        use std::os::unix::fs::MetadataExt;
        assert_eq!((source.dev(), source.ino()), (copy.dev(), copy.ino()));
    }

    #[test]
    fn whiteout_of_symlink_does_not_touch_target() {
        let outside = tempfile::NamedTempFile::new().unwrap();
        std::fs::write(outside.path(), b"retained").unwrap();
        let mut fs = UnixLayerFs::new().unwrap();
        fs.apply(&LayerOp::Symlink {
            dest: path(&["link"]),
            target: outside.path().as_os_str().to_os_string(),
        })
        .unwrap();
        fs.apply(&LayerOp::Whiteout {
            parent: vec![],
            name: Some(OsString::from("link")),
        })
        .unwrap();
        assert_eq!(std::fs::read(outside.path()).unwrap(), b"retained");
    }

    #[test]
    fn stage_is_private_under_sticky_temp_parent() {
        let fs = UnixLayerFs::new().unwrap();
        let stage = std::fs::metadata(fs.path()).unwrap();
        let parent = fs::fstat(&fs.parent).unwrap();
        use std::os::unix::fs::MetadataExt;
        assert_eq!(stage.mode() & 0o777, 0o700);
        assert_ne!(parent.st_mode & 0o1000, 0);
    }

    #[test]
    fn cleanup_removes_owned_stage_before_drop() {
        let mut layer = UnixLayerFs::new().unwrap();
        layer
            .apply(&LayerOp::Regular {
                dest: path(&["nested", "data"]),
                data: b"owned".to_vec(),
                mode: 0o600,
            })
            .unwrap();
        let stage_path = layer.path().to_owned();
        let _stage_guard = StageGuard(stage_path.clone());
        let named =
            fs::statat(&layer.parent, &layer.stage_name, AtFlags::SYMLINK_NOFOLLOW).unwrap();
        assert_eq!(identity(named), identity(fs::fstat(&layer.root).unwrap()));
        assert_eq!(
            std::fs::read(stage_path.join("nested/data")).unwrap(),
            b"owned"
        );

        layer.cleanup().unwrap();

        // Observe removal while the owner is alive: Drop must not mask a no-op.
        assert_eq!(
            fs::statat(&layer.parent, &layer.stage_name, AtFlags::SYMLINK_NOFOLLOW).unwrap_err(),
            rustix::io::Errno::NOENT
        );
        assert_eq!(
            std::fs::symlink_metadata(&stage_path).unwrap_err().kind(),
            std::io::ErrorKind::NotFound
        );
    }

    #[test]
    fn cleanup_rejects_replaced_stage_and_preserves_both_trees() {
        // A deterministic same-UID swap exercises the identity boundary, not a
        // claim of protection from the adversary excluded by ADR-0021.
        let parked = tempfile::tempdir_in("/tmp").unwrap();
        let mut layer = UnixLayerFs::new().unwrap();
        layer
            .apply(&LayerOp::Regular {
                dest: path(&["owned"]),
                data: b"original".to_vec(),
                mode: 0o600,
            })
            .unwrap();
        let stage_path = layer.path().to_owned();
        let _replacement_guard = StageGuard(stage_path.clone());
        let original_path = parked.path().join("original");
        std::fs::rename(&stage_path, &original_path).unwrap();
        std::fs::create_dir(&stage_path).unwrap();
        std::fs::write(stage_path.join("sentinel"), b"replacement").unwrap();
        let pinned = identity(fs::fstat(&layer.root).unwrap());
        let replacement =
            fs::statat(&layer.parent, &layer.stage_name, AtFlags::SYMLINK_NOFOLLOW).unwrap();
        let replacement_identity = identity(replacement);
        assert_eq!(pinned, layer.identity);
        assert_ne!(replacement_identity, pinned);
        assert_eq!(
            identity(fs::fstat(File::open(&original_path).unwrap()).unwrap()),
            pinned
        );

        let result = layer.cleanup();

        // A nonempty replacement alone would also survive unlinkat failure if
        // the identity check vanished. The pinned tree must remain intact too.
        assert_eq!(
            std::fs::read(original_path.join("owned")).unwrap(),
            b"original"
        );
        assert!(matches!(
            result,
            Err(LightrError::InvalidManifest(message))
                if message == "OCI staging name replaced before cleanup"
        ));
        drop(layer); // Automatic cleanup must reject the same replacement.
        assert_eq!(
            identity(fs::fstat(File::open(&stage_path).unwrap()).unwrap()),
            replacement_identity
        );
        assert_eq!(
            std::fs::read(stage_path.join("sentinel")).unwrap(),
            b"replacement"
        );
        assert_eq!(
            std::fs::read(original_path.join("owned")).unwrap(),
            b"original"
        );
    }

    #[test]
    fn captured_file_survives_unlink_before_prepare() {
        let temp = tempfile::TempDir::new().unwrap();
        let store = Store::open(temp.path().join("store")).unwrap();
        let mut fs = UnixLayerFs::new().unwrap();
        fs.apply(&LayerOp::Regular {
            dest: path(&["data"]),
            data: b"captured".to_vec(),
            mode: 0o644,
        })
        .unwrap();
        let (source, manifest) = fs.snapshot_source().unwrap();
        std::fs::remove_file(fs.path().join("data")).unwrap();
        let pending =
            prepare_snapshot_from_source(&source, &store, "@test/pinned", manifest).unwrap();
        fs.cleanup().unwrap();
        pending.commit().unwrap();
        let restored = temp.path().join("restored");
        hydrate(&restored, &store, "@test/pinned").unwrap();
        assert_eq!(std::fs::read(restored.join("data")).unwrap(), b"captured");
    }
}
