# R4 Publisher Preflight: Non-Upload Evidence

**Recorded:** 2026-10-01. **Status:** Identity/direct ownership and
`trusted-publishing` management scope proven; **regular-token publish-new/update UNVERIFIED; R4 pending**.
Authority: [prepared-source freeze][freeze] and [preparation permission][prep].
Source: `47f02795d0884956c4755254b5f6fc377a5938b5`, version `0.1.1`, Rust `1.96.0`.
Eleven intended root packages are prepared `publish = true`; this is not upload permission.

## Redacted receipt and observed GET results

[Durable owner preflight evidence][freeze]; local redacted record: `/var/folders/lt/z11pyzhj0m17vn798jkk69hh0000gn/T/opencode/lightr-publisher-rights-20261001.json`.
Existing default Cargo credentials were parsed and checked for a nonempty token;
credential file contents/token values were not printed or copied into repository/evidence.
Requests were GET only; token authentication may normally update `last_used_at`.

| Probe | Observed outcome |
| --- | --- |
| Anonymous / invalid-token Trusted Publishing GET controls | HTTP `403` / `403` |
| Generic legacy-scope endpoint probe with actual token | HTTP `403`, endpoint/crate scope mismatch |
| Actual-token `GET /api/v1/trusted_publishing/github_configs?user_id=440999` | HTTP `200`; authenticated `gmhelmold`, scoped token |
| Actual-token configs GET with `?crate=<name>`, all nine existing libraries below | HTTP `200` each; active direct ownership |

Libraries: `lightr-core`, `lightr-init`, `lightr-store`, `lightr-index`, `lightr-oci`,
`lightr-views`, `lightr-engine`, `lightr-run`, `lightr-build`.
No upload or owner/configuration changes were performed by these probes.

## Reach and remaining gates

**Later auth-path evidence:** [Trusted Publishing receipt](R4-trusted-publishing.md),
accepted under [#187/comment5938363943](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5938363943), records nine unchanged matching bindings and actual OIDC exchange/revoke in run `36908078128`.
Existing-nine version-publish auth-path readiness is PASS; this historical GET
preflight did not prove it. Regular-auth bootstrap proof remains required for
absent `hugr-lightr-cri-backend` and `hugr-lightr`, at publish positions 9 and 11.
No exclusive token allowlist, upload success, or publication authorization follows.

Pinned upstream [authentication][auth] and [configs controller][controller] explain
scope checks, legacy-token rejection on user-ID GET, matching authenticated user,
and non-deleted direct User ownership on crate GET. These are explanatory source
citations, **not an assertion that production deployment matches this commit**.
Only `trusted-publishing` management scope was exercised by these GET probes; they do not prove
`publish-new` or `publish-update`, name clearance/reservation, exact-version
availability, upload validation, or publication success for all eleven packages.
RC receipts qualify frozen `47f0279` under the VZ-only policy; [actual public native qualification](R3-public-release-assets.md) now PASS on both targets under [owner acceptance](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5934996357).
[Explicit owner tag/draft choice][tag-auth] advances binary qualification before crate scopes only; crate publication/promotion remain unauthorized.
Annotated unsigned `v0.1.1` object `ab042ab801f0bba462385c4c4fd47ac5f60c0866` peels to frozen `47f02795d0884956c4755254b5f6fc377a5938b5`.
[Public run 36850231990](https://github.com/gmhelmold/hugr-lightr/actions/runs/36850231990), attempt 1, completed/success; API updated `2026-10-01T11:24:23Z`. Required `G-PUBLISH` reviews approved.
[Release ID 400899741](https://api.github.com/repos/gmhelmold/hugr-lightr/releases/400899741): `draft=true`, five uploaded assets; no promotion. Use immutable release-ID API, not draft tag lookup.
Independent producer byte-provenance/local-inspection PASS preceded native execution; macOS stays unsigned/ad-hoc, no Developer ID/notarization or Apple credentials.
Producer bundle: `/var/folders/lt/z11pyzhj0m17vn798jkk69hh0000gn/T/opencode/lightr-public-producer-36850231990.GPdHpE` (`run.json`, `release-final.json`, `producer-verification.json`).
Historical [consumer 36877718655](https://github.com/gmhelmold/hugr-lightr/actions/runs/36877718655) failed private-draft GET with App `contents: read`; diagnostics remain preserved. [#283](https://github.com/gmhelmold/hugr-lightr/pull/283) explicitly repaired draft visibility using `contents: write`, `actions: read`; transport still GET-only, not publication authority.
[Consumer 36883638341](https://github.com/gmhelmold/hugr-lightr/actions/runs/36883638341), attempt 1 success, executed verifier/workflow `b0aabc450eab83ee844c29273b8203e5fd84365f` on fresh native runners; compiled source/producer remain `47f0279`. It does not qualify its own source or transfer RC OCI results.
Draft snapshot explicitly says "Qualification draft — not published" and "VZ NOT EXECUTED / unvalidated"; native acceptance changes no VZ policy, crate rights or promotion permission.
[Owner Publish Order](../../../RELEASE.md#owner-publish-order) still applies.

[freeze]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5928998891
[prep]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5928309446
[tag-auth]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5929619780
[auth]: https://github.com/rust-lang/crates.io/blob/a8b65a92154cd737b48abe84136e19156bcfefd2/src/auth.rs
[controller]: https://github.com/rust-lang/crates.io/blob/a8b65a92154cd737b48abe84136e19156bcfefd2/src/controllers/trustpub/github_configs/list.rs
