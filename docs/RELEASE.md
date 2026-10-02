# RELEASE: Owner G-PUBLISH Runbook

This procedure authorizes nothing. R0-R3 receipts for one frozen candidate and
explicit human-owner `G-PUBLISH` are required before publication.
The prepared candidate has `publish = true` for eleven intended root packages;
all eleven `0.1.1` crates are now published under explicit owner authorization; GitHub draft promotion is authorized, pending execution after final delivery review/CI. A tag alone creates no asset or release.

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
authenticated publication readiness, and explicit publication actions remain required.
Historical `ca88415` acceptance does not qualify this source. [GET preflight](plans/unix-first-go-live/evidence/R4-publisher-preflight.md)
proved identity/direct ownership and management scope only. [Historical live OIDC proof](plans/unix-first-go-live/evidence/R4-trusted-publishing.md) established existing-nine auth-path readiness; [actual publication receipt](plans/unix-first-go-live/evidence/R4-crates-publication.md) now records nine OIDC publications and two successful regular-auth first writes, without blanket token-scope introspection.

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

**0.1.1 COMPLETE:** this order is historical; do not rerun these uploads. Actual locked Cargo commands, immutable version IDs/hashes, and preserved partial failure are in [R4 publication](plans/unix-first-go-live/evidence/R4-crates-publication.md).
For a future qualified release, prepare intended publication manifests before final R0, as ordered below.
Only after final qualification, actual public-output qualification, authenticated
publishing-rights checks, and explicit owner execution authorization may the owner
execute the dependency order below for that newly authorized version. Recheck exact registry versions immediately beforehand;
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

### Trusted Publishing Scope and Bootstrap

`publish-crates.yml` at verifier `db0846d295cae27fef5f90c10b6441054c6fffd2`
was **auth-only, with no publication mode**. [Accepted historical live proof](plans/unix-first-go-live/evidence/R4-trusted-publishing.md)
binds frozen product `47f0279`/`v0.1.1`: nine matching configurations, actual
OIDC exchange, helper revocation HTTP 204, and successful official post-cleanup.
Readbacks are external network GETs, not workflow checks or disconnected reads.
Opaque token does not prove an exclusive nine-crate allowlist or successful uploads.

Current harness `f9c2202de58e8454183c7bad3a78fc85b9e693aa` retains default `auth-only` and adds actual `publish`/`publish-remaining` modes. Product remains frozen `47f0279`; this harness is not qualified product source.
[Owner initial authorization](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5939211059) and [controlled continuation](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5944066332) produced five original uploads and six continuation uploads, accepted in [completion record](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5945488224).
Regular-auth bootstrap succeeded at backend position 9 and CLI 11; bindings 23094/23095 now match original nine unchanged bindings. Applicable PubNew is proven for those two writes only; regular-token global scopes remain opaque. Environment bootstrap secret was removed successfully; local credentials untouched.
All eleven `0.1.1` versions are immutable/non-yanked; current frozen driver guards block reruns and are not a generic future publisher. Keep qualified source, packages and producer fixed; changing them restarts R0 and rerun receipts.

### Qualified Draft and Remaining Owner Actions

**Historical 0.1.1 order exception:** [owner choice "Autorizar tag e draft"](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5929619780) authorized annotated `v0.1.1` at `47f02795d0884956c4755254b5f6fc377a5938b5`, `release.yml` dispatch, explicit `G-PUBLISH` reviews, uploads and DRAFT qualification before publish-new/update scope proof. That authority advanced binary qualification only; later crate authorization is recorded separately above. Default rights-before-tag order otherwise remains.
Producer completed and immutable-ID DRAFT created; [actual public native receipt](plans/unix-first-go-live/evidence/R3-public-release-assets.md) records PASS on both targets under [owner acceptance](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5934996357). Crate publication/bootstrap are COMPLETE. [Owner delivery/promotion authorization](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5945719224) is granted; proposed delivery metadata awaits final cold review/CI. Draft `400899741` remains `draft=true`, `published_at=null`, with five unchanged assets; promotion and subsequent anonymous delivery checks are not executed.
Independent consumer/workflow `b0aabc450eab83ee844c29273b8203e5fd84365f` verified frozen producer `47f0279`; it neither qualifies its own source nor changes the product. Changing selected publication source/producer workflow restarts R0 and reruns.

Steps 1–5 record the completed 0.1.1 sequence and future-release prerequisites; step 6 is prepared in this proposed revision, step 7 is authorized but unexecuted. Do not repeat completed publication or move its tag.

1. Owner authorized preparation, then actual ordered crate publication and controlled continuation; R0/R4 record distinct authorities. Identity/ownership, OIDC readiness, registry checks and two regular-auth first writes are complete. Separate delivery/promotion authorization is now recorded above.
2. Intended packages are already `publish = true` in frozen `47f0279`. Any change to selected publication source, manifests or producer workflow invalidates qualification: freeze changed source anew and rerun Linux/hosted receipts. Only VZ is waived for 0.1.1; historical `ca88415` evidence does not qualify changed source. Do not change manifests after qualification or retag the same version.
3. Only after final qualification and explicit owner execution authorization, create/push annotated `v0.1.1` (signed if configured) at the final immutable SHA. Manually dispatch `release.yml` from that workflow revision with that exact SHA/tag; required `G-PUBLISH` reviews gate uploads and creation of a DRAFT, not promotion. Tag alone builds, uploads, and releases nothing.
4. Independently qualify ACTUAL public-workflow outputs: verify original individual `.sha256` files, artifact/binary identities, architecture/features, and macOS `codesign --verify --strict` plus Boolean-true `com.apple.security.virtualization` and truthful signing status. Complete fresh Linux and macOS checksum/install/version/help/hash/cleanup receipts using those exact output bytes. Cached RC outputs do not inherit or substitute for this qualification.
5. The qualified, reviewed and explicitly authorized 0.1.1 sequence completed in listed order, with indexing/checksum checks and regular-auth first publications at positions 9/11; new bindings followed bootstrap. Future publication requires renewed qualification, registry/auth checks and execution authorization. Do not change qualified manifests or tag.
6. Installer release base/version and formula URLs/SHA-256 values are prepared for `0.1.1` from exact verified R3 assets; macOS selects `-unsigned`. This consumer-delivery revision awaits final review/CI and landing; it is separate from qualified product/producer `47f0279`, with no new version, rebuild or tag.
7. Owner authorized promotion of immutable draft `400899741` after final delivery review/CI and asset identity checks. Promotion remains unexecuted; anonymous URL/download/checksum/install checks follow actual promotion and are not yet claimed. Neither waiver nor self-review permission substitutes for execution authorization.

Secrets, `publish = true`, manual workflow dispatch, environment approval,
release upload, and draft promotion are owner actions. The explicit
[self-review exception](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5927682740)
permits `gmhelmold` to review a job initiated by that account: environment
`23185655139` retains required reviewer **User gmhelmold / 265327906**,
`prevent_self_review=false`, and `can_admins_bypass=false`. Explicit environment
review remains required; this setting does not auto-approve or authorize publication.
Stop on name conflict, failed checksum/upload, an unwaived missing witness, or
identity mismatch. Do not repair released artifact in place.
