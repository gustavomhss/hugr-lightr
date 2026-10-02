# R4 Crates.io Publication: Complete 0.1.1 Receipt

**Recorded:** 2026-10-02. **COMPLETE:** eleven immutable `0.1.1` versions, all non-yanked.
[Initial owner authorization][initial], [six-crate continuation authorization][continue], and [owner completion acceptance][accepted] are separate records. Later [delivery/promotion authorization][delivery] is granted; execution awaits final delivery review/CI.

## Identity and executed runs

- Frozen product/producer: `47f02795d0884956c4755254b5f6fc377a5938b5`, Rust `1.96.0`, `v0.1.1`; annotated unsigned tag object `ab042ab801f0bba462385c4c4fd47ac5f60c0866` still peels to that source.
- [Original run 36951118620][original], attempt 1, publisher harness `27f5974b32f822d91675cd5f4eb6e71841ace803`, job `110664074426`: five published; **PARTIAL_FAILED**, no success receipt.
- [Continuation 36962108525][run], attempt 1, harness `f9c2202de58e8454183c7bad3a78fc85b9e693aa`, job [110697827520][job]: completed/success, exactly six uploads; combined ledger/receipt has five `VERIFIED_PRIOR` and six `PUBLISHED` rows, `state=COMPLETE`.
- Actor/reviewer `gmhelmold`, GitHub ID `265327906`, explicitly approved `G-PUBLISH`. Workflow ID `372449393`, `.github/workflows/publish-crates.yml`, `workflow_dispatch`; historical display name remains "Trusted Publishing auth-only readiness", but this run executed `publish-remaining`; `readiness` job skipped.
- Native Linux/X64 Ubuntu `24.04.5`, image `ubuntu-24.04`/`20260927.320.1`, runner `1000044791`/`2.337.0`; installed `rustc 1.96.0 (ac68faa20 2026-05-25)`. No runtime-performance measurement follows.
- [#290][pr] merged at `2026-10-02T03:52:54Z`; [required CI 36961374776][ci] completed/success for head `419bb24263accb49c9ac9d293a712d4cec624848`. CI is publisher validation, not product requalification.

## Original failure and bounded repair

Original position 6, credential-free `lightr-views` package, exited Cargo `101`/publisher `1` before upload. Preserved root log:

```text
failed to get `shlex` as a dependency of package `cc v1.2.63`
download of sh/le/shlex failed
[16] Error in the HTTP2 framing layer
```

Dependency chain: `shlex` → `cc v1.2.63` → `blake3 v1.8.5` → `lightr-core v0.1.1` → `lightr-views v0.1.1`. No HTTP response status was recorded for this failure; it was not a registry authorization rejection.
Repair sets Cargo child `CARGO_HTTP_MULTIPLEXING=false`. No blind retry, original-batch replay, source/manifest change, or retag occurred.
Fixed `packaging/crate-publication-0.1.1-prefix.json` content SHA-256 is `6d69cf4ec1cb97180e550ecf01af500730dea11a815e2924d3d043b78ecbe3d6` (Git blob `2a3339debf0df2f602acd99daefecb5f79e870d7`).
Before mint and again before the first continuation upload, helper required exact five prefix checksums/non-yanked versions and six absent versions; existing `0.1.0` GET controls calibrated absence checks. Positions 1–5 were neither packaged nor uploaded again.

## Exact published versions and package hashes

Every row: version `0.1.1`, license `Apache-2.0`, `yanked=false`; independent exact-version API, sparse index, and owners GETs each returned HTTP **200**. Active direct owner: `gmhelmold` / crates.io ID **440999**.
API route: `https://crates.io/api/v1/crates/<name>/0.1.1`; sparse route: `https://index.crates.io/<first-two>/<next-two>/<name>`. Raw per-crate response URLs/statuses and JSON are retained below.
`O` = original run `36951118620`; `C` = continuation `36962108525`. SHA-256 covers the compressed Cargo `.crate` bytes.

| Position | Package | Version ID | Origin / auth path | Package SHA-256 = API = sparse index |
| --- | --- | --- | --- | --- |
| 1 | `lightr-core` | 3380213 | O / OIDC | `1cd690f824465a5392ffdd43d7ea79690f3c5407cba8be923113d46efea9a12f` |
| 2 | `lightr-init` | 3380215 | O / OIDC | `764e0214c8487a46a8ae22e2f48482a3130c10b11cb3c78ead1e88c46fb7c83b` |
| 3 | `lightr-store` | 3380217 | O / OIDC | `4d94594ba4f426e09802de4504df8031515917e0297fd12976cb631e5be3e138` |
| 4 | `lightr-index` | 3380218 | O / OIDC | `5ae72539fc31122f523a514f2b02514593dac04b0b6839a63a88308de5012c4f` |
| 5 | `lightr-oci` | 3380221 | O / OIDC | `b199c804deb364d50cf6047cc2ccfff48a6ff06fdc2549445d8eeaf0343b7b91` |
| 6 | `lightr-views` | 3380927 | C / OIDC | `6a98860ad44d6796ca8e379393df4241a49a8472ca4ae76b2f21b661f24f30fb` |
| 7 | `lightr-engine` | 3380928 | C / OIDC | `6caac972f24d1fe203a5f2844a82955c82dae433f4269f5c530a6665f6c99d88` |
| 8 | `lightr-run` | 3380929 | C / OIDC | `bab176b7a7a13ea354ccd1e372d44f2d5f390b22878e5c6708ef55022d370dd0` |
| 9 | `hugr-lightr-cri-backend` | 3380932 | C / REGULAR | `69bc5ae9f40475e58b0a4cd6c8a2eb8352ed83fa27701f72140e73b01d7960fa` |
| 10 | `lightr-build` | 3380937 | C / OIDC | `72c96968687abbc001934512292ac4da72934c6df6ba5ceba24f4dcb16cbb21d` |
| 11 | `hugr-lightr` | 3380945 | C / REGULAR | `411acb32210f2813794b2261172fd8e6d656b81cfbf78baadafd9b63e7139842` |

Nine libraries' `trustpub_data` records provider `github`, repository `gmhelmold/hugr-lightr`, and corresponding origin run. Its `sha` is **harness** `27f5974…` or `f9c2202…`, not product `47f0279…`.
New backend/CLI have `trustpub_data=null`; `published_by` and `audit_actions[action=publish].user` identify `gmhelmold` / `440999`. Successful first writes prove applicable PubNew capability for these two writes only; no global regular-token publish-new/update scope introspection is claimed.

## Executed Cargo and archive-proof reach

For each of the six new rows, exact argv expands this template (`PRODUCT=/home/runner/work/hugr-lightr/hugr-lightr/crate-publication/product`; `PACKAGE` is the selected table name):

```sh
cargo +1.96.0 package --locked --registry crates-io --manifest-path "$PRODUCT/Cargo.toml" -p "$PACKAGE"
cargo +1.96.0 publish --locked --registry crates-io --manifest-path "$PRODUCT/Cargo.toml" -p "$PACKAGE"
```

Each `package` child was credential-free; normal Cargo verification/compilation remained enabled, with no `--no-verify`. Then actual `publish` received only selected `CARGO_REGISTRY_TOKEN`: `TP_TOKEN` for OIDC or environment bootstrap credential for positions 9/11. Isolated HOME/CARGO_HOME/build/target and allowlisted environment kept GitHub/runtime/other publication credentials out of Cargo children.
[Publisher source][driver] checks prepackage archive before write, deletes stale publish scratch, checks actual publish scratch afterward, and requires `prepackage_sha256 == package_sha256 == registry checksum` before advancing. Cargo's registry-visibility wait and helper exact-version API checksum/yank check completed before advance; independent sparse-index GETs corroborated afterward.
[Archive helper][io] checks normalized manifest name/version/license and `.cargo_vcs_info.json` clean Git SHA **47f02795d0884956c4755254b5f6fc377a5938b5**, before write and afterward. Successful receipts plus inspected control reach establish runtime local-archive checks; **no downloaded registry-package archive was independently audited**.
All eleven source packages remain `publish=true`, workspace root flag true; CLI source path `crates/lightr-cli`; acceptance, CRI serve, and nested CRI remain excluded. Cargo package compilation does not rerun OCI runtime acceptance or native R3; existing frozen-product qualification retains its original scope.

[Official action][action] `rust-lang/crates-io-auth-action@c6f97d42243bad5fab37ca0427f495c86d5b1a18` (Node24, SDK `getIDToken`, audience `crates.io`) exchanged at `https://crates.io/api/v1/trusted_publishing/tokens`; post-step reported **"Token revoked successfully"**, completed/success. No separate post HTTP status is recorded; historical auth-only helper HTTP 204 is not transferred here.
After bootstrap, matching bindings backend **23094** / CLI **23095** were created/read back at `2026-10-02T04:08:37.591485Z` / `2026-10-02T04:08:39.068130Z`; original nine **22982–22990** fields/creation timestamps stayed unchanged.
Every binding: `repository_owner=gmhelmold`, `repository_owner_id=265327906`, `repository_name=hugr-lightr`, `workflow_filename=publish-crates.yml`, `environment=G-PUBLISH`. All eleven are now configured/eligible; no subsequent eleven-binding OIDC mint or opaque-token allowlist proof is claimed.
[Owner completion record][accepted] confirms environment `CARGO_BOOTSTRAP_TOKEN` removed successfully, local credentials untouched; no credential values copied into this receipt.

## Evidence bytes and remaining release work

| Evidence ZIP | SHA-256 | Retention |
| --- | --- | --- |
| [Original artifact 11203851991][old-artifact] | `c5039f6face386897c98a1d346af19b01ad546b4928b27e74cb33036edc7ad56` | 30 days; historical partial failure, no success receipt |
| [Continuation artifact 11208028381][artifact], `crate-publication`, 12647 bytes | `dcc337b122bc1024e9b1504a7d2390f685cba5f989f937827b4a6c4830c95c74` | expires `2026-11-01T03:55:08Z` |

Downloaded ZIP hashes match recorded digests. Continuation ZIP contains preflight, identical COMPLETE ledger/receipt, and twelve package/publish logs; original ZIP preserves PARTIAL_FAILED ledger, failure record, and root package log.
Raw source bundles under `/var/folders/lt/z11pyzhj0m17vn798jkk69hh0000gn/T/opencode/`:
- `publisher-36951118620.9TFL2Uar`: `observation.json`, `failure.json`, `ledger.json`, `artifact.zip`, original redacted root/CI logs and pinned source snapshots.
- `publisher-36962108525.RH65hlFQ`: `run.json`, `jobs.json`, `artifacts.json`, `artifact-inventory.json`, `download-digests.json`, `preflight.json`, `ledger.json`, `receipt.json`, per-crate API/index/owners responses, `public-verification.json`, `verification-summary.json`, source manifest and pinned workflow/helper snapshots, redacted logs, PR/CI/tag/draft JSON.
- `lightr-trustpub-setup-20261001.json`: all eleven binding metadata readbacks; historical `workflow_proof=PENDING` label does not negate separately recorded execution.
Verification used real existing API/index controls and rejected altered checksum/yanked copies; original five hashes and failure were preserved.

[Draft 400899741][release] remains `draft=true`, `published_at=null`, bound to product `47f0279`; asset IDs **603105608, 603105607, 603105609, 603105606, 603105603** and names/sizes/digests match original snapshot. No promotion occurred.
Delivery metadata is prepared in this proposed revision under [owner authorization][delivery]: installer/formula select `0.1.1`, exact `gmhelmold/hugr-lightr` release URLs and R3 hashes (macOS `73af74ca490a9c600cf12271162005ef837d9b89f3dc83cc7c7368edbd7aca0d`, Linux `b8e83623b413a36b847cb4417fb623b9ab37500d5cab71bc9299fa2c2f38a6ca`). Final cold review/CI and landing remain pending; promotion is authorized but unexecuted, anonymous download/checksum/install checks follow promotion. This consumer revision does not requalify or rebuild frozen product/producer `47f0279`, change tag/version, or replace asset bytes.
Current driver is frozen `0.1.1` publication machinery, not a generic future-version publisher; initial all-absent and continuation suffix-absent guards intentionally block reruns now that all eleven versions exist.
VZ remains **NOT EXECUTED/unvalidated**, waived only for `0.1.1`; full R2 incomplete and [#113](https://github.com/gmhelmold/hugr-lightr/issues/113) open. [R0](R0.md) owner required/deferred ledger is unchanged.

[initial]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5939211059
[continue]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5944066332
[accepted]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5945488224
[delivery]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5945719224
[original]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36951118620
[run]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36962108525
[job]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36962108525/job/110697827520
[pr]: https://github.com/gmhelmold/hugr-lightr/pull/290
[ci]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36961374776
[driver]: https://github.com/gmhelmold/hugr-lightr/blob/f9c2202de58e8454183c7bad3a78fc85b9e693aa/scripts/ci/crate_publisher.py#L112-L140
[io]: https://github.com/gmhelmold/hugr-lightr/blob/f9c2202de58e8454183c7bad3a78fc85b9e693aa/scripts/ci/crate_publish_io.py#L46-L114
[action]: https://github.com/rust-lang/crates-io-auth-action/tree/c6f97d42243bad5fab37ca0427f495c86d5b1a18
[old-artifact]: https://api.github.com/repos/gmhelmold/hugr-lightr/actions/artifacts/11203851991/zip
[artifact]: https://api.github.com/repos/gmhelmold/hugr-lightr/actions/artifacts/11208028381/zip
[release]: https://api.github.com/repos/gmhelmold/hugr-lightr/releases/400899741
