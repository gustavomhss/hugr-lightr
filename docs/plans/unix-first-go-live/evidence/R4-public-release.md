# R4 Public Release: Complete 0.1.1 Receipt

**GO-LIVE 0.1.1 COMPLETE UNDER OWNER WAIVER.** [Owner authorization][authorized]
and [actual promotion/completion record][accepted] are distinct authorities.
[Release v0.1.1][public] / ID **400899741** was published at
**2026-10-02T05:29:38Z**, `draft=false`, `prerelease=false`.
Anonymous tag/latest API GETs resolved that same release; all five original stable
asset URLs returned HTTP **200**. No owner publication operation remains for 0.1.1.

## Fixed identities and prior qualification

- Product/producer: `47f02795d0884956c4755254b5f6fc377a5938b5`, Rust `1.96.0`, `0.1.1`.
- Annotated unsigned tag object `ab042ab801f0bba462385c4c4fd47ac5f60c0866` peels to that source; no retag, rebuild, re-sign or asset replacement.
- Consumer installer/formula source: `44adeb386df87d45943acca0d9fbc2081373b770`, separate from product and native verifier `b0aabc450eab83ee844c29273b8203e5fd84365f`.
- Delivery [#291][delivery] passed cold review and [required CI 36968180411][ci] at head `582294d6e3c01a5260cfe049d5da0c5a47ab8213`; these are delivery checks, not product requalification.
- [Native R3](R3-public-release-assets.md) / [consumer 36883638341][native] already proved exact binaries' version/help/hash/cleanup on both native targets. Identical public bytes retain that evidence; this pass did not rerun native execution.
- [Crate publication](R4-crates-publication.md) separately records all eleven immutable/non-yanked versions: first five uploads plus controlled six, preserved initial failure, completed bootstraps/bindings and removed environment bootstrap secret. This anonymous pass did not re-audit registry publication.

Historical R3 and crate R4 draft/pending statements describe their earlier snapshots;
this receipt supersedes publication state only, preserving their measured scope.
Before/after promotion identity guards preserved tag/source and exact five asset
IDs/names/sizes/digests. Anonymous API digests and downloaded hashes match R3:

| Original asset | ID | Public byte SHA-256 |
| --- | --- | --- |
| `lightr-0.1.1-darwin-arm64-unsigned.tar.gz` | 603105608 | `73af74ca490a9c600cf12271162005ef837d9b89f3dc83cc7c7368edbd7aca0d` |
| Same filename + `.sha256` | 603105607 | `39dc56f100de19f017bb400e8a534fc8f99d905e748b39607905491037e0faa1` |
| `lightr-0.1.1-linux-x86_64.tar.gz` | 603105609 | `b8e83623b413a36b847cb4417fb623b9ab37500d5cab71bc9299fa2c2f38a6ca` |
| Same filename + `.sha256` | 603105606 | `53ad88f7533b805f9afdc30fd3a26501e016849ded0772b075a4acd5961c5339` |
| `SHA256SUMS` | 603105603 | `df42e970e55a21f684a607090ee688381efa00a540b1a16c0570591fc0c99a1e` |

Stable asset base: `https://github.com/gmhelmold/hugr-lightr/releases/download/v0.1.1/`.
Public assets are the durable delivery path; proof does not require unexpired producer ZIPs.

## Anonymous proof and controls

Actual host: **Intel Mac, Darwin x86_64**. Sanitized child environment supplied only
PATH/HOME/locale; real `/usr/bin/curl -q`, HTTPS-only redirects, no Authorization,
cookies, GH_TOKEN or proxy. Request JSON, response headers/bodies and command logs
are retained. API routes: `https://api.github.com/repos/gmhelmold/hugr-lightr/releases/tags/v0.1.1`
and `https://api.github.com/repos/gmhelmold/hugr-lightr/releases/latest`.

Original individual checksums and aggregate passed; corrupt archive copies failed
checksum verification (exit 1; valid exit 0), originals preserved. Each tar contains
only regular `lightr`, mode `0755`, with exact R3 binary hash. macOS strict ad-hoc
signature verification passed; corrupt binary copy failed (exit 1). Signing remains
**unsigned/ad-hoc, no Developer ID, not notarized**; entitlement inspection is not VZ execution.

Actual `/bin/sh consumer-install.body` ran with forced `uname` fixtures for
`Linux/x86_64` and `Darwin/arm64`, isolated HOME and transparent real-curl wrapper.
Both routes installed exact R3 binary bytes, mode `0755`; corrupt Linux temporary
download was rejected before installation. HOME and actual trap temp cleanup verified.
Mac signed-name probe returned HTTP 404 / curl 56; unsigned fallback/sidecar returned
200 and installer exited 0. Initial harness expected curl 22; diagnostics preserved,
existing logs revalidated without request retry. Native `mktemp` ignored bare TMPDIR;
actual removed paths were audited; corruption control used an explicit-template shim.

Formula's two platform branches were evaluated with a metadata-only Ruby DSL:
version `0.1.1`, exact public URLs/R3 hashes, `Apache-2.0`; wrong-hash control rejected.
Wrong release-ID and manifest-hash controls also rejected. **No actual `brew install`,
Linux x86_64/macOS arm64 CLI, firmware or virtualization execution occurred.**
Anonymous source LICENSE at product `47f0279` confirmed Apache-2.0.

## Retained evidence and reproduction

Raw bundle: `/var/folders/lt/z11pyzhj0m17vn798jkk69hh0000gn/T/opencode/public-v0.1.1-proof.SyKR66CP`.
It contains originals/corrupt copies, request headers/bodies/argv, command outputs,
`first-attempt-report.json`, `report.json`, `summary.json`, `manifest.json` and controls.
Independent offline audit validated manifest, rejected mutation and checked cleanup;
its scope is retained evidence, not fresh native logs or registry checks.

| Evidence/source | SHA-256 |
| --- | --- |
| `report.json` | `f22cd67dbc44af4eaec61b74f4c19e4169dec61fa595d122c4caae950586beb0` |
| `manifest.json` | `aa0d78d569843473279e4bbc8e4ca4d409db5534d8a1d98ef360d85d94f078bf` |
| Pinned `packaging/install.sh` | `f921ea34539af3f2acebfcf1ae9e32031aeade45340e278f5111a3b7a195266a` |
| Pinned `packaging/lightr.rb` | `58086b59a74429ce6f2944e1155f2aed5f60aeddde5eb5aabda138140aeb5564` |

Redacted GET reproduction (URL is either API route or stable asset URL above):
```sh
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin HOME="$PROOF" LC_ALL=C /usr/bin/curl -q --noproxy '*' --proto '=https' --proto-redir '=https' --location --silent --show-error --connect-timeout 20 --max-time 180 --dump-header "$PROOF/response.headers" --output "$PROOF/response.body" --write-out '%{json}' "$URL"
```
Account-free installation on supported Linux x86_64/macOS arm64 hosts (consumer pin, not product pin):
```bash
set -o pipefail
curl -q --proto '=https' --proto-redir '=https' -fsSL https://raw.githubusercontent.com/gmhelmold/hugr-lightr/44adeb386df87d45943acca0d9fbc2081373b770/packaging/install.sh | sh
```

Only Linux x86_64 and macOS arm64 are public targets; macOS x86_64/Linux aarch64/Windows
have no public artifact/support claim. **VZ NOT EXECUTED/unvalidated; full R2 incomplete.** [0.1.1-only
owner waiver](R0-0.1.1-owner-waivers.md) removes that publication predecessor only;
[#113](https://github.com/gmhelmold/hugr-lightr/issues/113) stays open for future hardware evidence.
No sandbox/performance/benchmark or server-wide/cross-tenant dedup claim follows.

[authorized]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5945719224
[accepted]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5946324644
[public]: https://github.com/gmhelmold/hugr-lightr/releases/tag/v0.1.1
[delivery]: https://github.com/gmhelmold/hugr-lightr/pull/291
[ci]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36968180411
[native]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36883638341
