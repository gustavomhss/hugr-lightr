//! snapshot: SnapshotReport, snapshot.

use super::{codec::Index, scan::scan};
use lightr_core::{Digest, Entry, LightrError, Manifest, RefRecord, Result};
use lightr_store::Store;
use rayon::prelude::*;
use std::{
    path::Path,
    time::{SystemTime, UNIX_EPOCH},
};

pub struct SnapshotReport {
    pub root: lightr_core::Digest,
    pub files: u64,
    pub bytes_total: u64,
    pub objects_new: u64,
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
    publish_snapshot_with(root, store, name, walk.manifest, publish)
}

#[cfg(test)]
fn publish_snapshot(
    root: &Path,
    store: &Store,
    name: &str,
    manifest: Manifest,
) -> Result<SnapshotReport> {
    publish_snapshot_with(root, store, name, manifest, |rec| store.ref_put(rec))
}

/// Publish a captured manifest only after every required ingestion succeeds.
/// A live source may change after scan: reject a digest mismatch rather than
/// publishing a ref whose manifest names bytes we did not preserve. This is not
/// a point-in-time filesystem snapshot; the caller may retry after a mutation.
fn publish_snapshot_with<F>(
    root: &Path,
    store: &Store,
    name: &str,
    manifest: Manifest,
    publish: F,
) -> Result<SnapshotReport>
where
    F: FnOnce(&RefRecord) -> Result<()>,
{
    // Per-object write guards alone leave a gap before ref publication in which
    // gc could sweep newly ingested objects. Keep one shared guard across the
    // whole transaction, including reuse of existing objects and the manifest.
    let _publication_guard = store.write_guard()?;
    let prev = store.ref_get(name)?;

    let file_entries: Vec<(&str, Digest)> = manifest
        .entries
        .iter()
        .filter_map(|entry| match entry {
            Entry::File { path, digest, .. } => Some((path.as_str(), *digest)),
            _ => None,
        })
        .collect();

    // Do not filter out ingestion errors: any failure must prevent both the
    // manifest write and ref advancement. Already ingested, unreferenced objects
    // may remain on failure; normal gc can reclaim them after the guard drops.
    let ingest_results: Result<Vec<u64>> = file_entries
        .par_iter()
        .map(|(rel, expected)| {
            if store.exists(expected) {
                return Ok(0);
            }
            let actual = store.ingest_file(&root.join(rel))?;
            if actual != *expected {
                return Err(LightrError::Integrity {
                    expected: *expected,
                    actual,
                });
            }
            Ok(1)
        })
        .collect();
    let objects_new = ingest_results?.into_iter().sum();

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
    publish(&rec)?;

    Ok(SnapshotReport {
        root: manifest_digest,
        files: file_entries.len() as u64,
        bytes_total: manifest.total_size,
        objects_new,
    })
}

#[cfg(test)]
#[path = "snapshot_tests.rs"]
mod tests;
