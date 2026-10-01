# RELEASE: Owner G-PUBLISH Runbook

This procedure authorizes nothing. R0-R3 receipts for one frozen candidate and
explicit human-owner `G-PUBLISH` are required before publication or secret use.
`Cargo.toml` remains `publish = false` during R0. A tag alone creates no asset
or release.

## Frozen Public Matrix

| target | artifact |
|---|---|
| Linux x86_64 | `lightr-<version>-linux-x86_64.tar.gz` + `.sha256` |
| macOS arm64 | `lightr-<version>-darwin-arm64[-unsigned].tar.gz` + `.sha256` |

macOS x86_64 and Linux aarch64 are horizon targets: no public artifact or
support claim. Windows has no artifact or support claim. Existing CI and
cross-compile coverage do not qualify those targets.

## R0 Candidate

The owner-approved **0.1.1 preparation** sets the workspace version to `0.1.1`, with CLI Cargo package
`hugr-lightr`, binary `lightr`, and unchanged source path `crates/lightr-cli`.
Approval is recorded in the 2026-09-30
[#187 owner comment](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5921245830).
[Source preparation](https://github.com/gmhelmold/hugr-lightr/pull/272) includes
root workspace path dependencies pinned to `version = "=0.1.1"`; publication
remains disabled (`publish = false`). Workspace/package/pins are prepared,
not qualified or published. See [registry preflight](NAMING.md#2026-09-30-publication-preflight).

Read `docs/plans/unix-first-go-live/evidence/R0.md`. Candidate SHA, version,
workflow revision, matrix, checksum contract, P0/Unix-P1 disposition ledger,
and nonpublic-target disposition must agree before R1 or R2 begins. Any source,
workflow, package, or artifact-scope change requires a new R0 receipt.

The 0.1.1 version/package/pin and associated build/workflow changes require a
new R0 freeze and new R1-R3 execution. Historical `d09f6c3` Linux receipts prove
only that 0.1.0 source/workflow; preserve them without transferring qualification.

R2 macOS arm64 receipt must bind exact candidate SHA, `aarch64-apple-darwin`,
the `lightr` CLI built with `--features vz`, artifact filename/SHA-256, binary
SHA-256, named Apple Silicon hardware, and signed/notarized or unsigned status.
Cross-build or Intel execution cannot substitute for this identity.

## Signing Policy

macOS artifact is signed and notarized only when owner supplies all four
repository secrets: `APPLE_CERT`, `APPLE_CERT_PASSWORD`, `AC_API_KEY`, and
`AC_API_KEY_ID`. Missing any credential produces only
`lightr-<version>-darwin-arm64-unsigned.tar.gz`; release notes and receipts must
state `unsigned`. Never describe unsigned artifact as signed or notarized.

The local `packaging/release.sh` recipe builds the macOS CLI with `--features vz`,
then ad-hoc signs the stripped staging binary with `packaging/vz.entitlements`.
This permits local VZ execution without an Apple account; it is not Developer ID
signing or notarization. Its artifact keeps `-unsigned`; receipts must record
`unsigned (ad-hoc virtualization entitlement; no Developer ID; not notarized)`.

The public `release.yml` unsigned path has the same signing-state semantics
since [#264](https://github.com/gmhelmold/hugr-lightr/pull/264): it ad-hoc
signs the exact binary that is packaged, verifies its signature strictly, and
requires Boolean-true `com.apple.security.virtualization`. It retains
`SIGNING_DONE=false` and the `-unsigned` suffix; ad-hoc signing is neither
Developer ID signing nor notarization. The [hosted partial-evidence phase](plans/unix-first-go-live.md#hosted-partial-evidence-execution-sequencing)
uses merged #264 and [#266](https://github.com/gmhelmold/hugr-lightr/pull/266);
it does not execute the public release workflow or qualify its output by
inference. VZ remains NOT EXECUTED; full R2 and overall R3 remain incomplete.

## Crates.io Order

Only after explicit owner G-PUBLISH, the required receipts and authenticated
publishing-rights checks may the owner enable publication and execute this
0.1.1 dependency order. Recheck exact registry versions immediately beforehand;
yanked 0.1.0 versions remain immutable. Wait for each dependency tier to index:

```sh
cargo publish -p lightr-core
cargo publish -p lightr-init
cargo publish -p lightr-store
cargo publish -p lightr-index
cargo publish -p lightr-oci
cargo publish -p lightr-views
cargo publish -p lightr-engine
cargo publish -p lightr-run
cargo publish -p hugr-lightr-cri-backend
cargo publish -p lightr-build
cargo publish -p hugr-lightr
```

`lightr-acceptance` is excluded: its manifest sets `publish = false` because it
is test harness. `lightr-cri-serve` and nested `lightr-cri` workspace are
excluded: each manifest sets `publish = false`; they are not root workspace
release packages. Do not use `cargo publish --workspace`.

## Owner Publish Order

1. Recheck R0-R3 receipts against frozen candidate SHA/version. Stop on any mismatch.
2. Change `Cargo.toml` `publish = true` in owner-controlled release change; publish crates in listed order.
3. Create and push `v<version>` tag at frozen candidate SHA. Tag alone builds, uploads, and releases nothing.
4. In Actions, manually dispatch `release.yml` with that exact candidate SHA and existing tag. GitHub Environment `G-PUBLISH` owner approval gates every remote artifact upload and draft-release creation.
5. Verify each tarball with its individual `.sha256`; attach receipts and retain artifact URLs.
6. Fill installer release base/version and formula URLs/SHA-256 values only from verified release assets. Mac URL must match signed or `-unsigned` receipt status.
7. Human owner reviews draft scope and explicitly performs `G-PUBLISH`.

Secrets, `publish = true`, manual workflow dispatch, environment approval,
release upload, and draft promotion are owner actions. Configure `G-PUBLISH`
with required owner reviewers; do not grant self-review bypass. Stop on name
conflict, failed checksum, failed upload, missing native hardware witness, or
identity mismatch. Do not repair released artifact in place.
