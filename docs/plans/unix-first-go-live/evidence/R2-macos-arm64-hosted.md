# R2 macOS Arm64 Hosted Partial Receipt

**Status: PARTIAL. VZ NOT EXECUTED; full R2 and overall R3 incomplete.**
OCI/artifact/signature and separate fresh-VM install evidence passed for source
and workflow SHA `47f02795d0884956c4755254b5f6fc377a5938b5`, version `0.1.1`.
Authority: [#187 freeze][freeze] and [hosted sequencing deferral][deferral];
requirements: [hosted plan](../../unix-first-go-live.md#hosted-partial-evidence-execution-sequencing).
This documentation commit is not qualified. Public `release.yml` outputs are
not qualified by this run; `G-PUBLISH` pending, `publish = true` prepared.
[Owner policy](R0-0.1.1-owner-waivers.md) accepts candidate R3 for 0.1.1 only;
helper PARTIAL/incomplete labels above remain execution evidence, not policy verdicts.

## Run, environment, and byte identities

[Run 36845503601][run], attempt 1, `workflow_dispatch`, succeeded 2026-10-01.
Both fresh GitHub-hosted `macos-14` jobs checked out the frozen SHA:

| Job | Runner ID | Worker ID | Completed UTC |
| --- | --- | --- | --- |
| [build 110314559105][build] | 1000044113 | 53cecfda-2811-430a-aeda-d7a707e1a984 | 09:57:25Z |
| [clean-install 110316314269][install] | 1000044118 | 3b2077fa-6362-4612-9359-cd36fdcf8c45 | 09:57:48Z |

Both reported Darwin `arm64`, `hw.optional.arm64=1`, `hw.model=VirtualMac2,1`,
macOS `14.8.9` build `23J631`; image `macos-14-arm64`, `20260831.0302.1`.
Physical CPU brand was not recorded. Build toolchain: `rustc 1.96.0 (ac68faa20 2026-05-25)`,
host `aarch64-apple-darwin`, LLVM `22.1.2`.
Build environment: `LIGHTR_NET_TESTS=1`, `RUSTFLAGS="-D warnings -C link-arg=-Wl,-rpath,/usr/lib/swift"`.
CLI package `hugr-lightr`, binary `lightr`, locked release build with `--features vz`.

| Bytes | SHA-256 |
| --- | --- |
| `lightr-0.1.1-darwin-arm64-unsigned.tar.gz` | `0b70b838b50964cc43c513cf33d6324e51fc4316b9a841666e7d344871af1853` |
| Archive and installed `lightr` | `32f3a5cca9e3e7ed408808e56ac366ad04569020bf5108a97c550ef556a144bd` |
| `macos-build/receipt.json` | `ab4c23cbccb4b9290d7e8d0dec2f80f33b5036dff96dd637b0f334cd585e4b1e` |
| `macos-install/receipt.json` | `608769a4fb5d1d22477dab2388326ff01e49bf1062971e4fa6bfb55a14b778db` |

Archive contained only regular executable `lightr`, mode `0755`; `file` reported
`Mach-O 64-bit executable arm64`, `lipo -archs` reported `arm64`.
Both inspections ran `codesign --verify --strict` (exit `0`) and
`codesign -d --entitlements :-` (exit `0`); parsed virtualization entitlement
was **BOOL true**. Signing: **ad-hoc; unsigned; no Developer ID; not notarized**.

## Executed witnesses and controls
`macos-build/commands.json` records exact argv, cwd, exit codes, outputs, and
numbered log paths. From `/Users/runner/work/hugr-lightr/hugr-lightr`:

```bash
cargo +1.96.0 test --locked -p lightr-oci --lib
bash packaging/release.sh
```

Both exited `0`; full OCI suite: **86 passed, 0 failed, 0 ignored** (`07.log`).
The eight names/package selections in [R1](R1-linux-x86_64.md#exact-executed-commands-and-outcomes)
ran with identical Cargo argv **plus trailing `--nocapture` after `--exact`**.
Each ran **1 passed, 0 failed, 0 ignored** (`08.log`–`15.log`). Network log
`12.log` says `pull test PASSED (network lane)` with `LIGHTR_NET_TESTS=1`.
Package/inspection/version outputs are `16.log`–`23.log`; no VZ boot command ran.

Build-job guard commands used `"$RUNNER_TEMP/macos-guards/bin/python"` with
`scripts/ci/test_macos_candidate.py --require-apple-controls` and
`scripts/ci/test_macos_candidate_workflow.py`: **14 + 5 tests passed, zero required skips**.
Real Apple-tool controls accepted arm64/BOOL true and rejected Intel, string
`"true"`, BOOL false, and corrupted signature; identity/version/no-op controls
are retained in the [build job log][build] and frozen test sources.

## Fresh install, checksum, smoke, and cleanup
Install job downloaded immutable `ARTIFACT_ID=11152579956`; verified original
build receipt against `RECEIPT_SHA256=ab4c23cbccb4b9290d7e8d0dec2f80f33b5036dff96dd637b0f334cd585e4b1e`
before checking archive/binary hashes. It checked out the helper, built no CLI.
Fresh `HOME=/Users/runner/work/hugr-lightr/hugr-lightr/macos-install/tmply4n_l0x`;
smoke used `LIGHTR_HOME=$HOME/.lightr`, unset `LIGHTR_STORE_DIR`/`LIGHTR_LINUX_PACK`.
All recorded commands exited `0`. Checksum cwd was
`/Users/runner/work/hugr-lightr/hugr-lightr/candidate/packaging/dist`:

```bash
shasum -a 256 -c lightr-0.1.1-darwin-arm64-unsigned.tar.gz.sha256
```

Output: `lightr-0.1.1-darwin-arm64-unsigned.tar.gz: OK`. Remaining argv, cwd checkout:

```bash
tar -xzf /Users/runner/work/hugr-lightr/hugr-lightr/candidate/packaging/dist/lightr-0.1.1-darwin-arm64-unsigned.tar.gz -C /Users/runner/work/hugr-lightr/hugr-lightr/macos-install/tmply4n_l0x
install -m 755 /Users/runner/work/hugr-lightr/hugr-lightr/macos-install/tmply4n_l0x/lightr /Users/runner/work/hugr-lightr/hugr-lightr/macos-install/tmply4n_l0x/.local/bin/lightr
/Users/runner/work/hugr-lightr/hugr-lightr/macos-install/tmply4n_l0x/.local/bin/lightr --version
/Users/runner/work/hugr-lightr/hugr-lightr/macos-install/tmply4n_l0x/.local/bin/lightr --help
rm -rf /Users/runner/work/hugr-lightr/hugr-lightr/macos-install/tmply4n_l0x
```

Version: `lightr 0.1.1 (47f0279, 2026-10-01)`; help includes
`Usage: lightr [OPTIONS] <COMMAND>`. Full help: `macos-install/14.log` and receipt.
Installed hash matched archive bytes; helper asserted fresh HOME removal before
saving receipt. Exact host/inspection argv and outputs: `macos-install/commands.json`.

## Raw provenance and retention
Downloaded ZIP hashes matched API digests below. Retention is 30 days; expiry UTC:

| Immutable artifact / raw ZIP | ZIP SHA-256 | Expires |
| --- | --- | --- |
| [11152579956 candidate][candidate] / [ZIP][candidate-zip] | `45f14ed4814b7e54704db72b3776314d53396fce9a9b3e6204f3d1b61c8f716c` | 2026-10-31T09:57:17Z |
| [11152284571 build logs][logs] / [ZIP][logs-zip] | `40a048fcc928a33a3c09e541dd48a5a1f291b62c9094700d4550bdec7e15aed0` | 2026-10-31T09:57:19Z |
| [11152893954 install][installed] / [ZIP][install-zip] | `6feb562831b07db9c8a810331612d97c21063a52182183100dee067c0089c96b` | 2026-10-31T09:57:43Z |

Candidate ZIP retains `packaging/dist/` and `macos-build/`; standalone log ZIPs
put each phase's `receipt.json`, `commands.json`, and numbered logs at ZIP root.
Independent raw bundle: `/var/folders/lt/z11pyzhj0m17vn798jkk69hh0000gn/T/opencode/lightr-mac-47f0279-36845503601.vQ7mx8`;
`verification.json`, API metadata, original hash manifests, ZIPs and both job logs
retain review provenance. Build logs in both uploads are byte-identical.
CLI embeds short SHA; full identity comes from checkout/API/workflow/receipts.
No post-build tracked-input status/hash snapshot was captured; dedicated packaged VZ
execution [#113](https://github.com/gmhelmold/hugr-lightr/issues/113) remains open for full R2, waived only as a 0.1.1 publication predecessor.

[freeze]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5928998891
[deferral]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5918255831
[run]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36845503601
[build]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36845503601/job/110314559105
[install]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36845503601/job/110316314269
[candidate]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36845503601/artifacts/11152579956
[logs]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36845503601/artifacts/11152284571
[installed]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36845503601/artifacts/11152893954
[candidate-zip]: https://api.github.com/repos/gmhelmold/hugr-lightr/actions/artifacts/11152579956/zip
[logs-zip]: https://api.github.com/repos/gmhelmold/hugr-lightr/actions/artifacts/11152284571/zip
[install-zip]: https://api.github.com/repos/gmhelmold/hugr-lightr/actions/artifacts/11152893954/zip
