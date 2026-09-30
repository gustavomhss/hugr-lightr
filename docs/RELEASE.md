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

Read `docs/plans/unix-first-go-live/evidence/R0.md`. Candidate SHA, version,
workflow revision, matrix, checksum contract, P0/Unix-P1 disposition ledger,
and nonpublic-target disposition must agree before R1 or R2 begins. Any source,
workflow, package, or artifact-scope change requires a new R0 receipt.

R2 macOS arm64 receipt must bind exact candidate SHA, `aarch64-apple-darwin`,
`lightr-cli --features vz`, artifact filename/SHA-256, binary SHA-256, named
Apple Silicon hardware, and signed/notarized or unsigned status. Cross-build or
Intel execution cannot substitute for this identity.

## Signing Policy

macOS artifact is signed and notarized only when owner supplies all four
repository secrets: `APPLE_CERT`, `APPLE_CERT_PASSWORD`, `AC_API_KEY`, and
`AC_API_KEY_ID`. Missing any credential produces only
`lightr-<version>-darwin-arm64-unsigned.tar.gz`; release notes and receipts must
state `unsigned`. Never describe unsigned artifact as signed or notarized.

The local `packaging/release.sh` recipe builds macOS `lightr-cli --features vz`,
then ad-hoc signs the stripped staging binary with `packaging/vz.entitlements`.
This permits local VZ execution without an Apple account; it is not Developer ID
signing or notarization. Its artifact keeps `-unsigned`; receipts must record
`unsigned (ad-hoc virtualization entitlement; no Developer ID; not notarized)`.

## Crates.io Order

Before G-PUBLISH, recheck registry names. Publish every workspace crate that
inherits `publish.workspace = true`, waiting for each dependency tier to index:

```sh
cargo publish -p lightr-core
cargo publish -p lightr-init
cargo publish -p lightr-store
cargo publish -p lightr-index
cargo publish -p lightr-run
cargo publish -p lightr-oci
cargo publish -p lightr-views
cargo publish -p lightr-engine
cargo publish -p hugr-lightr-cri-backend
cargo publish -p lightr-build
cargo publish -p lightr-cli
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
