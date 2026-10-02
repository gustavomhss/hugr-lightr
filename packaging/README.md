# lightr Distribution Packaging

## R0 Contract

Initial public artifacts are exactly:

- `lightr-<version>-linux-x86_64.tar.gz` and matching `.sha256`
- `lightr-<version>-darwin-arm64.tar.gz`, or explicitly
  `lightr-<version>-darwin-arm64-unsigned.tar.gz`, and matching `.sha256`

macOS x86_64, Linux aarch64, and Windows have no initial public artifact or
support claim. Cross-compile coverage does not change this contract.

Tags create no assets or releases. Owner manually dispatches `release.yml` with
frozen candidate SHA and existing version tag; GitHub Environment `G-PUBLISH`
approval gates every artifact upload and draft GitHub Release. Release contains
exactly those tarballs, individual checksum files, and `SHA256SUMS`.

## Signing Policy

macOS signing and notarization run only when `APPLE_CERT`,
`APPLE_CERT_PASSWORD`, `AC_API_KEY`, and `AC_API_KEY_ID` are all present. If
any credential is absent, release workflow publishes only the clearly named
`-unsigned` macOS arm64 artifact. It never calls it signed or notarized.

## Installer And Formula

`install.sh` supports only macOS arm64 and Linux x86_64. It downloads an exact
artifact plus its `.sha256`, rejects a checksum entry whose filename differs
from downloaded artifact, then verifies SHA-256 before extraction. On macOS it
tries signed name first, then only explicit `-unsigned` name.

Installer and formula configure `0.1.1` delivery under
[owner delivery/promotion approval](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5945719224).
Release [v0.1.1](https://github.com/gmhelmold/hugr-lightr/releases/tag/v0.1.1), ID `400899741`, is public since `2026-10-02T05:29:38Z`, `draft=false`, `prerelease=false`, five assets unchanged.
[R4 completion](../docs/plans/unix-first-go-live/evidence/R4-public-release.md) records anonymous downloads and installer routing/byte-copy controls; formula metadata evaluation is not an actual Homebrew install.

Qualified product/tag: `47f02795d0884956c4755254b5f6fc377a5938b5` / `v0.1.1`.
Delivery source `44adeb386df87d45943acca0d9fbc2081373b770` is separate from the qualified product and
[native R3 verifier](../docs/plans/unix-first-go-live/evidence/R3-public-release-assets.md).
That receipt binds tarball/installed-binary SHA-256 and native version/help smoke;
it does not establish full VZ validation or a GA sandbox guarantee.
The formula selects the recorded unsigned/ad-hoc macOS artifact: no Developer ID,
not notarized. **VZ NOT EXECUTED/unvalidated; full R2 incomplete**;
[owner waiver](../docs/plans/unix-first-go-live/evidence/R0-0.1.1-owner-waivers.md)
applies to `0.1.1` only; [#113](https://github.com/gmhelmold/hugr-lightr/issues/113)
remains open for future native-hardware evidence.

## Local Candidate Artifact

```sh
bash packaging/release.sh
```

Local recipe never uploads. It produces host artifact only when host is Linux
x86_64 or macOS arm64; [release.sh](release.sh) ad-hoc signs macOS staging bytes
with [VZ entitlements](vz.entitlements) (since #259). Output remains `-unsigned`:
no Developer ID signing or notarization. Record output in R1/R2 receipts.
