# ADR-0021 — OCI layer confinement and typed-link preservation

- **Status:** Accepted (explicit owner decision, 2026-09-27)
- **Date:** 2026-09-27
- **Scope:** OCI layer import and its private staging tree only.
- **Evidence:** [issue #242](https://github.com/gmhelmold/hugr-lightr/issues/242), cold review of PR #241, and Linux validation run `36254198267` cited there.

## Context

Issue #242 identifies a check/use race: path-based layer application can validate a
component, then traverse an attacker-replaced symlink. Predictable, non-exclusive
staging makes that race adoptable. OCI-valid absolute symlink text must also remain
opaque rather than be interpreted against host filesystem.

ADR-0017 requires a Windows `symlink_file` copy fallback for its general portability
seam. Copying or skipping changes OCI layer meaning and cannot preserve confined
layer semantics.

## Decision

ADR-0017's OCI symlink copy fallback is superseded **only for OCI layer import**.
Its fallback remains unchanged for every other ADR-0017 scope.

### Unix layer apply

1. Create private staging exclusively. Never adopt existing path. Anchor apply on
   opened staging directory descriptor.
2. Resolve, create, write, delete, rename, and hardlink descendants
   descriptor-relatively. Every traversal is no-follow; no operation re-resolves a
   checked pathname from staging root.
3. Store symlink payload as opaque link text. Never dereference its target while
   applying layer, including absolute targets and dangling links.
4. Create hardlinks only from verified in-tree objects through same confined
   descriptor-relative path. Preserve hardlink identity; never degrade to copy.
5. Apply whiteouts and deletes only through confined no-follow handles. A whiteout
   or delete cannot follow or remove outside staging.

### Windows layer apply

1. Traverse descendants relative to named, opened directory handles. Every opened
   component forbids reparse points; no path-based check/use sequence is valid.
2. Preserve typed links only when type is known. Reject ambiguous dangling-link type.
   Never copy, skip, or synthesize another link representation as fallback.
3. Safe handle-relative reparse creation requires
   `SeCreateSymbolicLinkPrivilege`. Developer Mode alone is insufficient and
   must not select path-based `CreateSymbolicLinkW`. If capability is absent,
   fail with explicit unsupported/capability error; do not continue import,
   copy, or skip.
4. Reject device, FIFO, and socket layer entries as `Unsupported`.
5. Before mutating staging, validate every layer path for case-fold collision,
   reserved Windows name, alternate data stream, and trailing dot/space ambiguity.
   Reject ambiguous archive before partial application.

### Commit and cleanup

Publish ref is final visibility action. Any validation, traversal, mutation,
materialization, or cleanup failure leaves publish ref unadvanced. Cleanup acts only
on staging identity and handles created by this import; it must not clean a path
reopened by spelling.

## Consequences

OCI import either preserves confined layer semantics or fails explicitly. It never
silently weakens link safety or changes layer representation. Existing path
traversal, symlink-component, hardlink-escape, and whiteout/delete mutation probes
remain required evidence under issue #242.

Actual Windows runtime qualification is mandatory before claiming this path works on
Windows. Cross-compilation, static review, and non-Windows tests are not runtime
qualification. Until native evidence exists, Windows behavior remains specified but
unqualified.
