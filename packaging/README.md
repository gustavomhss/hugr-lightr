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

`lightr.rb` contains only macOS arm64 and Linux x86_64 template slots. Owner
fills one macOS URL matching receipt signing status after R0-R3 approval.

## Local Candidate Artifact

```sh
bash packaging/release.sh
```

Local recipe never uploads. It produces host artifact only when host is Linux
x86_64 or macOS arm64; macOS output is `-unsigned` because local recipe does
not sign or notarize. Record output in R1/R2, not template placeholders.
