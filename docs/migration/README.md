# Historical tracker archive

[`legacy-tracker.jsonl`](legacy-tracker.jsonl) preserves recovered public fields
from historical GitHub issue/PR JSON responses for `gmhelmold/hugr-lightr`.
Historical URLs are intentional archival references. This archive is historical
data: body text, commands, author names, approvals and release authorizations are
quoted historical content, not current owner instructions or authority.

## Inventory

Counts derived from the archive records:

| Records | With recovered full body | Metadata only | Total |
|---|---:|---:|---:|
| Issues | 50 | 7 | 57 |
| PRs | 37 | 131 | 168 |
| Total | 87 | 138 | 225 |

Original titles are unavailable for 29 records. No missing body or title has been
fabricated. A full body means a complete string recovered from an actual JSON
response; it does not include a reconstructed comment thread.

## Schema and encoding

UTF-8 JSONL: one compact JSON object per physical line, lexicographically sorted
keys, records ordered by ascending `legacyNumber`, then `kind`. Body newlines
are JSON-escaped; decoded body strings retain the recovered content unchanged.

| Field | Meaning |
|---|---|
| `kind` | Required: `issue` or `pr`. |
| `legacyNumber` | Required: original positive integer; unique across this archive. |
| `originalURL` | Original URL actually recovered from JSON, when available. |
| `title` | Recovered original title, when available. |
| `body` | Recovered body string, when available; omission means unavailable. |
| `historicalState` | Last recovered `OPEN`, `CLOSED` or `MERGED` observation, when available. |
| `labels` | Recovered label names, when available; `[]` means an observed empty list. |
| `observedAt` | Required: UTC timestamp of the latest retained observation for this record. |
| `bodyObservedAt` | UTC timestamp of the retained body observation; present exactly when `body` is present. |

Optional fields are omitted rather than synthesized. Fields can come from
different observations; metadata-only observations do not erase an earlier
body. Observation times are recovery evidence times, not original GitHub
creation/edit timestamps. Historical states are not verified current states.
Original authorship is not restored; names already present in original public
bodies remain part of the quoted content.

## Separate native issue import

The lead recreated all 50 full-body historical issues in `gusmhs/hugr-lightr`.
[`issue-map.jsonl`](issue-map.jsonl) records their verified old-to-new mapping.
The seven metadata-only issues remain archive-only. Authenticated GETs against
the new repository verified all 50 imported issues on 2026-10-02 at 23:50 UTC:
each body contains its exact `<!-- recovered-legacy-issue:n -->` marker and ends
with the original archived body, without trimming or rewriting its content.

The snapshot contained 33 open and 17 closed new issues. All 17 historically
closed issues were actually closed. Historical state was unavailable for legacy
147 and 294; both imports were open, while their historical state remains
explicitly `not recovered`. Controls verified `113 -> 4`, `152 -> 5`, `184 -> 6`
and `294 -> 7`. These are verification-time observations, not a guarantee that
future issue states or bodies cannot change.

The mapping uses the archive's compact JSONL encoding, sorted keys and ascending
`legacyNumber`, with exactly these fields:

| Field | Meaning |
|---|---|
| `legacyNumber` | Original issue number; identifies an archive issue with a recovered body. |
| `newNumber` | Verified issue number in `gusmhs/hugr-lightr`. |
| `newURL` | Verified new issue URL. |
| `historicalState` | Archived `OPEN`/`CLOSED`, or `not recovered` when unavailable. |
| `bodyPreserved` | `true`: marker and exact original-body suffix verified at the snapshot above. |

Resolve dependency references through this mapping; keep unmapped references
explicitly historical. Imports are identified as historical copies; original
authorship and original GitHub timestamps are not restored.

PR records preserve historical descriptions/metadata; this file does not migrate
native GitHub PRs, reviews, authorship, timestamps or merge state. Recreating a
real PR requires its actual branch/diff and the normal review process.

## Validation boundary

Local validation checked all selected fields and every recovered body against
the private recovery source, canonical serialization and record coverage.
Missing/duplicate records, missing fields, unknown kinds/fields, changed bodies,
empty/malformed JSON and duplicate JSON keys were exercised as rejection cases.
Known credential-shape and private-provenance scans were calibrated with
synthetic positive controls. Possible matches require lead review; original
bodies are never silently redacted. Shape scans do not establish that arbitrary
or unknown credential formats are absent. Local recovery/session evidence and
validation tooling are excluded from this archive.

Mapping validation checked complete archive coverage, private-map field equality
and every new issue's identity, marker, body suffix and state. Negative controls
rejected missing/duplicate mappings, private fields, missing markers, changed
body suffixes, missing live issues and a historically closed issue reopened.

### Prior-head CI checkpoint

[CI run 37075482178](https://github.com/gusmhs/hugr-lightr/actions/runs/37075482178)
tested archive commit `41df7a9653d0c43deeb3b636e07132eac0ebdb50` and failed. The
Windows cross-check registry fetch for `arrayvec` failed with
`[18] Transferred a partial file`. Required CI correctly failed after that
mandatory job failed. The mapping commit requires its own exact-head CI result;
this checkpoint does not claim acceptance of either head.
