# Runbook - Windows OCI layer import

## Current behavior

Windows OCI layer import is intentionally unavailable under ADR-0021. `oci load`,
direct OCI-layout or docker-save import, and registry `oci pull` return:

```
unsupported: OCI layer import is unsupported on Windows (ADR-0021)
```

Each route rejects before `Store::open`, input read, staging-directory creation,
layer download, image-metadata retention, or ref publication. No symlink,
hardlink, copy, or skip fallback is permitted.

## CI evidence

Native Windows CI runs:

```sh
cargo test -p lightr-oci --lib windows_import_tests
cargo test -p lightr-acceptance --test windows_oci_import
```

Tests cover OCI layout, docker-save, `oci load`, registry pull, and caller
preflight. CLI test verifies exact error and that missing `LIGHTR_HOME` remains
absent. This does not qualify native Windows layer application; qualification
remains future work under ADR-0021.
