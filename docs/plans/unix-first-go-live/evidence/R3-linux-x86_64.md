# R3 Linux x86_64 Clean-Install Receipt

**Status:** Linux verified; candidate R3 accepted by [0.1.1 owner policy](R0-0.1.1-owner-waivers.md).
Immutable source/workflow revision: `47f02795d0884956c4755254b5f6fc377a5938b5`, version `0.1.1`.
This documentation was recorded after candidate verification; its documentation
commit is not itself qualified. Authority: [#187 re-freeze][freeze]; requirements:
[R3 plan](../../unix-first-go-live.md#r3-clean-machine-linux-and-macos-arm64-install-checksum-smoke).

## Evidence and clean environment

- [Run 36845506826][run], attempt 1; [R3 job 110315496820][job] completed
  successfully on `2026-10-01T09:55:10Z`.
- [R3 receipt artifact 11153158044][receipt], created `2026-10-01T09:55:08Z`:
  `R3-linux-x86_64.json` and `commands.jsonl` retain exact argv, cwd, exit codes,
  and full checksum/version/help outputs, including the entire help text.
  Downloaded ZIP SHA-256 equals API digest: `9f9c0e1fa8c914d919ef9a80d30c8515bebe69a40fab8d2128513734f754c94e`.
  [Raw ZIP API][zip]; retention expires `2026-10-31T09:55:07Z` (30 days).
  Receipt JSON SHA-256: `d7423216eb87897676da09884b297cfc121f5198a55d087e13e9343b9a8c3cd7`.
- Distinct GitHub-hosted runner ID `1000044117` (R1: `1000044114`), Ubuntu
  `24.04.5` LTS, `Linux 6.17.0-1022-azure x86_64`, image `20260920.314.1`.
  Job performed only artifact download/install verification and receipt upload;
  no source checkout or build. Job log records fresh `HOME="$(mktemp -d)"`,
  absent `$HOME/.local/bin/lightr`, and cleanup assertion `test ! -e "$HOME"`.
- Immutable install source: [R1 artifact 11153018739][source], not a public
  release asset. Downloaded `packaging/dist/lightr-0.1.1-linux-x86_64.tar.gz` and
  matching `.sha256`; candidate/workflow identities matched [R1](R1-linux-x86_64.md).
  Tarball SHA-256: `e217569cf96e349fdeeea5bdde657738be7cba544557189517f45df9946a070a`.
  Installed binary SHA-256: `d237fb33a067261396e0b9e195fc4804ad492b75fb5b3356476e0f1548449352`.
  Job asserted archive-only `lightr`, extracted regular/non-symlink file, and
  equality of archive and installed binary hashes. Signing: **n/a (Linux)**.

## Exact commands and outcomes

`ARTIFACT=lightr-0.1.1-linux-x86_64.tar.gz`; fresh
`HOME=/tmp/tmp.bp26JyBAFx`. Below are expanded argv from raw JSON, matching the
plan's checksum/extract/install/version/help commands. All six exited `0`.
Checksum cwd: `/home/runner/work/hugr-lightr/hugr-lightr/r1/packaging/dist`:

```bash
sha256sum -c lightr-0.1.1-linux-x86_64.tar.gz.sha256
```

Extract/install/smoke cwd: `/tmp/tmp.bp26JyBAFx/extract`:

```bash
tar -xzf /home/runner/work/hugr-lightr/hugr-lightr/r1/packaging/dist/lightr-0.1.1-linux-x86_64.tar.gz
install -m 755 lightr /tmp/tmp.bp26JyBAFx/.local/bin/lightr
/tmp/tmp.bp26JyBAFx/.local/bin/lightr --version
/tmp/tmp.bp26JyBAFx/.local/bin/lightr --help
```

Checksum output: `lightr-0.1.1-linux-x86_64.tar.gz: OK`.
Version output: `lightr 0.1.1 (47f0279, 2026-10-01)`.
Help contains `Usage: lightr [OPTIONS] <COMMAND>`; full output is in raw JSON.
Cleanup cwd: `/home/runner/work/hugr-lightr/hugr-lightr/r3-receipt`:

```bash
rm -rf /tmp/tmp.bp26JyBAFx
```

Cleanup succeeded: raw receipt says `removed fresh HOME`; job asserted absence.
Independent downloaded-byte checks and corrupted-copy checksum controls are
cited in [R1](R1-linux-x86_64.md#independent-checksum-controls), review bundle
`lightr-receipt-36845506826.LxtarH/calibration.json` and `verification.json`.

Hosted macOS [OCI/artifact/fresh-install partial evidence](R2-macos-arm64-hosted.md)
passed; hosted arm64 has [no nested Virtualization.framework support][hosted].
**VZ NOT EXECUTED/unvalidated; full R2 incomplete**; raw hosted R3 stays incomplete.
Owner policy accepts candidate R3 only. Public outputs unqualified; `publish = true`
prepared, human-owner `G-PUBLISH` pending
under [the release runbook](../../../RELEASE.md). This receipt qualifies
only the recorded Linux candidate/install environment, not publication or performance.

[freeze]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5928998891
[run]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36845506826
[job]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36845506826/job/110315496820
[source]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36845506826/artifacts/11153018739
[receipt]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36845506826/artifacts/11153158044
[zip]: https://api.github.com/repos/gmhelmold/hugr-lightr/actions/artifacts/11153158044/zip
[hosted]: https://docs.github.com/en/actions/reference/runners/github-hosted-runners#limitations-for-arm64-macos-runners
