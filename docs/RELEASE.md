# RELEASE: Owner G-PUBLISH Runbook

This procedure authorizes nothing. R0-R3 receipts for one frozen candidate and
explicit human-owner `G-PUBLISH` are required before publication.
The prepared candidate has `publish = true` for eleven intended root packages;
crate upload/promotion remain unauthorized; the narrow tag/draft exception below applies. A tag alone creates no asset or release.

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
root workspace path dependencies pinned to `version = "=0.1.1"`; [owner-authorized preparation](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5928309446)
and [#278](https://github.com/gmhelmold/hugr-lightr/pull/278) now set intended root packages to `publish = true`. Preparation alone is not source
qualification or publication; recorded acceptance below binds exact source.
See [registry preflight](NAMING.md#2026-09-30-publication-preflight).

Read `docs/plans/unix-first-go-live/evidence/R0.md`. Candidate SHA, version,
workflow revision, matrix, checksum contract, P0/Unix-P1 disposition ledger,
and nonpublic-target disposition must agree before R1 or R2 begins. Any selected
publication-source, producer-workflow, package or artifact-scope change restarts R0.

The 0.1.1 version/package/pin and associated build/workflow changes require a
new R0 freeze and new R1-R3 execution. Historical `d09f6c3` Linux receipts prove
only that 0.1.0 source/workflow; preserve them without transferring qualification.

R2 macOS arm64 receipt must bind exact candidate SHA, `aarch64-apple-darwin`,
the `lightr` CLI built with `--features vz`, artifact filename/SHA-256, binary
SHA-256, named Apple Silicon hardware, and signed/notarized or unsigned status.
Cross-build or Intel execution cannot substitute for this identity.

### 0.1.1 Owner Waiver

For version `0.1.1`, recorded acceptance binds source/workflow
`47f02795d0884956c4755254b5f6fc377a5938b5` under the [prepared-source freeze](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5928998891); the [owner decision](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5927803638)
accepts the recorded OCI/artifact/fresh-install receipts subject to waiver of
packaged-binary VZ as a publication predecessor. Overall candidate R3 is accepted
for this release scope: both fresh installs passed. **VZ is waived, NOT EXECUTED,
and unvalidated; full R2 remains incomplete.** Historical `PARTIAL`/incomplete
receipts retain their measured status. [#113](https://github.com/gmhelmold/hugr-lightr/issues/113)
remains open for future dedicated-hardware evidence; no VZ sandbox guarantee or
performance claim follows. See the separate [policy acceptance receipt](plans/unix-first-go-live/evidence/R0-0.1.1-owner-waivers.md).
The documentation commit is not qualified. Any changed publication source needs
a new final R0 and rerun receipts; recorded acceptance does not qualify it.
The VZ-only waiver remains limited to 0.1.1. Actual public `release.yml` outputs,
publisher write-scope proof, and explicit publication actions remain required.
Historical `ca88415` acceptance does not qualify this source. [GET preflight](plans/unix-first-go-live/evidence/R4-publisher-preflight.md)
proved identity/direct ownership and trusted-publishing scope only; publish-new/update remain unverified.

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
inference. VZ remains NOT EXECUTED and full R2 incomplete; the
[0.1.1 owner waiver](#011-owner-waiver) accepts candidate R3 for that scope only.

## Crates.io Order

Prepare intended publication manifests before final R0, as ordered below.
Only after final qualification, actual public-output qualification, authenticated
publishing-rights checks, and explicit owner execution authorization may the owner
execute this 0.1.1 dependency order. Recheck exact registry versions immediately beforehand;
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

**0.1.1 order exception:** [owner choice "Autorizar tag e draft"](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5929619780) authorizes annotated `v0.1.1` at `47f02795d0884956c4755254b5f6fc377a5938b5`, `release.yml` dispatch, explicit `G-PUBLISH` reviews, uploads and DRAFT qualification before publish-new/update scope proof. This advances binary qualification only; crate publication/promotion remain unauthorized. Default rights-before-tag order otherwise remains.
Producer completed and immutable-ID DRAFT created; [R4](plans/unix-first-go-live/evidence/R4-publisher-preflight.md) records independent byte-provenance checks. Native public fresh-install qualification remains PENDING.
An independent consumer records its own workflow SHA separately when available; it neither qualifies its own source nor changes the frozen `47f0279` producer. Changing selected publication source/producer workflow restarts R0 and reruns.

1. Owner authorized crates + binaries preparation; #278 and the current R0 freeze record it. GET identity/ownership checks passed; confirm publishing write scopes for every intended crate and exact registry versions before any irreversible tag action. These execution permissions remain pending.
2. Intended packages are already `publish = true` in frozen `47f0279`. Any change to selected publication source, manifests or producer workflow invalidates qualification: freeze changed source anew and rerun Linux/hosted receipts. Only VZ is waived for 0.1.1; historical `ca88415` evidence does not qualify changed source. Do not change manifests after qualification or retag the same version.
3. Only after final qualification and explicit owner execution authorization, create/push annotated `v0.1.1` (signed if configured) at the final immutable SHA. Manually dispatch `release.yml` from that workflow revision with that exact SHA/tag; required `G-PUBLISH` reviews gate uploads and creation of a DRAFT, not promotion. Tag alone builds, uploads, and releases nothing.
4. Independently qualify ACTUAL public-workflow outputs: verify original individual `.sha256` files, artifact/binary identities, architecture/features, and macOS `codesign --verify --strict` plus Boolean-true `com.apple.security.virtualization` and truthful signing status. Complete fresh Linux and macOS checksum/install/version/help/hash/cleanup receipts using those exact output bytes. Cached RC outputs do not inherit or substitute for this qualification.
5. Only after that qualification and renewed exact-version/authenticated-rights checks, obtain explicit owner authorization for irreversible serial crate publication in the listed dependency order. Wait for each dependency tier to index; do not change manifests after final qualification or tag.
6. Fill installer release base/version and formula URLs/SHA-256 values only from exact verified release assets. Mac URL must match signed or `-unsigned` receipt status; attach receipts and retain URLs.
7. Human owner reviews the verified draft scope and explicitly authorizes promotion through `G-PUBLISH`. Neither waiver nor self-review permission authorizes any execution step above.

Secrets, `publish = true`, manual workflow dispatch, environment approval,
release upload, and draft promotion are owner actions. The explicit
[self-review exception](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5927682740)
permits `gmhelmold` to review a job initiated by that account: environment
`23185655139` retains required reviewer **User gmhelmold / 265327906**,
`prevent_self_review=false`, and `can_admins_bypass=false`. Explicit environment
review remains required; this setting does not auto-approve or authorize publication.
Stop on name conflict, failed checksum/upload, an unwaived missing witness, or
identity mismatch. Do not repair released artifact in place.
