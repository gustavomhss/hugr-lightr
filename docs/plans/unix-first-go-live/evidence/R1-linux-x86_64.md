# R1 Linux x86_64 Receipt

**Status:** Linux verified for immutable source and workflow revision
`47f02795d0884956c4755254b5f6fc377a5938b5`, version `0.1.1`.
This documentation was recorded after candidate verification; its documentation
commit is not itself qualified. Authority: [#187 re-freeze][freeze]; requirements:
[R1 plan](../../unix-first-go-live.md#r1-linux-oci-verification).

## Evidence and identity

- [Run 36845506826][run], attempt 1, `workflow_dispatch`, completed successfully
  on 2026-10-01; [R1 job 110314563642][job] completed at `09:55:02Z`.
- [R1 artifact 11153018739][artifact], created `2026-10-01T09:55:00Z`;
  API retention expires `2026-10-31T09:55:00Z` (30 days).
  Raw receipt: `r1-receipt/R1-linux-x86_64.json`; exact argv/exit codes:
  `r1-receipt/commands.jsonl`; witness outcomes: `r1-receipt/witnesses.jsonl`.
  Full outputs: `r1-receipt/oci-full.log`, `r1-receipt/package.log`, and each
  `r1-receipt/<exact test basename>.log` listed by the raw receipt's `log` fields.
- GitHub-hosted runner ID `1000044114`, Ubuntu `24.04.5` LTS,
  `Linux 6.17.0-1022-azure x86_64`; runner image `20260920.314.1`.
  Rust: `rustc 1.96.0 (ac68faa20 2026-05-25)`.
  `LIGHTR_NET_TESTS=1`, `RUSTFLAGS="-D warnings"`; network pull was enabled.
- Artifact: `packaging/dist/lightr-0.1.1-linux-x86_64.tar.gz` with matching
  `.sha256`, exactly one `<hash>  <filename>\n` record.
  Tarball SHA-256: `e217569cf96e349fdeeea5bdde657738be7cba544557189517f45df9946a070a`.
  Binary SHA-256: `d237fb33a067261396e0b9e195fc4804ad492b75fb5b3356476e0f1548449352`.
  Archive contains only regular executable `lightr`, mode `0755`, ELF64 x86_64.
  Signing/notarization: **n/a (Linux)**.
- Downloaded R1 ZIP SHA-256 matches API metadata:
  `8aedfdc1d497d4e9420a24917fd5ede09266f0fd07a3fb03ae74af362470b62b`.
  [Raw ZIP API][zip]; receipt JSON SHA-256:
  `07dae6f266fb9dbc4b242fee6ca032d4c1ee4c0b65c4394d10378ea9662bb9eb`.

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
sha256sum -c lightr-0.1.1-linux-x86_64.tar.gz.sha256
```

Output: `lightr-0.1.1-linux-x86_64.tar.gz: OK`. Rejection witnesses marked
`negative_control: true` in raw JSON: symlink-component write, path escape, and
replaced-stage cleanup. Import controls rejected publication; cleanup preserved
both trees after stage replacement.

## Independent checksum controls

Independent review bundle:
`/var/folders/lt/z11pyzhj0m17vn798jkk69hh0000gn/T/opencode/lightr-receipt-36845506826.LxtarH`.
`calibration.json` records exact argv/results; `evidence-manifest.json` binds bytes.
Valid ZIPs (cwd bundle root) and tarball (cwd `packaging/dist`) passed:

```bash
sha256sum -c zip-checksums.txt
shasum -a 256 -c zip-checksums.txt
sha256sum -c lightr-0.1.1-linux-x86_64.tar.gz.sha256
shasum -a 256 -c lightr-0.1.1-linux-x86_64.tar.gz.sha256
```

All exited `0` (`: OK`). In `corrupt-controls/`, both ZIP checkers used
`zip-checksum.txt`; both tarball checkers used the same tarball argv above.
All corrupted-copy checks exited `1` (`: FAILED`, one computed checksum mismatch).
Corrupted tarball SHA-256: `b7e9abd9a6555c4ced11bd2a62fadf064aa09c0ea5d88bc7318a7205676dbfb6`.
Review also rejected zero-pass/missing-name witness transcripts and skipped API
step controls (`verification.json`). These are review controls, not workflow runs.

R1 is Linux-only evidence. [Hosted macOS partial evidence](R2-macos-arm64-hosted.md)
passed; **VZ NOT EXECUTED/unvalidated; full R2 incomplete**. Raw hosted R3 remains
incomplete; [owner policy](R0-0.1.1-owner-waivers.md) accepts candidate R3 for 0.1.1 only.
Public `release.yml` outputs unqualified; `G-PUBLISH` pending, `publish = true` prepared.
Previous receipts remain historical run links in [R0](R0.md); no performance claim.

[freeze]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5928998891
[run]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36845506826
[job]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36845506826/job/110314563642
[artifact]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36845506826/artifacts/11153018739
[zip]: https://api.github.com/repos/gmhelmold/hugr-lightr/actions/artifacts/11153018739/zip
