# R3 Linux x86_64 Clean-Install Receipt

**Status:** Linux verified; **R3 overall is not done**. Immutable source and
workflow revision: `d09f6c3cf603269aff9dd9d95b94902286695449`, version `0.1.0`.
This documentation was recorded after candidate verification; its documentation
commit is not itself qualified. Authority: [#187 re-freeze][freeze]; requirements:
[R3 plan](../../unix-first-go-live.md#r3-clean-machine-linux-and-macos-arm64-install-checksum-smoke).

## Evidence and clean environment

- [Run 36728965586][run], attempt 1; [R3 job 109934012559][job] completed
  successfully on `2026-09-30T14:27:13Z`.
- [R3 receipt artifact 11103903836][receipt], created `2026-09-30T14:27:13Z`:
  `R3-linux-x86_64.json` and `commands.jsonl` retain exact argv, cwd, exit codes,
  and full checksum/version/help outputs, including the entire help text.
  ZIP SHA-256: `42c7a94656aa4cfa74729f2e06722d506c63813198b7b82c5c7bb968f6421745`.
- Distinct GitHub-hosted runner ID `1000043343` (R1: `1000043335`), Ubuntu
  `24.04.5` LTS, `Linux 6.17.0-1022-azure x86_64`, image `20260920.314.1`.
  Job performed only artifact download/install verification and receipt upload;
  no source checkout or build. Job log records fresh `HOME="$(mktemp -d)"`,
  absent `$HOME/.local/bin/lightr`, and cleanup assertion `test ! -e "$HOME"`.
- Immutable install source: [R1 artifact 11102919978][source], not a public
  release asset. Downloaded `packaging/dist/lightr-0.1.0-linux-x86_64.tar.gz` and
  matching `.sha256`; candidate/workflow identities matched [R1](R1-linux-x86_64.md).
  Tarball SHA-256: `4ac9e1014a3f6d889c9d33b6b01e880fccff518024b5dce13136ec0a5b8ab4b1`.
  Installed binary SHA-256: `e3bcabd0391a7c3857998e1aed4cc26be6cec807bbf6dbbc3d8a07975e916942`.
  Job asserted archive-only `lightr`, extracted regular/non-symlink file, and
  equality of archive and installed binary hashes. Signing: **n/a (Linux)**.

## Exact commands and outcomes

`ARTIFACT=lightr-0.1.0-linux-x86_64.tar.gz`; fresh
`HOME=/tmp/tmp.ZtJY71c74e`. Below are expanded argv from raw JSON, matching the
plan's checksum/extract/install/version/help commands. All six exited `0`.
Checksum cwd: `/home/runner/work/hugr-lightr/hugr-lightr/r1/packaging/dist`:

```bash
sha256sum -c lightr-0.1.0-linux-x86_64.tar.gz.sha256
```

Extract/install/smoke cwd: `/tmp/tmp.ZtJY71c74e/extract`:

```bash
tar -xzf /home/runner/work/hugr-lightr/hugr-lightr/r1/packaging/dist/lightr-0.1.0-linux-x86_64.tar.gz
install -m 755 lightr /tmp/tmp.ZtJY71c74e/.local/bin/lightr
/tmp/tmp.ZtJY71c74e/.local/bin/lightr --version
/tmp/tmp.ZtJY71c74e/.local/bin/lightr --help
```

Checksum output: `lightr-0.1.0-linux-x86_64.tar.gz: OK`.
Version output: `lightr 0.1.0 (d09f6c3, 2026-09-30)`.
Help contains `Usage: lightr [OPTIONS] <COMMAND>`; full output is in raw JSON.
Cleanup cwd: `/home/runner/work/hugr-lightr/hugr-lightr/r3-receipt`:

```bash
rm -rf /tmp/tmp.ZtJY71c74e
```

Cleanup succeeded: raw receipt says `removed fresh HOME`; job asserted absence.
Independent downloaded-byte checks and corrupted-copy checksum controls are
cited in [R1](R1-linux-x86_64.md#independent-checksum-controls), local review log
`run36728965586-review.aMhF39/verification.log` lines 21-26.

Required M-series hardware is unavailable for R2; hosted macOS arm64 has
[no nested Virtualization.framework support][hosted]. R2 and R3 macOS remain
blocked; R4 depends on their completion and human-owner `G-PUBLISH`, still
pending under [the release runbook](../../../RELEASE.md). This receipt qualifies
only the recorded Linux candidate/install environment, not publication or performance.

[freeze]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5913266196
[run]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36728965586
[job]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36728965586/job/109934012559
[source]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36728965586/artifacts/11102919978
[receipt]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36728965586/artifacts/11103903836
[hosted]: https://docs.github.com/en/actions/reference/runners/github-hosted-runners#limitations-for-arm64-macos-runners
