//! Integrity, whiteout ordering, and hardlink tests.

use super::{make_layer, make_layout, tmp_store_and_home, ENV_LOCK};
use crate::oci::import::import_layout;
use crate::oci::util::{host_arch, path_is_safe, sha256_hex_of, verify_sha256};
use lightr_core::LightrError;
use std::{fs, path::Path};
use tempfile::TempDir;

#[test]
fn test_path_is_safe() {
    assert!(path_is_safe(Path::new("a/b/c")));
    assert!(path_is_safe(Path::new("./a/b")));
    assert!(!path_is_safe(Path::new("../evil")));
    assert!(!path_is_safe(Path::new("/etc/passwd")));
    assert!(!path_is_safe(Path::new("a/../../etc")));
}

fn make_symlink_layer(target: &str, write_through_link: bool) -> Vec<u8> {
    let encoder = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::fast());
    let mut tar = tar::Builder::new(encoder);

    let content = b"target";
    let mut file = tar::Header::new_gnu();
    file.set_path("target").unwrap();
    file.set_mode(0o644);
    file.set_size(content.len() as u64);
    file.set_entry_type(tar::EntryType::Regular);
    file.set_cksum();
    tar.append(&file, &content[..]).unwrap();

    let mut link = tar::Header::new_gnu();
    link.set_path("link").unwrap();
    link.set_mode(0o777);
    link.set_size(0);
    link.set_entry_type(tar::EntryType::Symlink);
    link.set_link_name(target).unwrap();
    link.set_cksum();
    tar.append(&link, &b""[..]).unwrap();

    if write_through_link {
        let payload = b"must not follow symlink";
        let mut file = tar::Header::new_gnu();
        file.set_path("link/payload").unwrap();
        file.set_mode(0o644);
        file.set_size(payload.len() as u64);
        file.set_entry_type(tar::EntryType::Regular);
        file.set_cksum();
        tar.append(&file, &payload[..]).unwrap();
    }

    tar.into_inner().unwrap().finish().unwrap()
}

#[cfg(unix)]
#[test]
fn test_absolute_and_parent_symlink_targets_are_opaque() {
    let _guard = ENV_LOCK.lock().unwrap_or_else(|p| p.into_inner());
    for (suffix, target) in [("absolute", "/etc/passwd"), ("parent", "../escape")] {
        let tmp = TempDir::new().unwrap();
        let (_home, store) = tmp_store_and_home();
        let layout_dir = make_layout(tmp.path(), &[make_symlink_layer(target, false)]);
        let name = format!("symlink-{suffix}");
        import_layout(&layout_dir, &store, &name).unwrap();
        let hydrate = tmp.path().join(format!("hydrate-{suffix}"));
        fs::create_dir(&hydrate).unwrap();
        lightr_index::hydrate(&hydrate, &store, &name).unwrap();
        assert_eq!(
            fs::read_link(hydrate.join("link")).unwrap(),
            Path::new(target)
        );
    }
}

#[test]
fn test_write_through_symlink_component_rejects_import_without_ref() {
    let _guard = ENV_LOCK.lock().unwrap_or_else(|p| p.into_inner());
    let tmp = TempDir::new().unwrap();
    let (_home, store) = tmp_store_and_home();
    let sentinel = tmp.path().join("outside-sentinel");
    fs::write(&sentinel, b"outside remains").unwrap();
    let layout_dir = make_layout(
        tmp.path(),
        &[make_symlink_layer(sentinel.to_str().unwrap(), true)],
    );
    let result = import_layout(&layout_dir, &store, "symlink-component");

    assert!(
        matches!(&result, Err(LightrError::InvalidManifest(_))),
        "write through symlink component must reject import, got: {:?}",
        result.as_ref().err()
    );
    assert!(
        store.ref_get("symlink-component").unwrap().is_none(),
        "rejected symlink-component import must not publish ref"
    );
    assert_eq!(fs::read(&sentinel).unwrap(), b"outside remains");
}

#[cfg(unix)]
#[test]
fn test_relative_symlink_imports() {
    let _guard = ENV_LOCK.lock().unwrap_or_else(|p| p.into_inner());
    let tmp = TempDir::new().unwrap();
    let (_home, store) = tmp_store_and_home();
    let layout_dir = make_layout(tmp.path(), &[make_symlink_layer("target", false)]);
    import_layout(&layout_dir, &store, "relative-symlink").unwrap();

    let hydrate_dir = tmp.path().join("hydrated-relative-symlink");
    fs::create_dir_all(&hydrate_dir).unwrap();
    lightr_index::hydrate(&hydrate_dir, &store, "relative-symlink").unwrap();
    assert_eq!(
        fs::read_link(hydrate_dir.join("link")).unwrap(),
        Path::new("target")
    );
}

// ── FIX 1: sha256 integrity tests ─────────────────────────────────────────

/// Corrupt a layer blob after writing the layout → import must fail with
/// Integrity error (sha256 mismatch).
#[test]
fn test_integrity_corrupt_layer_fails() {
    let _guard = ENV_LOCK.lock().unwrap_or_else(|p| p.into_inner());
    let tmp = TempDir::new().unwrap();
    let (_home, store) = tmp_store_and_home();

    let layer = make_layer(&[("hello.txt", b"hello", 0o644)]);
    let layout_dir = make_layout(tmp.path(), &[layer]);

    // Corrupt one of the layer blobs in blobs/sha256/
    let blobs_dir = layout_dir.join("blobs/sha256");
    let mut entries: Vec<_> = fs::read_dir(&blobs_dir)
        .unwrap()
        .filter_map(|e| e.ok())
        .filter(|e| e.path().is_file())
        .collect();
    // The layout has manifest blob + 1 layer blob; corrupt the smaller one
    // that is likely the layer (manifest is JSON, layer is gz tar).
    entries.sort_by_key(|e| e.metadata().map(|m| m.len()).unwrap_or(0));
    // Corrupt the layer blob (smallest file, index 0 after sort)
    let corrupt_path = entries[0].path();
    let mut data = fs::read(&corrupt_path).unwrap();
    // Flip a byte in the middle
    let mid = data.len() / 2;
    data[mid] ^= 0xFF;
    fs::write(&corrupt_path, &data).unwrap();

    let result = import_layout(&layout_dir, &store, "corrupt-test");
    assert!(
        matches!(result, Err(LightrError::Integrity { .. })),
        "corrupt blob must produce Integrity error; got: {:?}",
        result.err()
    );
}

/// Verify that `verify_sha256` helper correctly identifies corruption.
#[test]
fn test_verify_sha256_helper() {
    let data = b"test content";
    let good_hex = sha256_hex_of(data);
    assert!(verify_sha256(data, &good_hex).is_ok());

    // Wrong hex → Integrity error
    let bad_hex = "0".repeat(64);
    let err = verify_sha256(data, &bad_hex).unwrap_err();
    assert!(matches!(err, LightrError::Integrity { .. }));
}

fn rewrite_layout_manifest(layout: &Path, manifest: serde_json::Value) {
    let bytes = serde_json::to_vec(&manifest).unwrap();
    let hex = sha256_hex_of(&bytes);
    fs::write(layout.join("blobs/sha256").join(&hex), bytes).unwrap();
    fs::write(
        layout.join("index.json"),
        serde_json::to_vec(&serde_json::json!({
            "schemaVersion": 2,
            "manifests": [{
                "digest": format!("sha256:{hex}"),
                "platform": {"os": "linux", "architecture": host_arch()}
            }]
        }))
        .unwrap(),
    )
    .unwrap();
}

/// Config is required and validated before snapshot. Every rejection leaves no ref.
#[test]
fn test_oci_config_rejections_publish_no_ref() {
    let _guard = ENV_LOCK.lock().unwrap_or_else(|p| p.into_inner());
    for case in ["missing", "malformed", "unsupported", "mismatch"] {
        let tmp = TempDir::new().unwrap();
        let (_home, store) = tmp_store_and_home();
        let layout = make_layout(tmp.path(), &[make_layer(&[("x", b"x", 0o644)])]);
        let blobs = layout.join("blobs/sha256");
        let index: serde_json::Value =
            serde_json::from_slice(&fs::read(layout.join("index.json")).unwrap()).unwrap();
        let manifest_hex = index["manifests"][0]["digest"]
            .as_str()
            .unwrap()
            .strip_prefix("sha256:")
            .unwrap();
        let mut manifest: serde_json::Value =
            serde_json::from_slice(&fs::read(blobs.join(manifest_hex)).unwrap()).unwrap();
        let old_hex = manifest["config"]["digest"]
            .as_str()
            .unwrap()
            .strip_prefix("sha256:")
            .unwrap()
            .to_string();

        match case {
            "missing" => fs::remove_file(blobs.join(old_hex)).unwrap(),
            "malformed" => {
                let bytes = b"[]";
                let hex = sha256_hex_of(bytes);
                fs::write(blobs.join(&hex), bytes).unwrap();
                manifest["config"]["digest"] = serde_json::json!(format!("sha256:{hex}"));
                manifest["config"]["size"] = serde_json::json!(bytes.len());
                rewrite_layout_manifest(&layout, manifest);
            }
            "unsupported" => {
                manifest["config"]["digest"] = serde_json::json!("sha512:deadbeef");
                rewrite_layout_manifest(&layout, manifest);
            }
            "mismatch" => fs::write(blobs.join(old_hex), b"{\"os\":\"linux\"}").unwrap(),
            _ => unreachable!(),
        }

        let name = format!("config-{case}");
        let result = import_layout(&layout, &store, &name);
        assert!(
            matches!(
                result,
                Err(LightrError::InvalidManifest(_)) | Err(LightrError::Integrity { .. })
            ),
            "{case} config must fail"
        );
        assert!(
            store.ref_get(&name).unwrap().is_none(),
            "{case} config published ref"
        );
    }
}

/// Index selection accepts only native Linux descriptor, never first descriptor.
#[test]
fn test_oci_layout_rejects_non_host_platform_without_ref() {
    let _guard = ENV_LOCK.lock().unwrap_or_else(|p| p.into_inner());
    let tmp = TempDir::new().unwrap();
    let (_home, store) = tmp_store_and_home();
    let layout = make_layout(tmp.path(), &[make_layer(&[("x", b"x", 0o644)])]);
    let index: serde_json::Value =
        serde_json::from_slice(&fs::read(layout.join("index.json")).unwrap()).unwrap();
    let digest = index["manifests"][0]["digest"].clone();
    let other = if host_arch() == "amd64" {
        "arm64"
    } else {
        "amd64"
    };
    fs::write(
        layout.join("index.json"),
        serde_json::to_vec(&serde_json::json!({
            "schemaVersion": 2,
            "manifests": [{"digest": digest, "platform": {"os": "linux", "architecture": other}}]
        }))
        .unwrap(),
    )
    .unwrap();

    let result = import_layout(&layout, &store, "wrong-platform");
    assert!(matches!(result, Err(LightrError::InvalidManifest(_))));
    assert!(store.ref_get("wrong-platform").unwrap().is_none());
}

// ── FIX 3/4: whiteout ordering tests ─────────────────────────────────────

/// Same-layer add-then-whiteout: the file must be absent (whiteouts win).
#[test]
fn test_intra_layer_whiteout_ordering() {
    let _guard = ENV_LOCK.lock().unwrap_or_else(|p| p.into_inner());
    let tmp = TempDir::new().unwrap();
    let (_home, store) = tmp_store_and_home();

    // Single layer: add x/f AND add x/.wh.f (whiteout of x/f)
    // Per OCI parent-ref semantics our impl documents: whiteouts are
    // processed before additions within a layer, so x/f ends up absent.
    let layer = make_layer(&[
        ("x/", &[], 0o755),
        ("x/f", b"should be absent", 0o644),
        ("x/.wh.f", &[], 0o644), // whiteout of x/f
    ]);

    let layout_dir = make_layout(tmp.path(), &[layer]);
    let report = import_layout(&layout_dir, &store, "wo-order-test").unwrap();
    assert_eq!(report.layers, 1);

    let hydrate_dir = tmp.path().join("hydrated-wo");
    fs::create_dir_all(&hydrate_dir).unwrap();
    lightr_index::hydrate(&hydrate_dir, &store, "wo-order-test").unwrap();

    assert!(
        !hydrate_dir.join("x/f").exists(),
        "x/f must be absent: whiteout in same layer applies (whiteouts execute before additions)"
    );
}

/// Opaque whiteout clears dir from prior layer; new dir created by opaque.
#[test]
fn test_opaque_whiteout_clears_prior_layer() {
    let _guard = ENV_LOCK.lock().unwrap_or_else(|p| p.into_inner());
    let tmp = TempDir::new().unwrap();
    let (_home, store) = tmp_store_and_home();

    // Layer 1: create dir and file
    let layer1 = make_layer(&[("dir/", &[], 0o755), ("dir/old.txt", b"old", 0o644)]);
    // Layer 2: opaque whiteout of dir, then add a new file in dir
    let layer2 = make_layer(&[
        ("dir/.wh..wh..opq", &[], 0o644), // opaque whiteout
        ("dir/new.txt", b"new", 0o644),
    ]);

    let layout_dir = make_layout(tmp.path(), &[layer1, layer2]);
    import_layout(&layout_dir, &store, "opaque-test").unwrap();

    let hydrate_dir = tmp.path().join("hydrated-opaque");
    fs::create_dir_all(&hydrate_dir).unwrap();
    lightr_index::hydrate(&hydrate_dir, &store, "opaque-test").unwrap();

    assert!(
        !hydrate_dir.join("dir/old.txt").exists(),
        "dir/old.txt must be absent after opaque whiteout"
    );
    assert!(
        hydrate_dir.join("dir/new.txt").exists(),
        "dir/new.txt must be present after opaque whiteout"
    );
}

// ── FIX 5: hardlink tests ─────────────────────────────────────────────────

/// Hardlink to a present target: both files have identical content.
#[test]
fn test_hardlink_present_target() {
    let _guard = ENV_LOCK.lock().unwrap_or_else(|p| p.into_inner());
    let tmp = TempDir::new().unwrap();
    let (_home, store) = tmp_store_and_home();

    // Build a layer gz with a regular file then a hardlink pointing to it.
    let layer_bytes = {
        let gz_buf = Vec::new();
        let encoder = flate2::write::GzEncoder::new(gz_buf, flate2::Compression::fast());
        let mut tar_b = tar::Builder::new(encoder);

        // Regular file: "original.txt"
        let content = b"link content";
        let mut rh = tar::Header::new_gnu();
        rh.set_path("original.txt").unwrap();
        rh.set_mode(0o644);
        rh.set_size(content.len() as u64);
        rh.set_entry_type(tar::EntryType::Regular);
        rh.set_cksum();
        tar_b.append(&rh, &content[..]).unwrap();

        // Hardlink: "copy.txt" → "original.txt"
        let mut lh = tar::Header::new_gnu();
        lh.set_path("copy.txt").unwrap();
        lh.set_mode(0o644);
        lh.set_size(0);
        lh.set_entry_type(tar::EntryType::Link);
        lh.set_link_name("original.txt").unwrap();
        lh.set_cksum();
        tar_b.append(&lh, &b""[..]).unwrap();

        tar_b.into_inner().unwrap().finish().unwrap()
    };

    let layout_dir = make_layout(tmp.path(), &[layer_bytes]);
    import_layout(&layout_dir, &store, "hardlink-test").unwrap();

    let hydrate_dir = tmp.path().join("hydrated-hl");
    fs::create_dir_all(&hydrate_dir).unwrap();
    lightr_index::hydrate(&hydrate_dir, &store, "hardlink-test").unwrap();

    let orig = hydrate_dir.join("original.txt");
    let copy = hydrate_dir.join("copy.txt");
    assert!(orig.exists(), "original.txt must exist");
    assert!(copy.exists(), "copy.txt (hardlink) must exist");
    assert_eq!(
        fs::read(&orig).unwrap(),
        fs::read(&copy).unwrap(),
        "hardlinked files must have identical content"
    );
}

/// Dangling hardlink → import must fail (fail-closed).
#[test]
fn test_hardlink_dangling_fails() {
    let _guard = ENV_LOCK.lock().unwrap_or_else(|p| p.into_inner());
    let tmp = TempDir::new().unwrap();
    let (_home, store) = tmp_store_and_home();

    let layer_bytes = {
        let gz_buf = Vec::new();
        let encoder = flate2::write::GzEncoder::new(gz_buf, flate2::Compression::fast());
        let mut tar_b = tar::Builder::new(encoder);

        // Hardlink that points to a non-existent target
        let mut lh = tar::Header::new_gnu();
        lh.set_path("dangling.txt").unwrap();
        lh.set_mode(0o644);
        lh.set_size(0);
        lh.set_entry_type(tar::EntryType::Link);
        lh.set_link_name("ghost.txt").unwrap();
        lh.set_cksum();
        tar_b.append(&lh, &b""[..]).unwrap();

        tar_b.into_inner().unwrap().finish().unwrap()
    };

    let layout_dir = make_layout(tmp.path(), &[layer_bytes]);
    let result = import_layout(&layout_dir, &store, "dangling-hl");

    assert!(
        matches!(result, Err(LightrError::InvalidManifest(_))),
        "dangling hardlink must return InvalidManifest; got: {:?}",
        result.err()
    );
    if let Err(LightrError::InvalidManifest(msg)) = result {
        assert!(
            msg.contains("hardlink target not found"),
            "error must mention 'hardlink target not found'; got: {msg}"
        );
    }
}
