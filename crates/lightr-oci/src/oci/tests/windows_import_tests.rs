//! ADR-0021 Windows OCI layer-import rejection tests.

use super::{make_layer, make_layout, make_modern_docker_save, tmp_store_and_home};
use crate::oci::{
    import::{import_layout, preflight_oci_layer_import, WINDOWS_LAYER_IMPORT_UNSUPPORTED},
    load::load,
    pull::pull,
};
use lightr_core::{LightrError, Result};
use std::fs;

fn import_error<T>(result: Result<T>) -> LightrError {
    match result {
        Err(error) => error,
        Ok(_) => panic!("OCI layer import unexpectedly succeeded"),
    }
}

fn assert_windows_unsupported(error: LightrError) {
    assert!(
        matches!(error, LightrError::Unsupported(ref message) if message == WINDOWS_LAYER_IMPORT_UNSUPPORTED),
        "OCI layer import must fail with ADR-0021 Unsupported, got {error:?}"
    );
}

/// Every layer-import entry point rejects before input reads, staging, or ref
/// publication. Missing input and invalid ref prove no route falls through to
/// its normal validation or network path.
#[test]
fn layer_import_routes_reject_before_stage_or_ref_mutation() {
    let (home, store) = tmp_store_and_home();
    let before = store.list_refs().unwrap();
    let layer = make_layer(&[("file", b"contents", 0o644)]);
    let layout = make_layout(home.path(), std::slice::from_ref(&layer));
    let docker_save = home.path().join("image.tar");
    fs::write(&docker_save, make_modern_docker_save(&layer, false)).unwrap();
    let missing = home.path().join("missing.tar");

    assert_windows_unsupported(import_error(import_layout(&layout, &store, "layout")));
    assert_windows_unsupported(import_error(import_layout(
        &docker_save,
        &store,
        "docker-save",
    )));
    assert_windows_unsupported(import_error(load(Some(&missing), &store)));
    assert_windows_unsupported(import_error(pull("not a valid image ref", &store, "pull")));
    assert_eq!(
        store.list_refs().unwrap(),
        before,
        "no route may publish a ref"
    );
}

#[test]
fn preflight_returns_exact_unsupported_without_a_store() {
    assert_windows_unsupported(import_error(preflight_oci_layer_import()));
}
