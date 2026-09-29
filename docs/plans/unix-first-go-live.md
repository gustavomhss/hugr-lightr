# Unix-First Release DAG

**Status:** Frozen release-verification plan. Documentation only; it authorizes
neither a tag, publication, nor a release claim.

**Authority:** [#187 Unix-first scope decision](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5858592985)
and its [initial target-matrix decision](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5859033087),
[ADR-0021](../adr/0021-oci-layer-confinement.md),
[ADR-0022](../adr/0022-atomic-oci-publication-envelope.md), and
[`docs/RELEASE.md`](../RELEASE.md).

**Scope:** Initial public artifacts and support claims are exactly Linux x86_64
and macOS arm64. macOS x86_64 and Linux aarch64 remain horizon targets: retain
code/cross-compile coverage, but publish no initial artifact or support claim.
Windows OCI import is explicit `Unsupported` under
[#249](https://github.com/gmhelmold/hugr-lightr/pull/249); Windows OCI
[#253](https://github.com/gmhelmold/hugr-lightr/issues/253) and WSL runtime
[#199](https://github.com/gmhelmold/hugr-lightr/issues/199) are deferred future
work, not Unix-first publication claims.

```text
R0 candidate freeze and artifact scope
 |
 +--> R1 Linux OCI verification --+
 |                              |
 +--> R2 macOS arm64 OCI/artifact verification
                                |
                                v
                     R3 clean-machine install/checksum/smoke
                                |
                                v
                         R4 owner G-PUBLISH
```

## R0 Candidate Freeze And Artifact Scope

### Success Criteria

- Freeze one release candidate source commit, release version, and intended Linux
  x86_64 and macOS arm64 artifact names: `lightr-<version>-linux-x86_64.tar.gz`
  and `lightr-<version>-darwin-arm64[-unsigned].tar.gz`, with matching `.sha256`.
- Produce lean P0/applicable Unix P1 disposition ledger required by #187. It lists
  only owner-classified P0 and Unix-applicable P1 items, their exact issue/ref,
  accepted/deferred/blocked disposition, and evidence; it is not a universal
  tracker sweep.
- Freeze release-contract work for `.github/workflows/release.yml`,
  `docs/RELEASE.md`, and `packaging/{README.md,install.sh,lightr.rb,release.sh}`
  to remove nonpublic macOS x86_64, Linux aarch64, and Windows release artifacts
  and installer/formula claims before tag.

### Completeness Criteria

- Record candidate commit, toolchain, release workflow revision, artifact matrix,
  checksum filename, intended install inputs, and ledger in
  `docs/plans/unix-first-go-live/evidence/R0.md`.
- Record each nonpublic-artifact reference and the contract change that removes
  it. No scope-by-prose alternative is accepted while release workflow, release
  guide, installer, or formula can publish or select that artifact.

### Quality Standards

- No tag, `cargo publish`, `publish = true`, release upload, or placeholder
  substitution during R0.
- Candidate identity is immutable for R1-R3. Any source, workflow, package, or
  artifact-scope change restarts R0.

### Definition of Done

- Reviewer accepts exact candidate record and nonpublic-artifact disposition.
- R1 and R2 receive same immutable candidate identity.
- R0 receipt identifies only two public artifact targets and records no public
  macOS x86_64, Linux aarch64, or Windows artifact.

### Invariants

- Cross-compilation or expected `Unsupported` does not prove runtime support.
- Horizon/deferred status is not an artifact, support, or qualification claim.

## R1 Linux OCI Verification

### Success Criteria

- Frozen Linux candidate preserves ADR-0021 confined OCI behavior or fails
  explicitly before publication.
- OCI-derived ref publication follows ADR-0022's per-ref atomic envelope boundary.

### Completeness Criteria

- Run specified Linux OCI import, opaque-link, traversal, whiteout, hardlink,
  cleanup, and publish-path witnesses from frozen Linux x86_64 candidate:
  `cargo +1.96.0 test -p lightr-oci --lib` and
  `bash packaging/release.sh`.
- Expected candidate artifact is
  `packaging/dist/lightr-<version>-linux-x86_64.tar.gz` plus its `.sha256` file.
  Record command output, artifact SHA-256, and witness results in
  `docs/plans/unix-first-go-live/evidence/R1-linux-x86_64.md`.
- Preserve exact commands, source/binary identities, environment, outputs, and
  mutation or negative-control results in receipt.

### Quality Standards

- Verify descriptor-relative no-follow traversal, exclusive staging, opaque link
  text, and identity-checked cleanup; do not substitute path-based checks.
- A failed or unavailable witness blocks R1. No retry-until-green, skipped
  witness, or artifact-only inference.

### Definition of Done

- Reviewed Linux receipt identifies candidate and every required witness outcome.
- Pass requires both commands exit 0, every selected OCI test passes, and receipt
  hash equals generated `.sha256` value for named Linux x86_64 artifact.
- R1 failure leaves no release claim and returns candidate to R0 or repair.

### Invariants

- OCI remains import format, not runtime image model.
- Per-ref envelope atomicity does not claim multi-ref atomicity or crash recovery.

## R2 macOS Arm64 OCI And Artifact Verification

### Success Criteria

- Frozen macOS arm64 candidate verifies OCI behavior required by ADR-0021 and
  produces intended macOS arm64 artifact with recorded checksum.

### Completeness Criteria

- Run OCI witnesses on named Apple Silicon hardware using frozen candidate.
- In frozen candidate checkout run `cargo +1.96.0 test -p lightr-oci --lib`,
  `bash packaging/release.sh`, and
  `bash spikes/s5-vz-boot-arm64/run-s5-arm64.sh`.
- Verify artifact filename, architecture, executable identity, checksum, and
  signing status as signed/notarized or explicitly unsigned. Bind receipt to
  frozen source SHA, binary SHA-256, `aarch64-apple-darwin`, and
  `lightr-cli --features vz`; Intel execution or a binary without `vz` fails R2.
- Expected candidate artifact is
  `packaging/dist/lightr-<version>-darwin-arm64[-unsigned].tar.gz` plus its
  `.sha256` file. Record hardware identity, all command outputs, artifact
  SHA-256, and signing status in
  `docs/plans/unix-first-go-live/evidence/R2-macos-arm64.md`.

### Quality Standards

- Native Apple Silicon execution is required; Intel execution or cross-build is
  not substitute evidence.
- Missing signing credentials may yield clearly unsigned artifact only if R0 scope
  and `docs/RELEASE.md` permit it; never label it signed or notarized.

### Definition of Done

- Reviewed receipt binds named hardware, exact candidate/binary, OCI witnesses,
  artifact checksum, and signing status.
- Pass requires all three commands exit 0, `run-s5-arm64.sh` reports every
  assertion passed, and receipt hash equals generated `.sha256` value for named
  macOS arm64 artifact.
- Unavailable hardware, failed witness, or unverifiable artifact blocks R2.

### Invariants

- Receipt proves only recorded candidate and environment.
- Expected Windows `Unsupported` is not macOS OCI evidence.

## R3 Clean-Machine Linux And macOS Arm64 Install, Checksum, Smoke

### Success Criteria

- One clean Linux x86_64 environment and one clean macOS arm64 environment verify intended checksums,
  install intended artifacts, and complete defined smoke commands.

### Completeness Criteria

- Use environments without preinstalled candidate binary or workspace artifacts.
- Linux receipt runs `sha256sum -c "$ARTIFACT.sha256"`; macOS receipt runs
  `shasum -a 256 -c "$ARTIFACT.sha256"`. Both run
  `tar -xzf "$ARTIFACT"`,
  `install -m 755 lightr "$HOME/.local/bin/lightr"`,
  `"$HOME/.local/bin/lightr" --version`, and
  `"$HOME/.local/bin/lightr" --help`, where `ARTIFACT` is exact R1/R2
  filename in receipt directory.
- Record OS/architecture, artifact URL or local immutable source, checksum command
  and result, install command, binary version/hash, smoke command, output, and
  uninstall or cleanup result where applicable.
- Record Linux result in
  `docs/plans/unix-first-go-live/evidence/R3-linux-x86_64.md` and macOS result in
  `docs/plans/unix-first-go-live/evidence/R3-macos-arm64.md`.

### Quality Standards

- Download/install path must use same candidate artifact verified in R1/R2.
- Failed checksum, install, or smoke is a release blocker; no manual binary swap,
  unrecorded cache, or substitute artifact.

### Definition of Done

- Independent Linux x86_64 and macOS arm64 receipts pass review and identify exact
  artifacts and commands.
- Pass requires every stated command exit 0, installed binary comes from checked
  tarball, version/help smoke succeeds, and each receipt names one public target.
- R3 closes only for Linux x86_64 and macOS arm64; it makes no horizon or Windows claim.

### Invariants

- A build-machine execution is not clean-machine evidence.
- A successful install does not certify deferred features or unrelated subsystems.

## R4 Owner G-PUBLISH

### Success Criteria

- Human owner publishes only frozen, R0-R3-approved Unix-first artifacts through
  [#187](https://github.com/gmhelmold/hugr-lightr/issues/187) and `docs/RELEASE.md`.

### Completeness Criteria

- Recheck crate/package names, execute required publish order, create tag/release,
  attach intended artifacts and checksums, and retain release URLs and receipts.
- Confirm public release presents only R0-scoped Unix-first support claims.

### Quality Standards

- Credentials and signing material remain out of repository, issues, logs, and
  this plan.
- Stop on name conflict, checksum mismatch, upload failure, or any R0-R3 identity
  mismatch. Do not repair a released artifact in place.

### Definition of Done

- Owner has executed `G-PUBLISH`; published artifact URLs and checksums match R3
  receipts; release status and signing status are truthful.

### Invariants

- Only human owner can execute `G-PUBLISH`.
- This PR, CI, or a green R0-R3 receipt is not publication authorization.

## Separate Work

Snapshot Integrity remains governed by [#146](https://github.com/gmhelmold/hugr-lightr/pull/146)
and campaign [#152](https://github.com/gmhelmold/hugr-lightr/issues/152), with
its own package issues [#147](https://github.com/gmhelmold/hugr-lightr/issues/147)
through [#153](https://github.com/gmhelmold/hugr-lightr/issues/153). PTY work is
separate from this artifact DAG. This document neither closes, defers, qualifies,
nor creates a release gate for those plans.

macOS x86_64 and Linux aarch64 are horizon targets with retained code/cross-compile
coverage but no initial artifact/support claim. Windows OCI #253 and Windows WSL
#199 remain deferred under #187 Unix-first scope. Their omission from R0-R4 is
not implementation, hardware, or support completion.

## No-Release Rule

No release claim follows from this document, PR CI, a cross-build, a planned
receipt, or an expected `Unsupported` result. Publication requires R0-R3 review
on one frozen candidate and explicit human-owner `G-PUBLISH` in #187.
