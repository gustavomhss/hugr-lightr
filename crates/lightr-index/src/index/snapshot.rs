//! snapshot: SnapshotReport, snapshot.

use super::{codec::Index, scan::scan};
use lightr_core::{Digest, Entry, Manifest, RefRecord, Result};
use lightr_store::{Store, WriteGuard};
use std::{
    io::Read,
    path::Path,
    time::{SystemTime, UNIX_EPOCH},
};

pub struct SnapshotReport {
    pub root: lightr_core::Digest,
    pub files: u64,
    pub bytes_total: u64,
    pub objects_new: u64,
}

/// Platform-neutral file source for a previously captured manifest.
/// Implementations return a fresh stream for each relative manifest path.
pub trait SnapshotSource {
    fn open(&self, relative: &str) -> Result<Box<dyn Read>>;
}

impl SnapshotSource for Path {
    fn open(&self, relative: &str) -> Result<Box<dyn Read>> {
        Ok(Box::new(std::fs::File::open(self.join(relative))?))
    }
}

/// Fully ingested snapshot held private until [`PendingSnapshot::commit`].
/// Dropping this value releases its write guard without advancing its ref.
pub struct PendingSnapshot<'a> {
    store: &'a Store,
    _guard: WriteGuard,
    record: RefRecord,
    report: SnapshotReport,
}

impl PendingSnapshot<'_> {
    /// Publish prepared manifest by atomically advancing its ref.
    pub fn commit(self) -> Result<SnapshotReport> {
        let store = self.store;
        self.commit_with(|record| store.ref_put(record))
    }

    /// Publish prepared ref through caller-selected Store seam.
    pub fn commit_with<F>(self, publish: F) -> Result<SnapshotReport>
    where
        F: FnOnce(&RefRecord) -> Result<()>,
    {
        publish(&self.record)?;
        Ok(self.report)
    }
}

pub fn snapshot(root: &Path, store: &Store, name: &str) -> Result<SnapshotReport> {
    snapshot_with_publisher(root, store, name, |rec| store.ref_put(rec))
}

/// Snapshot then publish its prepared ref through caller-selected Store seam.
/// OCI uses this to make its ref and retained metadata one visibility action.
pub fn snapshot_with_publisher<F>(
    root: &Path,
    store: &Store,
    name: &str,
    publish: F,
) -> Result<SnapshotReport>
where
    F: FnOnce(&RefRecord) -> Result<()>,
{
    lightr_core::validate_ref_name(name)?;

    let mut index = Index::load_for(root)?;
    let walk = scan(root, &mut index)?;
    prepare_snapshot_from_source(root, store, name, walk.manifest)?.commit_with(publish)
}

/// Publish a captured manifest only after every required ingestion succeeds.
/// A live source may change after scan: reject a digest mismatch rather than
/// publishing a ref whose manifest names bytes we did not preserve. This is not
/// a point-in-time filesystem snapshot; the caller may retry after a mutation.
pub fn prepare_snapshot_from_source<'a>(
    source: &(impl SnapshotSource + ?Sized),
    store: &'a Store,
    name: &str,
    manifest: Manifest,
) -> Result<PendingSnapshot<'a>> {
    // Per-object write guards alone leave a gap before ref publication in which
    // gc could sweep newly ingested objects. Keep one shared guard across the
    // whole transaction, including reuse of existing objects and the manifest.
    let publication_guard = store.write_guard()?;
    let prev = store.ref_get(name)?;

    let file_entries: Vec<(&str, Digest, u64)> = manifest
        .entries
        .iter()
        .filter_map(|entry| match entry {
            Entry::File {
                path, digest, size, ..
            } => Some((path.as_str(), *digest, *size)),
            _ => None,
        })
        .collect();

    // Existing objects retain legacy snapshot behavior: source need not remain
    // available after its content has been preserved. Missing objects stream
    // directly into CAS and validate both expected digest and manifest length.
    let mut objects_new = 0;
    for entry in &manifest.entries {
        let Entry::File {
            path, digest, size, ..
        } = entry
        else {
            continue;
        };
        if store.exists(digest) {
            continue;
        }
        let mut reader = source.open(path)?;
        store.ingest_reader(&mut reader, *digest, *size)?;
        objects_new += 1;
    }

    let manifest_bytes = manifest.encode();
    let manifest_digest = store.put_bytes(&manifest_bytes)?;

    let parent = prev.map(|r| r.root);
    let created_at_unix = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);

    let rec = RefRecord {
        name: name.to_string(),
        root: manifest_digest,
        parent,
        created_at_unix,
        tool_version: env!("CARGO_PKG_VERSION").to_string(),
    };
    Ok(PendingSnapshot {
        store,
        _guard: publication_guard,
        record: rec,
        report: SnapshotReport {
            root: manifest_digest,
            files: file_entries.len() as u64,
            bytes_total: manifest.total_size,
            objects_new,
        },
    })
}

#[cfg(test)]
#[path = "snapshot_tests.rs"]
mod tests;
