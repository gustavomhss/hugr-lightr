# RELEASE: Current Owner Runbook

Current repository: **[gusmhs/hugr-lightr](https://github.com/gusmhs/hugr-lightr)**.
Current GitHub owner/reviewer: **gusmhs / 337118305**. Historical release records
retain original identities in [the historical Git snapshot](https://github.com/gusmhs/hugr-lightr/blob/d8f668b3fd43ae8abf7518b6a1e30954f96cdb8f/docs/RELEASE.md);
old workflow, run, release and environment IDs are not portable credentials or
qualification for the new repository.

## Status

- Historical 0.1.1 assets were restored byte-for-byte as current-repository
  [release 402204175](https://github.com/gusmhs/hugr-lightr/releases/tag/v0.1.1),
  public since **2026-10-03T00:36:31Z**, with original tag and source
  `47f02795d0884956c4755254b5f6fc377a5938b5`. All five anonymous downloads matched
  original hashes. This is not a rebuild or renewed native/VM qualification.
- Historically published GitHub/crates.io 0.1.1 retains the native explicit-env bug. The source correction and
  selective cache invalidation are described in [ADR-0023](adr/0023-native-explicit-env-cache.md).
- 0.1.2 preparation is retained on `release/0.1.2-prepare`; it is not qualified
  or published. Source/metadata changes during migration require a fresh freeze.
- Crates.io ownership and Trusted Publisher transfer are **pending** the new
  owner's registry identity. GitHub authentication alone does not establish those
  rights. Do not dispatch a publisher or recreate a bootstrap secret while blocked.
- Existing `crate_publisher.py` publication modes remain frozen historical 0.1.1
  machinery. They are not a generic future-version uploader.

## Public Matrix

| Target | Artifact |
| --- | --- |
| Linux x86_64 | `lightr-<version>-linux-x86_64.tar.gz` + `.sha256` |
| macOS arm64 | `lightr-<version>-darwin-arm64-unsigned.tar.gz` + `.sha256` |

## Signing Policy

macOS remains unsigned/ad-hoc, without Developer ID/notarization. Apple Silicon
VZ remains **NOT EXECUTED/unvalidated**; its hardware task is tracked in the
[recovered issue](https://github.com/gusmhs/hugr-lightr/issues/4). The owner's
0.1.2-only predecessor waiver is recorded in the [current-owner continuation](https://github.com/gusmhs/hugr-lightr/issues/7#issuecomment-5963649623):
the same human owner continues under the new account. It does not establish VZ
runtime/sandbox evidence, grant registry rights or authorize later releases.
No public Windows, macOS x86_64 or Linux aarch64 claim.

## Gates

Main requires `Required CI`, strict up-to-date checks and administrator enforcement.
`G-PUBLISH` is environment **23341014123**, required reviewer **gusmhs / 337118305**,
`prevent_self_review=false`, `can_admins_bypass=false`. Explicit deployment review
is still required; the settings neither auto-approve nor grant publication rights.

Preserve the exact selected product source, workflow revision and package manifests
through qualification/publication. Independent verifier/consumer commits are
recorded separately. No source change inherits a previous candidate's receipts.

## Crates.io Order

After verified ownership/configuration, frozen-source qualification and explicit
owner execution authorization, publish registered packages serially with OIDC.
Each verified dependency must index before proceeding:

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

Never `cargo publish --workspace`. Acceptance, CRI serve and nested CRI remain
unpublished. No automatic retry/resume after partial publication: preserve the
ledger, stop, and require separately bounded owner continuation authority.

## Owner Publish Order

1. Confirm registry owner/Trusted Publisher configurations point to the current
   repository, `publish-crates.yml`, `G-PUBLISH` and current GitHub owner ID.
2. Prepare version/exact pins/lock and intended manifests before final R0. Obtain
   independent review and exact-head CI, then record the immutable product source.
3. Run `r1-linux-x86_64-rc.yml` and `macos-arm64-candidate.yml` at the selected
   source/workflow revision; retain OCI witnesses, artifact hashes, native fresh
   installs and signing status. Record any version-specific VZ waiver separately.
4. After rights/readiness and owner authorization, create an annotated tag at that
   exact source. Dispatch `release.yml`; protected jobs create a draft, not a public
   release. Tags alone create no asset.
5. Independently qualify actual producer bytes with `public-release-install.yml`
   on fresh native Linux x86_64/macOS arm64 runners. Use the new producer/release
   IDs, annotated source tag and original sidecars/aggregate checksums.
6. Execute the newly authorized frozen serial crate batch; verify local package,
   publish scratch, API and index checksums. Stop on failure; never replay 0.1.1.
7. Update installer/formula from actual qualified assets in a reviewed delivery
   change. Promote only the verified draft under owner authority; recheck anonymous
   downloads/checksums and preserve receipts with their actual proof boundaries.

Local source/runtime use requires no GitHub account or optional network bridge.
