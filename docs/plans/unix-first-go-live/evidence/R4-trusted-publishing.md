# R4 Trusted Publishing: Configuration and Live Auth-Only Proof

**Recorded:** 2026-10-01. **PASS: OIDC existing-nine version-publish auth-path readiness**, from matching configuration readbacks plus live exchange/revocation; not publication success or permission to upload.
[Setup/proof authority][authority], [registration status][registration], and [live owner acceptance][accepted] are distinct records. Regular-token `publish-new`/`publish-update` remain **UNVERIFIED**; two absent crates require regular-auth first publication. R4 publication/promotion remain pending.

## Product, verifier, and runtime

- Frozen product/producer: `47f02795d0884956c4755254b5f6fc377a5938b5`, version `0.1.1`, Rust `1.96.0`; [R0](R0.md) and [actual native R3](R3-public-release-assets.md) retain their qualification.
- Annotated unsigned `v0.1.1`, object `ab042ab801f0bba462385c4c4fd47ac5f60c0866`, peels to that product. [Release 400899741][release] remains `draft=true`, `published_at=null`, with the same five assets.
- Independent workflow/verifier checkout: `db0846d295cae27fef5f90c10b6441054c6fffd2`, merged [#285][pr]; not qualified product source. One verifier checkout; helper reads product `Cargo.toml` with `git show`, not a second product checkout.
- [Run 36908078128][run], attempt `1`, `workflow_dispatch`, completed/success; workflow ID `372449393`, `.github/workflows/publish-crates.yml`, job [110523569589][job].
- Explicit `gmhelmold` approval in `G-PUBLISH` (environment `23185655139`, reviewer GitHub ID `265327906`) authorized auth-only exchange/revoke: no crate upload, VZ execution, or promotion.
- Native Linux/X64, Ubuntu `24.04.5`; image `ubuntu-24.04`, `ImageOS=ubuntu24`, `ImageVersion=20260927.320.1`; Python `3.12.3`, Git `2.55.0`. Rust product toolchain was not exercised by this auth-only job.
- Runner `1000044428`, runner version `2.337.0`, worker `6496db8c-470f-4ad5-b11b-f8f48d903256`, Azure `eastus`; provisioner `20260901.588`, commit `f88ec8081b781fac6c440065ac7ff9e710ce3d0b`.
- [PR CI 36906496601][ci] succeeded for head `1b5ced3339d17fc629bbe4dc2bda15f3fba591ee`; required CI job succeeded, GTW release job skipped. CI/static fixtures do not prove publishing or VZ execution.

## Executed phases and proof bytes

Workflow permissions: `contents: read`, `id-token: write`. Evidence-bearing phases below all completed/success in this order; setup, checkout cleanup, and completion also succeeded.

| Phase / API step | Exact command or action |
| --- | --- |
| Verifier checkout / 2 | `actions/checkout@11d5960a326750d5838078e36cf38b85af677262`, `ref=github.sha`, full history, `persist-credentials=false` |
| Credential-free preflight / 3 | `python3 scripts/ci/trusted_publishing_readiness.py preflight` |
| Live exchange / 4 | `rust-lang/crates-io-auth-action@c6f97d42243bad5fab37ca0427f495c86d5b1a18` |
| Explicit revocation / 5 | `python3 scripts/ci/trusted_publishing_readiness.py revoke` |
| Proof upload / 6 | `actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02` |
| Official post-cleanup / 11 | Auth action `dist/post.js` |

Pinned official action uses Node24, `dist/main.js`/`dist/post.js`. No URL override: default `https://crates.io`, SDK `getIDToken` audience `crates.io`, then `POST https://crates.io/api/v1/trusted_publishing/tokens`. Log records successful JWT acquisition and exchange; temporary token is masked.
Helper rechecks source/tag/verifier/version and exact preflight identity, then fixed-endpoint `DELETE` must return **HTTP 204** before receipt is written: `state=READY`, `minted=true`, `revocation_status=204`, `publication="NOT EXECUTED"`.
Helper disables ambient proxies and refuses redirects. That guarantee is helper-only: official action uses `fetch` defaults. Official post-step separately reports `"Token revoked successfully"` and success; its HTTP status is not separately recorded.
No Cargo upload, crate publication, VZ execution, or draft promotion occurred. Evidence-artifact upload is not package publication; this workflow has no publication mode.

| Evidence | SHA-256 |
| --- | --- |
| [Artifact 11185921943 ZIP][artifact], `trusted-publishing-readiness`, 1098 bytes | `23274bf0f257374d381a1ec5aa645332f4fde4bac8d03af59be0259a64acba60` |
| ZIP-root `preflight.json` | `da8f2e3b463fcf546b607da29a5c0a59a2f7bbd2b3a4a2a166f6bbcc617d1600` |
| ZIP-root `receipt.json` | `0f5cc8826442849f2deee4a8624a551952520c71fcf02a50e28443da3f796e5f` |

API digest matches downloaded ZIP; expiry **2026-10-31T18:37:03Z**. Closed ZIP list and exact schemas/shared identity were checked; extra-key and wrong-workflow controls were rejected.
Raw bundle: `/var/folders/lt/z11pyzhj0m17vn798jkk69hh0000gn/T/opencode/lightr-authonly-36908078128-5w5dmj9i` (receipt/preflight, ZIP, run/jobs/artifacts/approvals, source snapshots, redacted logs, hash manifest).
Its earlier verification report leaves post-run readback pending; [later acceptance][accepted] and the external setup record below supersede that pending observation. Raw evidence remains historical.

## Nine configurations: before/after readback

External authenticated `GET /api/v1/trusted_publishing/github_configs?crate=<name>` readbacks before and after the run confirmed these unchanged IDs/fields, without duplicate creation. Management credential remained outside CI.
Shared fields for **every row**: `repository_owner=gmhelmold`, `repository_owner_id=265327906`, `repository_name=hugr-lightr`, `workflow_filename=publish-crates.yml`, `environment=G-PUBLISH`.

| Crate | Configuration ID | `created_at` (UTC), unchanged |
| --- | --- | --- |
| `lightr-core` | 22982 | `2026-10-01T17:31:02.625639Z` |
| `lightr-init` | 22983 | `2026-10-01T17:31:04.409915Z` |
| `lightr-store` | 22984 | `2026-10-01T17:31:06.358161Z` |
| `lightr-index` | 22985 | `2026-10-01T17:31:08.199207Z` |
| `lightr-oci` | 22986 | `2026-10-01T17:31:09.568305Z` |
| `lightr-views` | 22987 | `2026-10-01T17:31:11.032694Z` |
| `lightr-engine` | 22988 | `2026-10-01T17:31:12.922448Z` |
| `lightr-run` | 22989 | `2026-10-01T17:31:14.440599Z` |
| `lightr-build` | 22990 | `2026-10-01T17:31:16.598299Z` |

External record: `/var/folders/lt/z11pyzhj0m17vn798jkk69hh0000gn/T/opencode/lightr-trustpub-setup-20261001.json`; `configuration_status="READBACK VERIFIED"`. Its `workflow_proof="PENDING"` is a historical label superseded by the live receipt/acceptance.
Receipt's `"LEAD offline before/after; not checked here"` means **outside the workflow**, not disconnected API reads: these were network GETs, not CI checks.
Matching configs establish eligibility for all nine under the [inspected exchange contract][exchange]; successful mint alone proves at least one matching config. Token response is opaque: no exact allowlist or permission introspection, and no claim that other matching server configurations are absent. This is auth-path readiness, not an upload-validation or publication-success guarantee.

## Bootstrap and remaining execution gates

Public GET snapshots return **404** for `hugr-lightr` and `hugr-lightr-cri-backend`; positive control `lightr-core` returns **200** with matching crate ID. Absence is not name reservation/clearance.
[Upstream publish controller][publish] at `a8b65a92154cd737b48abe84136e19156bcfefd2` explicitly rejects first publication with:
> Trusted Publishing tokens do not support creating new crates. Publish the crate manually, first

[Inspected usage documentation][usage] requires initial API-token publication; [RFC 3691][rfc] lists pending publishers as future possibilities. Pending-publisher CREATE is not deployed in the observed setup; proposed routes are not a bootstrap path. Source citations explain contracts, not proof that production runs that exact upstream commit.
Before any upload, obtain regular first-publication authorization and credential evidence for both absent names: `publish-new`, applicable exact-name/crate scope, account publication prerequisites, full publish authentication, and immediate name/version checks. Existing management scope/ownership proves none of these; regular-token `publish-update` also remains unverified.
Keep the [eleven-package dependency order](../../../RELEASE.md#cratesio-order): backend first publication is **9**, `lightr-build` **10**, CLI `hugr-lightr` **11**. Do not publish the nine existing crates first. Only after each new crate's regular-auth first publication may its matching Trusted Publisher binding be configured/read back.
Actual publisher workflow is a **future separate change**, requiring CI/cold review and explicit owner execution approval before first upload. Keep frozen product/packages/producer unchanged; changing them requires new R0 and rerun receipts. Crate publication and draft promotion each need explicit authorization.
VZ remains **NOT EXECUTED/unvalidated**, waived only as a `0.1.1` predecessor; full R2 incomplete and [#113](https://github.com/gmhelmold/hugr-lightr/issues/113) open. Existing RC/witness/SI/PTY and native R3 evidence retains its scope.

[authority]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5936778067
[registration]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5937887005
[accepted]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5938363943
[release]: https://api.github.com/repos/gmhelmold/hugr-lightr/releases/400899741
[pr]: https://github.com/gmhelmold/hugr-lightr/pull/285
[run]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36908078128
[job]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36908078128/job/110523569589
[ci]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36906496601
[artifact]: https://api.github.com/repos/gmhelmold/hugr-lightr/actions/artifacts/11185921943/zip
[exchange]: https://github.com/rust-lang/crates.io/blob/a8b65a92154cd737b48abe84136e19156bcfefd2/src/controllers/trustpub/tokens/exchange/mod.rs
[publish]: https://github.com/rust-lang/crates.io/blob/a8b65a92154cd737b48abe84136e19156bcfefd2/src/controllers/krate/publish.rs
[usage]: https://github.com/rust-lang/crates.io/blob/a8b65a92154cd737b48abe84136e19156bcfefd2/svelte/src/routes/docs/trusted-publishing/+page.svelte
[rfc]: https://rust-lang.github.io/rfcs/3691-trusted-publishing-cratesio.html#future-possibilities
