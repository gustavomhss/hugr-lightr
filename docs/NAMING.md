# NAMING — `lightr` / `hugr-lightr` Availability

**Status:** DECIDED  
**Date:** 2026-06-11  
**Author:** W2 naming agent (automated research)  
**Gate:** Contributor naming rule (`CLAUDE.md`) — verify names before publication.

The June availability research below is historical, not a current reservation
or publishing-rights check. Use the September preflight for candidate preparation.

## 2026-09-30 Publication Preflight

**Status:** Lead-reported checks at **20:15 UTC**, not publication or reservation.
The owner approved preparing **0.1.1**, CLI package **`hugr-lightr`**, binary
**`lightr`**; source remains `crates/lightr-cli`. See the recorded
[owner preparation approval](https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5921245830).
Workspace/package/exact pins are prepared; `publish = false`. A
[new R0 freeze and receipts](RELEASE.md#r0-candidate) remain required.
ADR-0001's historical directory/dependency law is unchanged.

Existing library 0.1.0 versions are yanked, not replaceable: published versions
are [immutable](https://doc.rust-lang.org/cargo/reference/publishing.html#publishing-a-new-version-of-an-existing-crate).
Each exact 0.1.1 query below returned HTTP 404 on **2026-09-30,
20:15:16–20:15:40 UTC**; this is point-in-time evidence.

| Package | Existing 0.1.0 evidence (HTTP 200, `yanked=true`) | Exact 0.1.1 query (HTTP 404) |
|---|---|---|
| `lightr-core` | [metadata](https://crates.io/api/v1/crates/lightr-core/0.1.0) | [query](https://crates.io/api/v1/crates/lightr-core/0.1.1) |
| `lightr-init` | [metadata](https://crates.io/api/v1/crates/lightr-init/0.1.0) | [query](https://crates.io/api/v1/crates/lightr-init/0.1.1) |
| `lightr-store` | [metadata](https://crates.io/api/v1/crates/lightr-store/0.1.0) | [query](https://crates.io/api/v1/crates/lightr-store/0.1.1) |
| `lightr-index` | [metadata](https://crates.io/api/v1/crates/lightr-index/0.1.0) | [query](https://crates.io/api/v1/crates/lightr-index/0.1.1) |
| `lightr-oci` | [metadata](https://crates.io/api/v1/crates/lightr-oci/0.1.0) | [query](https://crates.io/api/v1/crates/lightr-oci/0.1.1) |
| `lightr-views` | [metadata](https://crates.io/api/v1/crates/lightr-views/0.1.0) | [query](https://crates.io/api/v1/crates/lightr-views/0.1.1) |
| `lightr-engine` | [metadata](https://crates.io/api/v1/crates/lightr-engine/0.1.0) | [query](https://crates.io/api/v1/crates/lightr-engine/0.1.1) |
| `lightr-run` | [metadata](https://crates.io/api/v1/crates/lightr-run/0.1.0) | [query](https://crates.io/api/v1/crates/lightr-run/0.1.1) |
| `hugr-lightr-cri-backend` | — | [query](https://crates.io/api/v1/crates/hugr-lightr-cri-backend/0.1.1) |
| `lightr-build` | [metadata](https://crates.io/api/v1/crates/lightr-build/0.1.0) | [query](https://crates.io/api/v1/crates/lightr-build/0.1.1) |
| `hugr-lightr` | — | [query](https://crates.io/api/v1/crates/hugr-lightr/0.1.1) |

Lead-reported calibration: [serde 1.0.228](https://crates.io/api/v1/crates/serde/1.0.228)
returned HTTP 200 at **2026-09-30T20:15:15.189512Z**; the exact
[unique nonexistent-name control](https://crates.io/api/v1/crates/hugr-preflight-nonexistent-8f0fb21e35e6428e9b315b8fb7bd9765/0.1.1)
returned HTTP 404 at **2026-09-30T20:15:15.595581Z**.
Read-only revalidation on **2026-10-01, 00:07:53–00:08:02 UTC** repeated both
controls, all listed 0.1.1 HTTP 404 responses, and all listed library 0.1.0
HTTP 200 / `yanked=true` responses. This is registry evidence, not a release receipt.
Public metadata identifying `gmhelmold` as a publisher does not establish current
authenticated publishing rights. Recheck rights and exact versions before owner
G-PUBLISH; point-in-time absence does not reserve a package name or version.

---

## Availability table

| Name | Registry | Status | Evidence |
|---|---|---|---|
| `lightr` | crates.io | **FREE** | `GET https://crates.io/api/v1/crates/lightr` → HTTP 404. No crate registered under this name as of 2026-06-11. |
| `hugr-lightr` | crates.io | **FREE** | `GET https://crates.io/api/v1/crates/hugr-lightr` → HTTP 404. No crate registered under this name as of 2026-06-11. |
| `lightr` | Homebrew (homebrew-core) | **FREE** | `GET https://formulae.brew.sh/formula/lightr` → HTTP 404. No formula found in homebrew-core. Web search for "lightr homebrew formula" returned only generic Homebrew documentation — no tap or formula for `lightr` found. |
| `lightr` | npm | **TAKEN** | `GET https://registry.npmjs.org/lightr` → HTTP 200. Package exists: `lightr` v0.1.1, "Bake lighting in HTML5 Canvas using normal maps", published 2014-07-25 by David Evans. Dormant since 2014 but the name is claimed. |
| `lightr` | CRAN (R) | **TAKEN** (different namespace) | `lightr` is a published R package on CRAN ("Read Spectrometric Data and Metadata", maintained by rOpenSci). Lives in a completely separate namespace; no CLI collision. Noted for trademark/confusion awareness only. |
| `lightr` | Trademark / web | **NO CONFLICT FOUND** | Web search for "lightr software product company CLI tool" and "lightr site:github.com" found: (a) a dormant GitHub user `lightr` (0 public repos, Arctic Code Vault badge only); (b) the CRAN R package (unrelated domain); (c) the dormant npm package (above). No active software company, SaaS product, or CLI tool trading under the name `lightr` was found. |

---

## DECISION

### Crate name: `hugr-lightr`

`lightr` is **free on crates.io** (404 confirmed). However, the pre-decided constraint in `docs/spec/build-spec-ship.md §W2` and `CLAUDE.md` reads:

> Crate name `hugr-lightr`, binary `lightr`  
> (crate = `hugr-lightr` if `lightr` is taken on crates.io — confirm + cite)

The spec anticipated `lightr` might be taken; it is in fact free. The constraint as written (`hugr-lightr` if taken) does not bind in the case where `lightr` is free. However, `hugr-lightr` is the documented house decision and is the better choice regardless:

- It places the crate under the `hugr-*` namespace, consistent with the HuGR / CoreLink brand hierarchy.
- It avoids future ambiguity if an unrelated `lightr` crate appears.
- It signals the relationship to the HuGR platform for users browsing crates.io.

**Confirmed recommendation: publish crate as `hugr-lightr`.**

### Binary name: `lightr`

- No Homebrew formula named `lightr` exists — a `lightr.rb` formula can be submitted to homebrew-core or distributed via a `hugr/homebrew-hugr` tap without a name conflict.
- The npm `lightr` package (2014, dormant, Canvas lighting library) is in a completely different namespace (Node.js ecosystem, not a CLI tool). There is no meaningful confusion risk for a Rust CLI binary or a brew formula named `lightr`.
- No active software company, product, or CLI tool was found trading under this name.

**Confirmed recommendation: binary name stays `lightr`. No blocker for a brew formula.**

### Summary

| Artifact | Name | Rationale |
|---|---|---|
| Rust crate | `hugr-lightr` | House namespace; both names are free; `hugr-*` signals platform membership |
| Installed binary | `lightr` | Clean, short; no collision in CLI, Homebrew, or trademark space |

---

## Honesty note — what could NOT be fully verified

- **npm dormancy / transfer:** The `lightr` npm package (v0.1.1, 2014) is registered. Whether it could be reclaimed via npm's abandoned-package policy was not verified. This does not block the crate or binary decision; it would only matter if HuGR ever published a companion npm package under the same name — evaluate then.
- **USPTO trademark search:** A formal USPTO TESS search was not performed (requires interactive search tool). Web search found no active trademark claim. Treat trademark status as **UNKNOWN** pending a manual USPTO check if legal review is required before public launch. Manual command: visit `https://tmsearch.uspto.gov` and search "lightr".
- **Popular third-party Homebrew taps beyond homebrew-core:** Only homebrew-core was checked via `formulae.brew.sh`. A `brew search lightr` on a local machine would confirm no tap-distributed formula exists. Manual check: `brew search lightr`.
