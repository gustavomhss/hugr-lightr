# R3 Linux x86_64 Clean-Install Receipt

**Status:** Linux verified; **R3 overall is not done**. Immutable source and
workflow revision: `ca88415b5e34cfefa4fef1eae9ea13511c30f718`, version `0.1.1`.
This documentation was recorded after candidate verification; its documentation
commit is not itself qualified. Authority: [#187 re-freeze][freeze]; requirements:
[R3 plan](../../unix-first-go-live.md#r3-clean-machine-linux-and-macos-arm64-install-checksum-smoke).

## Evidence and clean environment

- [Run 36823107072][run], attempt 1; [R3 job 110243412452][job] completed
  successfully on `2026-10-01T06:09:56Z`.
- [R3 receipt artifact 11143393919][receipt], created `2026-10-01T06:09:54Z`:
  `R3-linux-x86_64.json` and `commands.jsonl` retain exact argv, cwd, exit codes,
  and full checksum/version/help outputs, including the entire help text.
  Downloaded ZIP SHA-256 equals API digest: `187afc0e76e80d13bf7d9d0bb9923f829e0458be328bf38d402519a7ee122018`.
  [Raw ZIP API][zip]; retention expires `2026-10-31T06:09:53Z` (30 days).
  Receipt JSON SHA-256: `5c3d3273b22463f58f9cec4a607c3a3378c5416d7df1d6f3dca6cd4df6898ca7`.
- Distinct GitHub-hosted runner ID `1000044019` (R1: `1000044017`), Ubuntu
  `24.04.5` LTS, `Linux 6.17.0-1022-azure x86_64`, image `20260920.314.1`.
  Job performed only artifact download/install verification and receipt upload;
  no source checkout or build. Job log records fresh `HOME="$(mktemp -d)"`,
  absent `$HOME/.local/bin/lightr`, and cleanup assertion `test ! -e "$HOME"`.
- Immutable install source: [R1 artifact 11144330730][source], not a public
  release asset. Downloaded `packaging/dist/lightr-0.1.1-linux-x86_64.tar.gz` and
  matching `.sha256`; candidate/workflow identities matched [R1](R1-linux-x86_64.md).
  Tarball SHA-256: `deb3ad351d248187a8577642f8cce1023e1c6b70091b059e3cdf268d2ff33616`.
  Installed binary SHA-256: `d6f6a4e496554f28378f3e324bdb7ef5dc85100def883cabbf55a562cd3fd568`.
  Job asserted archive-only `lightr`, extracted regular/non-symlink file, and
  equality of archive and installed binary hashes. Signing: **n/a (Linux)**.

## Exact commands and outcomes

`ARTIFACT=lightr-0.1.1-linux-x86_64.tar.gz`; fresh
`HOME=/tmp/tmp.rCZp3jfGK2`. Below are expanded argv from raw JSON, matching the
plan's checksum/extract/install/version/help commands. All six exited `0`.
Checksum cwd: `/home/runner/work/hugr-lightr/hugr-lightr/r1/packaging/dist`:

```bash
sha256sum -c lightr-0.1.1-linux-x86_64.tar.gz.sha256
```

Extract/install/smoke cwd: `/tmp/tmp.rCZp3jfGK2/extract`:

```bash
tar -xzf /home/runner/work/hugr-lightr/hugr-lightr/r1/packaging/dist/lightr-0.1.1-linux-x86_64.tar.gz
install -m 755 lightr /tmp/tmp.rCZp3jfGK2/.local/bin/lightr
/tmp/tmp.rCZp3jfGK2/.local/bin/lightr --version
/tmp/tmp.rCZp3jfGK2/.local/bin/lightr --help
```

Checksum output: `lightr-0.1.1-linux-x86_64.tar.gz: OK`.
Version output: `lightr 0.1.1 (ca88415, 2026-10-01)`.
Help contains `Usage: lightr [OPTIONS] <COMMAND>`; full output is in raw JSON.
Cleanup cwd: `/home/runner/work/hugr-lightr/hugr-lightr/r3-receipt`:

```bash
rm -rf /tmp/tmp.rCZp3jfGK2
```

Cleanup succeeded: raw receipt says `removed fresh HOME`; job asserted absence.
Independent downloaded-byte checks and corrupted-copy checksum controls are
cited in [R1](R1-linux-x86_64.md#independent-checksum-controls), review bundle
`lightr-receipt-36823107072.VIhsrg/calibration.json` and `verification.json`.

Hosted macOS [OCI/artifact/fresh-install partial evidence](R2-macos-arm64-hosted.md)
passed; hosted arm64 has [no nested Virtualization.framework support][hosted].
**VZ NOT EXECUTED; full R2 and overall R3 incomplete**. Public `release.yml`
outputs are not qualified; `publish = false`, human-owner `G-PUBLISH` pending
under [the release runbook](../../../RELEASE.md). This receipt qualifies
only the recorded Linux candidate/install environment, not publication or performance.

[freeze]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5925747505
[run]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36823107072
[job]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36823107072/job/110243412452
[source]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36823107072/artifacts/11144330730
[receipt]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36823107072/artifacts/11143393919
[zip]: https://api.github.com/repos/gmhelmold/hugr-lightr/actions/artifacts/11143393919/zip
[hosted]: https://docs.github.com/en/actions/reference/runners/github-hosted-runners#limitations-for-arm64-macos-runners
