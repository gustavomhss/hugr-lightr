# ADR-0021 — OCI layer confinement and typed-link preservation

- **Status:** Accepted (owner Unix-first decision, 2026-09-27)
- **Date:** 2026-09-27
- **Scope:** OCI layer import and its private staging tree only; macOS and Linux
  are target release scope pending issue #242 implementation and evidence.
- **Evidence:** [issue #242](https://github.com/gmhelmold/hugr-lightr/issues/242),
  [owner decision comment 5854246940](https://github.com/gmhelmold/hugr-lightr/issues/242#issuecomment-5854246940),
  cold review of PR #241, and Linux validation run `36254198267` cited there.

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

macOS and Linux OCI confinement are target release scope, pending implementation
and evidence under issue #242; this ADR makes no shipped-behavior claim. Windows
OCI layer import must return explicit `Unsupported` for that release until a
separate native Windows qualification wave is accepted. Enforcement is pending a
separate PR; this ADR makes no claim that current code returns `Unsupported`.
It must not copy, skip, synthesize, or otherwise fall back while unsupported. This
supersedes prior Windows-full and privilege decisions only for release timing;
their fail-closed requirement remains binding.

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

### OCI staging and CAS snapshot boundary

ADR-0021 requires confined layer apply to preserve staging hardlink identity;
implementation remains pending under issue #242. Current CAS snapshot manifests
preserve file bytes/content identity, not POSIX inode or hardlink topology.
`hydrate` may therefore materialize formerly hardlinked paths as independent
files. This is an explicit owner decision dated 2026-09-27; it does not weaken
traversal or link safety requirements above.

### Future Windows layer apply

Windows privileged-handle implementation and native runtime qualification are
future work, not release blockers. Required `Unsupported` enforcement remains
pending its separate PR. Once Windows OCI import is qualified, it must:

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

Target release behavior either preserves confined layer semantics or fails
explicitly. It must never silently weaken link safety or change layer
representation. Existing path traversal, symlink-component, hardlink-escape, and
whiteout/delete mutation probes remain required evidence under issue #242.

Windows `Unsupported` behavior is required for this release but pending
enforcement; current code is not claimed to implement it. Cross-compilation,
static review, and non-Windows tests are not native Windows runtime qualification.
A later qualified implementation must meet the future Windows layer-apply
requirements above; it must not introduce a copy fallback.
