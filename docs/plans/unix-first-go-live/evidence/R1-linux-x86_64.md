# R1 Linux x86_64 Receipt

**Status:** Linux verified for immutable source and workflow revision
`ca88415b5e34cfefa4fef1eae9ea13511c30f718`, version `0.1.1`.
This documentation was recorded after candidate verification; its documentation
commit is not itself qualified. Authority: [#187 re-freeze][freeze]; requirements:
[R1 plan](../../unix-first-go-live.md#r1-linux-oci-verification).

## Evidence and identity

- [Run 36823107072][run], attempt 1, `workflow_dispatch`, completed successfully
  on 2026-10-01; [R1 job 110242756699][job] completed at `06:09:47Z`.
- [R1 artifact 11144330730][artifact], created `2026-10-01T06:09:45Z`;
  API retention expires `2026-10-31T06:09:45Z` (30 days).
  Raw receipt: `r1-receipt/R1-linux-x86_64.json`; exact argv/exit codes:
  `r1-receipt/commands.jsonl`; witness outcomes: `r1-receipt/witnesses.jsonl`.
  Full outputs: `r1-receipt/oci-full.log`, `r1-receipt/package.log`, and each
  `r1-receipt/<exact test basename>.log` listed by the raw receipt's `log` fields.
- GitHub-hosted runner ID `1000044017`, Ubuntu `24.04.5` LTS,
  `Linux 6.17.0-1022-azure x86_64`; runner image `20260927.320.1`.
  Rust: `rustc 1.96.0 (ac68faa20 2026-05-25)`.
  `LIGHTR_NET_TESTS=1`, `RUSTFLAGS="-D warnings"`; network pull was enabled.
- Artifact: `packaging/dist/lightr-0.1.1-linux-x86_64.tar.gz` with matching
  `.sha256`, exactly one `<hash>  <filename>\n` record.
  Tarball SHA-256: `deb3ad351d248187a8577642f8cce1023e1c6b70091b059e3cdf268d2ff33616`.
  Binary SHA-256: `d6f6a4e496554f28378f3e324bdb7ef5dc85100def883cabbf55a562cd3fd568`.
  Archive contains only regular executable `lightr`, mode `0755`, ELF64 x86_64.
  Signing/notarization: **n/a (Linux)**.
- Downloaded R1 ZIP SHA-256 matches API metadata:
  `8e89ce60ddea70b25e6ba388b23c12548fe2ae755543db88aface54a89dd9dcb`.
  [Raw ZIP API][zip]; receipt JSON SHA-256:
  `3db5398f6192fc3af58744b6571fc3bb9b8c1fa47699df524aef2d6c68808348`.

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
`/var/folders/lt/z11pyzhj0m17vn798jkk69hh0000gn/T/opencode/lightr-receipt-36823107072.VIhsrg`.
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
Corrupted tarball SHA-256: `b495b774da12cd1f6e4c75f0efda8926a6a65482a46b65e6fbe57fbda130dd81`.
Review also rejected zero-pass/missing-name witness transcripts and skipped API
step controls (`verification.json`). These are review controls, not workflow runs.

R1 is Linux-only evidence. [Hosted macOS partial evidence](R2-macos-arm64-hosted.md)
passed; **VZ NOT EXECUTED; full R2 and overall R3 incomplete**. Public `release.yml`
outputs are not qualified; owner `G-PUBLISH` pending, `publish = false`.
Previous receipts remain historical run links in [R0](R0.md); no performance claim.

[freeze]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5925747505
[run]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36823107072
[job]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36823107072/job/110242756699
[artifact]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36823107072/artifacts/11144330730
[zip]: https://api.github.com/repos/gmhelmold/hugr-lightr/actions/artifacts/11144330730/zip
