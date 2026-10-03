# Repository ownership migration

Active repository: **[gusmhs/hugr-lightr](https://github.com/gusmhs/hugr-lightr)**,
GitHub owner ID **337118305**. The owner authorized a public migration while
preserving historical commits, authors, tags and evidence.

## Preserved and Recovered

- Initial imported snapshot: 77 previously fetched public branches and the
  annotated `v0.1.1` tag, with unchanged refs/hashes. Main snapshot source was
  `d8f668b3fd43ae8abf7518b6a1e30954f96cdb8f`.
- Local-only/WIP refs and stash were retained in a verified local bundle rather
  than exposed as new public branches. Existing worktrees were not reset/pruned.
- Original 0.1.1 archives/sidecars/aggregate checksum were recovered from retained
  native-install evidence and imported without rebuilding as **release 402204175**,
  public at **2026-10-03T00:36:31Z**. All five anonymous asset hashes matched;
  no new native/VM execution is implied. New release/asset IDs are distinct from
  historical observations; original tag/source/hashes remain.
- [Historical tracker archive](https://github.com/gusmhs/hugr-lightr/blob/1dbdeff26e6db520fc143c5e2f316e5f1d1c5a83/docs/migration/README.md): 225 actually recovered
  issue/PR records, including 87 full bodies. Missing fields remain explicit.
- Fifty full-body issues were recreated under the current owner. Mapping and
  original bodies identify them as historical imports; original authorship,
  timestamps, comments, reviews and native PR merge state were not recreated.
  Metadata-only gaps remain archived rather than invented as placeholder issues.

## Operational Cutover

- `origin` uses the current repository for fetch and push.
- Active source/distribution URLs and client-side repository pins target the
  current repository. Historical references remain archival provenance.
- CI is enabled. Main is protected by strict `Required CI` and administrator
  enforcement; publication uses current-owner `G-PUBLISH` review.
- Producer workflow identity is resolved from the current repository's exact
  `release.yml` API record, not copied from an old repository's numeric ID.
- Crates.io ownership and Trusted Publisher migration remain pending the new
  owner's registry login. Existing immutable packages retain historical publisher
  attribution; this cannot be relabeled as a new owner's historical publication.

## Continuing Work

Native explicit-env correction is on main; historical 0.1.1 binaries still have
the bug. 0.1.2 requires renewed source-bound qualification and publication rights.
See [the current release runbook](RELEASE.md). Apple Silicon VZ remains unvalidated.

The unavailable origin's unfetched issues, comments, PR reviews, Actions logs,
secrets, runners and settings cannot be claimed restored. Current settings were
configured anew; retained original observations stay historical evidence.
