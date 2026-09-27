use super::*;
use crate::Store;
use std::sync::{Arc, Barrier};
use std::thread;
use tempfile::TempDir;

fn tmp_store() -> (TempDir, Store) {
    let dir = TempDir::new().unwrap();
    let store = Store::open(dir.path().join("store")).unwrap();
    (dir, store)
}

fn record(name: &str, root: &[u8]) -> RefRecord {
    RefRecord {
        name: name.into(),
        root: Digest::of_bytes(root),
        parent: None,
        created_at_unix: 7,
        tool_version: "test".into(),
    }
}

fn manifest(body: &[u8]) -> ImageManifestRecord {
    ImageManifestRecord {
        manifest_bytes: body.into(),
        descriptors: vec![],
        platform: "linux/amd64".into(),
    }
}

#[test]
fn locie1_golden_frame_and_all_read_apis_roundtrip() {
    let (_dir, store) = tmp_store();
    let rec = record("image", b"root");
    let config = b"{\"config\":true}";
    let image_manifest = manifest(b"{\"schemaVersion\":2}");
    store
        .publish_image_ref(&rec, Some(config), Some(&image_manifest))
        .unwrap();

    let config_digest = Digest::of_bytes(config);
    let manifest_digest = Digest::of_bytes(&encode_manifest_record(&image_manifest));
    let mut expected = Vec::new();
    expected.extend_from_slice(MAGIC);
    expected.extend_from_slice(&1u32.to_le_bytes());
    let encoded = rec.encode();
    expected.extend_from_slice(&(encoded.len() as u32).to_le_bytes());
    expected.extend_from_slice(&encoded);
    expected.push(1);
    expected.extend_from_slice(&config_digest.0);
    expected.push(1);
    expected.extend_from_slice(&manifest_digest.0);
    let path = refs::ref_path(store.root(), &lightr_core::ref_key("image"));
    assert_eq!(std::fs::read(path).unwrap(), expected);
    assert_eq!(store.ref_get("image").unwrap(), Some(rec.clone()));
    assert_eq!(
        store.image_config_get("image").unwrap(),
        Some(config.to_vec())
    );
    assert_eq!(
        store.image_manifest_get("image").unwrap(),
        Some(image_manifest.clone())
    );
    assert_eq!(
        store.image_ref_get("image").unwrap(),
        Some(ImageRef {
            record: rec,
            config: Some(config.to_vec()),
            manifest: Some(image_manifest),
        })
    );
}

#[test]
fn tagged_malformed_frames_never_fall_back() {
    let (_dir, store) = tmp_store();
    let path = refs::ref_path(store.root(), &lightr_core::ref_key("image"));
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    let rec = record("image", b"root").encode();
    let frame = |parts: &[&[u8]]| {
        let mut out = MAGIC.to_vec();
        for part in parts {
            out.extend_from_slice(part);
        }
        out
    };
    let cases = [
        MAGIC.to_vec(),
        frame(&[&2u32.to_le_bytes()]),
        frame(&[&1u32.to_le_bytes(), &u32::MAX.to_le_bytes()]),
        frame(&[
            &1u32.to_le_bytes(),
            &(rec.len() as u32).to_le_bytes(),
            &rec,
            &[2],
        ]),
        frame(&[
            &1u32.to_le_bytes(),
            &(rec.len() as u32).to_le_bytes(),
            &rec,
            &[0, 0, 9],
        ]),
    ];
    for bytes in cases {
        std::fs::write(&path, bytes).unwrap();
        let error = store.ref_get("image").unwrap_err();
        assert!(
            matches!(error, LightrError::InvalidManifest(message) if message.starts_with("malformed LOCIE1 envelope:"))
        );
    }
}

#[test]
fn tagged_invalid_flag_has_no_legacy_interpretation() {
    let (_dir, store) = tmp_store();
    let path = refs::ref_path(store.root(), &lightr_core::ref_key("image"));
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    let rec = record("image", b"root").encode();
    let mut bytes = MAGIC.to_vec();
    bytes.extend_from_slice(&1u32.to_le_bytes());
    bytes.extend_from_slice(&(rec.len() as u32).to_le_bytes());
    bytes.extend_from_slice(&rec);
    bytes.extend_from_slice(&[2, 0]);
    std::fs::write(path, bytes).unwrap();
    let error = store.ref_get("image").unwrap_err();
    assert!(
        matches!(error, LightrError::InvalidManifest(message) if message == "malformed LOCIE1 envelope: invalid config-present flag")
    );
}

#[test]
fn reads_reject_envelope_record_at_wrong_ref_key() {
    let (_dir, store) = tmp_store();
    let path = refs::ref_path(store.root(), &lightr_core::ref_key("image"));
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    std::fs::write(
        path,
        encode_envelope(
            &record("other", b"root"),
            &PreparedImageRef {
                config: None,
                manifest: None,
            },
        )
        .unwrap(),
    )
    .unwrap();
    for result in [
        store.ref_get("image").map(|_| ()),
        store.image_ref_get("image").map(|_| ()),
        store.image_config_get("image").map(|_| ()),
        store.image_manifest_get("image").map(|_| ()),
    ] {
        assert!(matches!(
            result,
            Err(LightrError::InvalidManifest(message)) if message.contains("ref name does not match storage key")
        ));
    }
}

#[test]
fn legacy_sidecars_read_without_ref_but_tuple_read_requires_ref() {
    let (_dir, store) = tmp_store();
    store.image_config_put("image", b"sidecar").unwrap();
    let image_manifest = manifest(b"sidecar-manifest");
    store.image_manifest_put("image", &image_manifest).unwrap();

    assert_eq!(
        store.image_config_get("image").unwrap(),
        Some(b"sidecar".to_vec())
    );
    assert_eq!(
        store.image_manifest_get("image").unwrap(),
        Some(image_manifest)
    );
    assert!(store.image_ref_get("image").unwrap().is_none());
}

#[test]
fn legacy_ref_and_sidecars_remain_readable() {
    let (_dir, store) = tmp_store();
    let rec = record("legacy", b"root");
    let image_manifest = manifest(b"legacy-manifest");
    store.ref_put(&rec).unwrap();
    store.image_config_put("legacy", b"legacy-config").unwrap();
    store.image_manifest_put("legacy", &image_manifest).unwrap();
    assert_eq!(store.ref_get("legacy").unwrap(), Some(rec.clone()));
    assert_eq!(
        store.image_ref_get("legacy").unwrap(),
        Some(ImageRef {
            record: rec,
            config: Some(b"legacy-config".to_vec()),
            manifest: Some(image_manifest),
        })
    );
}

#[test]
fn failed_prepared_publication_keeps_prior_envelope_visible() {
    let (_dir, store) = tmp_store();
    let previous = record("image", b"previous");
    store
        .publish_image_ref(&previous, Some(b"old-config"), None)
        .unwrap();
    let next = record("image", b"next");
    let missing = PreparedImageRef {
        config: Some(Digest::of_bytes(b"not-in-store")),
        manifest: None,
    };
    assert!(store.publish_prepared_image_ref(&next, missing).is_err());
    let got = store.image_ref_get("image").unwrap().unwrap();
    assert_eq!(got.record, previous);
    assert_eq!(got.config, Some(b"old-config".to_vec()));
}

#[test]
fn concurrent_tuple_reads_never_observe_mixed_publication() {
    let (_dir, store) = tmp_store();
    let root = store.root().to_path_buf();
    let first = (
        record("image", b"one"),
        b"config-one".to_vec(),
        manifest(b"manifest-one"),
    );
    let second = (
        record("image", b"two"),
        b"config-two".to_vec(),
        manifest(b"manifest-two"),
    );
    store
        .publish_image_ref(&first.0, Some(&first.1), Some(&first.2))
        .unwrap();
    let start = Arc::new(Barrier::new(2));
    let writer_start = Arc::clone(&start);
    let writer_first = first.clone();
    let writer_second = second.clone();
    let writer = thread::spawn(move || {
        let store = Store::open(root).unwrap();
        writer_start.wait();
        for i in 0..100 {
            let tuple = if i % 2 == 0 {
                &writer_second
            } else {
                &writer_first
            };
            store
                .publish_image_ref(&tuple.0, Some(&tuple.1), Some(&tuple.2))
                .unwrap();
        }
    });
    start.wait();
    for _ in 0..100 {
        let got = store.image_ref_get("image").unwrap().unwrap();
        let is_first = got.record == first.0
            && got.config == Some(first.1.clone())
            && got.manifest == Some(first.2.clone());
        let is_second = got.record == second.0
            && got.config == Some(second.1.clone())
            && got.manifest == Some(second.2.clone());
        assert!(
            is_first || is_second,
            "mixed or partial image tuple: {got:?}"
        );
    }
    writer.join().unwrap();
}
