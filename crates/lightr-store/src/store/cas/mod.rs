//! CAS object plane — put_bytes / ingest_file / get_bytes / materialize_file.
//!
//! Objects are content-addressed (blake3), sharded 2/62, stored read-only (0o444).
//! Writes go through a temp+rename+fsync pipeline for crash durability.

use super::cow::{cow_copy_file, try_cow_at_rung, CowRung};
use super::lock::write_guard;
use lightr_core::{Digest, LightrError, Result};
#[cfg(unix)]
use std::ffi::CString;
#[cfg(unix)]
use std::fs::Permissions;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
#[cfg(unix)]
use std::os::fd::{AsRawFd, FromRawFd};
#[cfg(unix)]
use std::os::unix::fs::OpenOptionsExt;
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
pub(crate) mod owned_temp;
/// Additive private-file preparation; no existing Store route is changed.
pub mod preparation;
use owned_temp::OwnedTemp;

// ── path helpers ──────────────────────────────────────────────────────────────

/// Returns the two-char shard prefix and 62-char remainder from a Digest hex.
pub(super) fn shard_parts(hex: &str) -> (&str, &str) {
    (&hex[..2], &hex[2..])
}

/// Object path: <root>/objects/<2hex>/<62hex>
pub(crate) fn object_path(root: &Path, d: &Digest) -> PathBuf {
    let hex = d.to_hex();
    let (pre, rest) = shard_parts(&hex);
    root.join("objects").join(pre).join(rest)
}

/// fsync the parent directory so the rename (directory entry change) is
/// crash-durable on macOS/Linux.
///
/// On Windows: NTFS has no portable directory fsync API (FlushFileBuffers on a
/// directory handle is not guaranteed to flush directory metadata to disk across
/// all NTFS configurations). This function is a documented no-op on Windows.
/// The weaker guarantee: file data and the rename are durable once
/// FlushFileBuffers is called on the FILE itself (done in atomic_write before
/// rename), but the directory entry update may not be crash-synced.
/// This is acceptable for the CAS store (objects are content-addressed;
/// a missing directory entry after a crash means re-ingest, not corruption).
pub(super) fn fsync_dir(dir: &Path) -> std::io::Result<()> {
    #[cfg(unix)]
    {
        let f = File::open(dir)?;
        f.sync_all()?;
    }
    // Windows: documented no-op — see function doc above.
    #[cfg(windows)]
    let _ = dir;
    Ok(())
}

/// Atomic write: write `data` to a temp file in `parent`, fsync the file,
/// rename to `dest`, then fsync the parent directory so the rename is
/// crash-durable.
pub(super) fn atomic_write(parent: &Path, dest: &Path, data: &[u8]) -> Result<()> {
    fs::create_dir_all(parent)?;
    let staging = OwnedTemp::new(parent, "w")?;
    let tmp = staging.payload();
    {
        let mut f = File::create(&tmp)?;
        f.write_all(data)?;
        // fsync before rename: flush file data to stable storage.
        #[cfg(unix)]
        f.sync_all()?;
        #[cfg(windows)]
        {
            // WIN-PATH: FlushFileBuffers ensures data is on disk before rename.
            use std::os::windows::io::AsRawHandle;
            use windows_sys::Win32::Storage::FileSystem::FlushFileBuffers;
            let handle = f.as_raw_handle();
            unsafe { FlushFileBuffers(handle as _) };
        }
    }
    fs::rename(&tmp, dest)?;
    fsync_dir(parent)?; // fsync parent dir after rename
    Ok(())
}

/// chmod a path to the given mode bits (unix only).
pub(super) fn set_mode(path: &Path, mode: u32) -> Result<()> {
    #[cfg(unix)]
    {
        fs::set_permissions(path, Permissions::from_mode(mode))?;
    }
    // Windows: mode bits are a Unix concept. Skip silently.
    // Windows uses ACLs/read-only attribute semantics — not set here.
    #[cfg(windows)]
    {
        let _ = (path, mode);
    }
    Ok(())
}

// ── CAS methods (called from Store) ─────────────────────────────────────────

/// Content-address `bytes` and store them.  Idempotent: if the object
/// already exists the digest is returned immediately without any write.
pub fn put_bytes(root: &Path, bytes: &[u8]) -> Result<Digest> {
    let _wg = write_guard(root)?;
    let d = Digest::of_bytes(bytes);
    let path = object_path(root, &d);

    if path.exists() {
        return Ok(d);
    }

    let hex = d.to_hex();
    let (pre, _) = shard_parts(&hex);
    let shard = root.join("objects").join(pre);
    fs::create_dir_all(&shard)?;

    let staging = OwnedTemp::new(&shard, &hex[..8])?;
    let tmp = staging.payload();
    {
        let mut f = File::create(&tmp)?;
        f.write_all(bytes)?;
        // fsync before rename: flush file data.
        #[cfg(unix)]
        f.sync_all()?;
        #[cfg(windows)]
        {
            // WIN-PATH: FlushFileBuffers on the file before rename.
            use std::os::windows::io::AsRawHandle;
            use windows_sys::Win32::Storage::FileSystem::FlushFileBuffers;
            let handle = f.as_raw_handle();
            unsafe { FlushFileBuffers(handle as _) };
        }
    }
    fs::rename(&tmp, &path)?;
    fsync_dir(&shard)?; // fsync parent dir after rename
    set_mode(&path, 0o444)?;

    Ok(d)
}

/// Hash `path` and CoW-clone it into the store.  Idempotent.
pub fn ingest_file(root: &Path, path: &Path, rung: CowRung) -> Result<Digest> {
    let _wg = write_guard(root)?;
    let d = Digest::of_file(path)?;
    let dest = object_path(root, &d);

    if dest.exists() {
        return Ok(d);
    }

    let hex = d.to_hex();
    let (pre, _) = shard_parts(&hex);
    let shard = root.join("objects").join(pre);
    fs::create_dir_all(&shard)?;

    let staging = OwnedTemp::new(&shard, &hex[..8])?;
    let tmp = staging.payload();

    // Try CoW into a temp, then rename+chmod.
    // On failure fall through to fs::copy.
    let used_cow = match try_cow_at_rung(path, &tmp, rung) {
        Ok(()) => true,
        Err(_) => {
            let _ = fs::remove_file(&tmp);
            fs::copy(path, &tmp)?;
            false
        }
    };
    let _ = used_cow; // counted but not surfaced in API

    finish_ingest(&tmp, &dest, &shard, d)
}

/// Stream one expected object into CAS without retaining its contents in memory.
/// Both digest and length are checked before the staged file becomes visible.
pub fn ingest_reader(
    root: &Path,
    reader: &mut impl Read,
    expected: Digest,
    expected_length: u64,
) -> Result<Digest> {
    let _wg = write_guard(root)?;
    let hex = expected.to_hex();
    let (pre, _) = shard_parts(&hex);
    let shard = root.join("objects").join(pre);
    fs::create_dir_all(&shard)?;
    let staging = OwnedTemp::new(&shard, &hex[..8])?;
    let tmp = staging.payload();
    let result = (|| {
        let mut file = File::create(&tmp)?;
        let (actual, length) = {
            let mut tee = TeeReader {
                reader,
                writer: &mut file,
            };
            Digest::of_reader(&mut tee)?
        };
        file.sync_all()?;
        drop(file);

        if actual != expected {
            return Err(LightrError::Integrity { expected, actual });
        }
        if length != expected_length {
            return Err(LightrError::InvalidManifest(format!(
                "stream length mismatch: expected {expected_length} got {length}"
            )));
        }

        let dest = object_path(root, &expected);
        if dest.exists() {
            return Ok(expected);
        }
        fs::rename(&tmp, &dest)?;
        fsync_dir(&shard)?;
        set_mode(&dest, 0o444)?;
        Ok(expected)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&tmp);
    }
    result
}

struct TeeReader<'a, R, W> {
    reader: &'a mut R,
    writer: &'a mut W,
}

impl<R: Read, W: Write> Read for TeeReader<'_, R, W> {
    fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
        let count = self.reader.read(buffer)?;
        self.writer.write_all(&buffer[..count])?;
        Ok(count)
    }
}

/// Validate the copied bytes, not just the earlier observation of the source.
/// Kept separate so tests can deterministically model a source mutation between
/// hashing and copying, without races or hooks in the public API.
fn finish_ingest(tmp: &Path, dest: &Path, shard: &Path, expected: Digest) -> Result<Digest> {
    let result = (|| {
        let actual = Digest::of_file(tmp)?;
        if actual != expected {
            return Err(LightrError::Integrity { expected, actual });
        }

        // The staged file is private to this ingestion. Verify it before making
        // it visible under a content-addressed name, then preserve durability.
        let f = File::open(tmp)?;
        #[cfg(unix)]
        f.sync_all()?;
        #[cfg(windows)]
        {
            use std::os::windows::io::AsRawHandle;
            use windows_sys::Win32::Storage::FileSystem::FlushFileBuffers;
            let handle = f.as_raw_handle();
            unsafe { FlushFileBuffers(handle as _) };
        }
        drop(f);
        fs::rename(tmp, dest)?;
        fsync_dir(shard)?;
        set_mode(dest, 0o444)?;
        Ok(expected)
    })();
    if result.is_err() {
        // Only remove our unpublished staging file, never a CAS object. If a
        // later durability step failed after rename, the valid object remains.
        let _ = fs::remove_file(tmp);
    }
    result
}

/// Read and verify `d`.  Missing → NotFound.  Hash mismatch → Integrity
/// (evidence file kept, never deleted).
pub fn get_bytes(root: &Path, d: &Digest) -> Result<Vec<u8>> {
    let path = object_path(root, d);
    if !path.exists() {
        return Err(LightrError::NotFound(*d));
    }
    let bytes = fs::read(&path)?;
    let actual = Digest::of_bytes(&bytes);
    if actual != *d {
        return Err(LightrError::Integrity {
            expected: *d,
            actual,
        });
    }
    Ok(bytes)
}

/// Open and verify one immutable CAS object without buffering its bytes.
#[allow(dead_code)]
pub(crate) fn open_verified(
    root: &Path,
    d: &Digest,
    mut checkpoint: impl FnMut() -> std::io::Result<()>,
) -> Result<File> {
    let mut file = match open_object_file(root, d) {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Err(lightr_core::LightrError::NotFound(*d));
        }
        Err(error) => return Err(error.into()),
    };
    let (actual, _) = Digest::of_reader_checked(&mut file, &mut checkpoint)?;
    if actual != *d {
        return Err(lightr_core::LightrError::Integrity {
            expected: *d,
            actual,
        });
    }
    file.seek(SeekFrom::Start(0))?;
    Ok(file)
}

#[allow(dead_code)]
fn open_object_file(root: &Path, d: &Digest) -> std::io::Result<File> {
    #[cfg(unix)]
    let file = {
        let root = open_directory(root)?;
        let objects = openat_directory(&root, "objects")?;
        let hex = d.to_hex();
        let (shard, object) = shard_parts(&hex);
        let shard = openat_directory(&objects, shard)?;
        openat_object(&shard, object)?
    };
    #[cfg(not(unix))]
    let file = OpenOptions::new().read(true).open(object_path(root, d))?;
    if !file.metadata()?.is_file() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "CAS object is not a regular file",
        ));
    }
    Ok(file)
}

#[cfg(unix)]
fn open_directory(path: &Path) -> std::io::Result<File> {
    OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)
}

#[cfg(unix)]
fn openat_directory(parent: &File, name: &str) -> std::io::Result<File> {
    openat_component(
        parent,
        name,
        libc::O_CLOEXEC | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_NONBLOCK,
    )
}

#[cfg(unix)]
fn openat_object(parent: &File, name: &str) -> std::io::Result<File> {
    openat_component(
        parent,
        name,
        libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK,
    )
}

#[cfg(unix)]
fn openat_component(parent: &File, name: &str, flags: libc::c_int) -> std::io::Result<File> {
    let name = CString::new(name).map_err(|_| {
        std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "NUL in CAS object component",
        )
    })?;
    let fd = unsafe { libc::openat(parent.as_raw_fd(), name.as_ptr(), libc::O_RDONLY | flags) };
    if fd < 0 {
        return Err(std::io::Error::last_os_error());
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}

/// Returns true iff the object file exists (no rehash).
pub fn exists(root: &Path, d: &Digest) -> bool {
    object_path(root, d).exists()
}

/// CoW the object identified by `d` to `dest`, then set its mode to
/// `mode`.  Missing object → NotFound.  Parent dirs created if absent.
pub fn materialize_file(
    root: &Path,
    d: &Digest,
    dest: &Path,
    mode: u32,
    rung: CowRung,
) -> Result<()> {
    let src = object_path(root, d);
    if !src.exists() {
        return Err(LightrError::NotFound(*d));
    }

    // FIX-#76 (CAS integrity): re-hash the stored object and verify it against the
    // requested digest BEFORE the CoW, so a bit-rotted object can never silently
    // reach a build. Ingest (`put_bytes`/`ingest_file`) already content-addresses
    // at WRITE time — the object path IS its digest — so a freshly written object
    // is correct by construction; this guards against on-disk corruption AFTER
    // ingest (the same bit-rot `get_bytes` already catches on its read path, which
    // this read path previously skipped). Fail-closed: a mismatch is an honest
    // Integrity error and the corrupt object is left as evidence (never deleted),
    // matching `get_bytes`. Correctness over perf for a content-addressed store.
    let actual = Digest::of_file(&src)?;
    if actual != *d {
        return Err(LightrError::Integrity {
            expected: *d,
            actual,
        });
    }

    if let Some(p) = dest.parent() {
        fs::create_dir_all(p)?;
    }

    // Remove any stale dest so clonefile can succeed (it fails if dst exists).
    let _ = fs::remove_file(dest);

    cow_copy_file(&src, dest, rung)?;

    // Always apply the manifest mode (clonefile carries 0o444 from the store).
    set_mode(dest, mode)?;

    Ok(())
}

/// gc sweep only: chmod 0o644 then remove one object.
/// Object absent ⇒ Ok(()) (idempotent).
pub fn remove_object(root: &Path, d: &Digest) -> Result<()> {
    let path = object_path(root, d);
    if !path.exists() {
        return Ok(());
    }
    set_mode(&path, 0o644)?;
    fs::remove_file(&path)?;
    Ok(())
}

#[cfg(test)]
mod tests;

#[cfg(test)]
mod ingest_tests;
