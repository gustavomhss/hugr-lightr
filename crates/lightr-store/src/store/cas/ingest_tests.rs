//! Regressions for the hash -> copy -> publish integrity boundary.

use super::{finish_ingest, ingest_file, object_path, CowRung};
use crate::Store;
use lightr_core::{Digest, LightrError};
use std::fs;
use std::path::PathBuf;
use tempfile::TempDir;

fn stage(store: &Store, expected: Digest, bytes: &[u8]) -> (PathBuf, PathBuf, PathBuf) {
    let dest = object_path(store.root(), &expected);
    let shard = dest.parent().unwrap().to_path_buf();
    fs::create_dir_all(&shard).unwrap();
    let tmp = shard.join(".tmp-ingest-regression");
    fs::write(&tmp, bytes).unwrap();
    (tmp, dest, shard)
}

#[test]
fn staged_bytes_must_match_the_pre_copy_digest() {
    let temp = TempDir::new().unwrap();
    let store = Store::open(temp.path().join("store")).unwrap();
    let expected = Digest::of_bytes(b"before");
    let actual = Digest::of_bytes(b"after!");
    // Model a source that changed between the initial hash and the copy.
    let (tmp, dest, shard) = stage(&store, expected, b"after!");

    match finish_ingest(&tmp, &dest, &shard, expected) {
        Err(LightrError::Integrity {
            expected: got_expected,
            actual: got_actual,
        }) => {
            assert_eq!(got_expected, expected);
            assert_eq!(got_actual, actual);
        }
        _ => panic!("mismatched staging bytes must never be published"),
    }
    assert!(!dest.exists());
    assert!(!tmp.exists(), "rejected staging file must be cleaned up");
    assert!(
        !store.exists(&actual),
        "a mismatch must not silently re-key"
    );
}

#[test]
fn missing_staged_file_does_not_publish_an_object() {
    let temp = TempDir::new().unwrap();
    let store = Store::open(temp.path().join("store")).unwrap();
    let expected = Digest::of_bytes(b"data");
    let (tmp, dest, shard) = stage(&store, expected, b"data");
    fs::remove_file(&tmp).unwrap();

    assert!(matches!(
        finish_ingest(&tmp, &dest, &shard, expected),
        Err(LightrError::Io(_))
    ));
    assert!(!dest.exists());
}

#[test]
fn verified_staging_bytes_are_published_and_read_back() {
    let temp = TempDir::new().unwrap();
    let store = Store::open(temp.path().join("store")).unwrap();
    let bytes = b"captured bytes";
    let expected = Digest::of_bytes(bytes);
    let (tmp, dest, shard) = stage(&store, expected, bytes);

    assert_eq!(
        finish_ingest(&tmp, &dest, &shard, expected).unwrap(),
        expected
    );
    assert!(!tmp.exists());
    assert_eq!(store.get_bytes(&expected).unwrap(), bytes);
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            fs::metadata(dest).unwrap().permissions().mode() & 0o777,
            0o444
        );
    }
}

fn assert_ingested_bytes_survive_source_change(rung: Option<CowRung>) {
    let temp = TempDir::new().unwrap();
    let store = Store::open(temp.path().join("store")).unwrap();
    let source = temp.path().join("source");
    let before = b"before";
    fs::write(&source, before).unwrap();
    let rung = rung.unwrap_or_else(|| store.rung());

    let digest = ingest_file(store.root(), &source, rung).unwrap();
    assert_eq!(digest, Digest::of_bytes(before));
    fs::write(&source, b"after!").unwrap();
    assert_eq!(store.get_bytes(&digest).unwrap(), before);
}

#[test]
fn copy_fallback_preserves_bytes_independently_of_source() {
    assert_ingested_bytes_survive_source_change(Some(CowRung::Copy));
}

#[test]
fn probed_copy_rung_preserves_bytes_independently_of_source() {
    assert_ingested_bytes_survive_source_change(None);
}

#[test]
fn reader_ingest_rejects_digest_or_length_mismatch_without_object() {
    let temp = TempDir::new().unwrap();
    let store = Store::open(temp.path().join("store")).unwrap();
    let expected = Digest::of_bytes(b"expected");

    assert!(matches!(
        store.ingest_reader(&mut b"actual".as_slice(), expected, 6),
        Err(LightrError::Integrity { .. })
    ));
    assert!(!store.exists(&expected));

    let bytes = b"expected";
    assert!(matches!(
        store.ingest_reader(&mut bytes.as_slice(), expected, 1),
        Err(LightrError::InvalidManifest(_))
    ));
    assert!(!store.exists(&expected));
}
