# R1 Linux x86_64 Receipt

**Status:** Linux verified for immutable source and workflow revision
`d09f6c3cf603269aff9dd9d95b94902286695449`, version `0.1.0`.
This documentation was recorded after candidate verification; its documentation
commit is not itself qualified. Authority: [#187 re-freeze][freeze]; requirements:
[R1 plan](../../unix-first-go-live.md#r1-linux-oci-verification).

## Evidence and identity

- [Run 36728965586][run], attempt 1, `workflow_dispatch`, completed successfully
  on 2026-09-30; [R1 job 109933150414][job] completed at `14:27:08Z`.
- [R1 artifact 11102919978][artifact], created `2026-09-30T14:27:05Z`.
  Raw receipt: `r1-receipt/R1-linux-x86_64.json`; exact argv/exit codes:
  `r1-receipt/commands.jsonl`; witness outcomes: `r1-receipt/witnesses.jsonl`.
  Full outputs: `r1-receipt/oci-full.log`, `r1-receipt/package.log`, and each
  `r1-receipt/<exact test basename>.log` listed by the raw receipt's `log` fields.
- GitHub-hosted runner ID `1000043335`, Ubuntu `24.04.5` LTS,
  `Linux 6.17.0-1022-azure x86_64`; runner image `20260927.320.1`.
  Rust: `rustc 1.96.0 (ac68faa20 2026-05-25)`.
  `LIGHTR_NET_TESTS=1`, `RUSTFLAGS="-D warnings"`; network pull was enabled.
- Artifact: `packaging/dist/lightr-0.1.0-linux-x86_64.tar.gz` with matching
  `.sha256`, exactly one `<hash>  <filename>\n` record.
  Tarball SHA-256: `4ac9e1014a3f6d889c9d33b6b01e880fccff518024b5dce13136ec0a5b8ab4b1`.
  Binary SHA-256: `e3bcabd0391a7c3857998e1aed4cc26be6cec807bbf6dbbc3d8a07975e916942`.
  Archive contains only regular executable `lightr`, mode `0755`, ELF64 x86_64.
  Signing/notarization: **n/a (Linux)**.
- Downloaded R1 ZIP SHA-256 matches API metadata:
  `89cfa3d576d543c26ca3c47d0adce0247118349a667a571f677740039fd7f881`.

## Exact executed commands and outcomes

From the frozen candidate checkout, the plan's OCI command used `--locked`.
Every command below exited `0`; full OCI suite: **86 passed, 0 failed, 0 ignored**.
Each of the eight `--exact` commands ran **1 passed, 0 failed, 0 ignored**.
These bind confined traversal/opaque links, whiteouts/hardlinks, import/hydrate,
save/load, network pull, identity-checked cleanup, and per-ref publication.

```bash
cargo +1.96.0 test --locked -p lightr-oci --lib
cargo +1.96.0 test --locked -p lightr-oci --lib -- oci::tests::integrity_tests::test_write_through_symlink_component_rejects_import_without_ref --exact
cargo +1.96.0 test --locked -p lightr-store --lib -- store::image_ref::tests::concurrent_tuple_reads_never_observe_mixed_publication --exact
cargo +1.96.0 test --locked -p lightr-oci --lib -- oci::tests::import_tests::test_import_layout_two_layers_whiteout_and_hydrate --exact
cargo +1.96.0 test --locked -p lightr-oci --lib -- oci::load::load_tests::save_load_roundtrip_lossless --exact
cargo +1.96.0 test --locked -p lightr-oci --lib -- oci::tests::pull_tests::test_pull_alpine_network_gated --exact
cargo +1.96.0 test --locked -p lightr-oci --lib -- oci::tests::import_tests::test_path_escape_rejects_import_without_ref --exact
cargo +1.96.0 test --locked -p lightr-oci --lib -- oci::layer::unix::tests::cleanup_removes_owned_stage_before_drop --exact
cargo +1.96.0 test --locked -p lightr-oci --lib -- oci::layer::unix::tests::cleanup_rejects_replaced_stage_and_preserves_both_trees --exact
bash packaging/release.sh
```

Checksum command, cwd `packaging/dist`:

```bash
sha256sum -c lightr-0.1.0-linux-x86_64.tar.gz.sha256
```

Output: `lightr-0.1.0-linux-x86_64.tar.gz: OK`. Rejection witnesses marked
`negative_control: true` in raw JSON: symlink-component write, path escape, and
replaced-stage cleanup. Import controls rejected publication; cleanup preserved
both trees after stage replacement.

## Independent checksum controls

Downloaded API metadata, ZIP bytes, receipts, and job logs were reviewed in
`/var/folders/lt/z11pyzhj0m17vn798jkk69hh0000gn/T/opencode/run36728965586-review.aMhF39`.
Local `verification.log` lines 21-26 record these exact argv commands in
`negative-control/`, first against a valid tarball copy, then against that copy
with byte 100 XORed by 1 (original download preserved):

```bash
/usr/bin/shasum -a 256 -c lightr-0.1.0-linux-x86_64.tar.gz.sha256
/usr/local/bin/sha256sum -c lightr-0.1.0-linux-x86_64.tar.gz.sha256
```

Both valid-copy controls exited `0` (`: OK`); both corrupted-copy controls exited
`1` (`: FAILED`, one computed checksum mismatch). Corrupted-copy SHA-256:
`245a0b705d5e7ce088e3b693629f6da9dd7e29f906f3ea23986a1b46792565b1`.
These are local review controls, not additional candidate workflow commands.

R1 is Linux-only evidence; R2/R3 macOS and R4 remain blocked. R3 overall is not
done; owner `G-PUBLISH` remains pending. No hardware-performance claim follows.

[freeze]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5913266196
[run]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36728965586
[job]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36728965586/job/109933150414
[artifact]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36728965586/artifacts/11102919978
