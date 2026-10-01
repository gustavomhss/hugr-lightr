# R2 macOS Arm64 Hosted Partial Receipt

**Status: PARTIAL. VZ NOT EXECUTED; full R2 and overall R3 incomplete.**
OCI/artifact/signature and separate fresh-VM install evidence passed for source
and workflow SHA `ca88415b5e34cfefa4fef1eae9ea13511c30f718`, version `0.1.1`.
Authority: [#187 freeze][freeze] and [hosted sequencing deferral][deferral];
requirements: [hosted plan](../../unix-first-go-live.md#hosted-partial-evidence-execution-sequencing).
This documentation commit is not qualified. Public `release.yml` outputs are
not qualified by this run; `G-PUBLISH` remains pending, `publish = false`.

## Run, environment, and byte identities

[Run 36823104019][run], attempt 1, `workflow_dispatch`, succeeded 2026-10-01.
Both fresh GitHub-hosted `macos-14` jobs checked out the frozen SHA:

| Job | Runner ID | Worker ID | Completed UTC |
| --- | --- | --- | --- |
| [build 110242747882][build] | 1000044016 | 41e3b9d4-147e-46b4-be36-b488d1ef7c8d | 06:12:01Z |
| [clean-install 110244010826][install] | 1000044020 | 2d581508-5838-458f-858b-e194e5d670c6 | 06:12:17Z |

Both reported Darwin `arm64`, `hw.optional.arm64=1`, `hw.model=VirtualMac2,1`,
macOS `14.8.9` build `23J631`; image `macos-14-arm64`, `20260831.0302.1`.
Physical CPU brand was not recorded. Build toolchain: `rustc 1.96.0 (ac68faa20 2026-05-25)`,
host `aarch64-apple-darwin`, LLVM `22.1.2`.
Build environment: `LIGHTR_NET_TESTS=1`, `RUSTFLAGS="-D warnings -C link-arg=-Wl,-rpath,/usr/lib/swift"`.
CLI package `hugr-lightr`, binary `lightr`, locked release build with `--features vz`.

| Bytes | SHA-256 |
| --- | --- |
| `lightr-0.1.1-darwin-arm64-unsigned.tar.gz` | `8cff2a1e4e2947fba09e10c4de0a088b2cfc56ecc58394637d16bf8b63efc6c2` |
| Archive and installed `lightr` | `d52c0cc931ad45e7df0cdd0d8e2424417163afa1f8284134d74f549ebfe444aa` |
| `macos-build/receipt.json` | `07056e6d26b0c93cd33390d84acf469603b1e438f2c0c34d8813328622003e77` |
| `macos-install/receipt.json` | `520f36408059f964d8698823d647f410fa39c9226cf4e27166cf1c782ce6b468` |

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
Install job downloaded immutable `ARTIFACT_ID=11143594082`; verified original
build receipt against `RECEIPT_SHA256=07056e6d26b0c93cd33390d84acf469603b1e438f2c0c34d8813328622003e77`
before checking archive/binary hashes. It checked out the helper, built no CLI.
Fresh `HOME=/Users/runner/work/hugr-lightr/hugr-lightr/macos-install/tmp_2bnpq5i`;
smoke used `LIGHTR_HOME=$HOME/.lightr`, unset `LIGHTR_STORE_DIR`/`LIGHTR_LINUX_PACK`.
All recorded commands exited `0`. Checksum cwd was
`/Users/runner/work/hugr-lightr/hugr-lightr/candidate/packaging/dist`:

```bash
shasum -a 256 -c lightr-0.1.1-darwin-arm64-unsigned.tar.gz.sha256
```

Output: `lightr-0.1.1-darwin-arm64-unsigned.tar.gz: OK`. Remaining argv, cwd checkout:

```bash
tar -xzf /Users/runner/work/hugr-lightr/hugr-lightr/candidate/packaging/dist/lightr-0.1.1-darwin-arm64-unsigned.tar.gz -C /Users/runner/work/hugr-lightr/hugr-lightr/macos-install/tmp_2bnpq5i
install -m 755 /Users/runner/work/hugr-lightr/hugr-lightr/macos-install/tmp_2bnpq5i/lightr /Users/runner/work/hugr-lightr/hugr-lightr/macos-install/tmp_2bnpq5i/.local/bin/lightr
/Users/runner/work/hugr-lightr/hugr-lightr/macos-install/tmp_2bnpq5i/.local/bin/lightr --version
/Users/runner/work/hugr-lightr/hugr-lightr/macos-install/tmp_2bnpq5i/.local/bin/lightr --help
rm -rf /Users/runner/work/hugr-lightr/hugr-lightr/macos-install/tmp_2bnpq5i
```

Version: `lightr 0.1.1 (ca88415, 2026-10-01)`; help includes
`Usage: lightr [OPTIONS] <COMMAND>`. Full help: `macos-install/14.log` and receipt.
Installed hash matched archive bytes; helper asserted fresh HOME removal before
saving receipt. Exact host/inspection argv and outputs: `macos-install/commands.json`.

## Raw provenance and retention
Downloaded ZIP hashes matched API digests below. Retention is 30 days; expiry UTC:

| Immutable artifact / raw ZIP | ZIP SHA-256 | Expires |
| --- | --- | --- |
| [11143594082 candidate][candidate] / [ZIP][candidate-zip] | `bff4db075d66f93e43dd9a25f287e9856c770edecfe015ce95b9ff548bf7e3ca` | 2026-10-31T06:11:55Z |
| [11143144544 build logs][logs] / [ZIP][logs-zip] | `9734f1325e9beb262101e1a689ca256471bea3301758557f07e8e6cec14398bf` | 2026-10-31T06:11:56Z |
| [11143079590 install][installed] / [ZIP][install-zip] | `254c0ecdabd3f5e8b3ae22c3f817d82e0058b24d9f77af9b614df2d56f141aae` | 2026-10-31T06:12:14Z |

Candidate ZIP retains `packaging/dist/` and `macos-build/`; standalone log ZIPs
put each phase's `receipt.json`, `commands.json`, and numbered logs at ZIP root.
Independent raw bundle: `/var/folders/lt/z11pyzhj0m17vn798jkk69hh0000gn/T/opencode/lightr-mac-ca88415-36823104019.JIwP1y`;
`verification.json`, API metadata, original hash manifests, ZIPs and both job logs
retain review provenance. Build logs in both uploads are byte-identical.
CLI embeds short SHA; full identity comes from checkout/API/workflow/receipts.
No post-build tracked-input status/hash snapshot was captured; dedicated packaged VZ
execution [#113](https://github.com/gmhelmold/hugr-lightr/issues/113) remains required.

[freeze]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5925747505
[deferral]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5918255831
[run]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36823104019
[build]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36823104019/job/110242747882
[install]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36823104019/job/110244010826
[candidate]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36823104019/artifacts/11143594082
[logs]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36823104019/artifacts/11143144544
[installed]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36823104019/artifacts/11143079590
[candidate-zip]: https://api.github.com/repos/gmhelmold/hugr-lightr/actions/artifacts/11143594082/zip
[logs-zip]: https://api.github.com/repos/gmhelmold/hugr-lightr/actions/artifacts/11143144544/zip
[install-zip]: https://api.github.com/repos/gmhelmold/hugr-lightr/actions/artifacts/11143079590/zip
