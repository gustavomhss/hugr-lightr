# ADR-0022 — Atomic OCI image publication envelope

- **Status:** Accepted (owner authorized 2026-09-27)
- **Date:** 2026-09-27
- **Scope:** Local Store persistence and publication of OCI-derived per-ref metadata.

## Context

An OCI image ref currently has a `RefRecord` plus optional config and manifest
metadata held in separate per-ref files. Independent writes expose intermediate
states: readers can observe a new ref with old, missing, or unrelated OCI
metadata. Ordering separate files reduces a particular window but cannot make
their combined state atomic.

OCI remains an import format. Lightr local model remains CAS objects, manifests,
and refs (ADR-0009). This decision changes only how a ref's optional OCI
metadata is published; it does not make OCI blobs or images a local runtime
model.

## Decision

1. Store one per-ref atomic publication envelope. It owns exactly one
   `RefRecord` and optional digest pointers for captured OCI config and image
   manifest metadata.
2. Freeze envelope v1 bytes as: `00 00 4c 4f 43 49 45 31` (ASCII suffix
   `LOCIE1`),
   `u32-le version = 1`, `u32-le RefRecord length`, exact `RefRecord` bytes,
   one `u8` config-present flag plus 32-byte digest when set, then one `u8`
   manifest-present flag plus 32-byte digest when set. Flags are only `0` or
   `1`; no trailing bytes are allowed. The leading zero name length is
   disjoint from every valid legacy `RefRecord` name.
3. An envelope-tagged ref must decode as this complete frame and version.
   Truncation, invalid lengths or flags, invalid embedded `RefRecord`, unknown
   version, trailing bytes, or missing pointed-to CAS body are tagged malformed
   envelope errors. They never fall back to legacy parsing. Fallback occurs
   only after a complete, grammar-valid legacy `RefRecord` decode with full
   consumption proves the file is legacy.
4. Prepare every referenced body in CAS before publication. Config and manifest
   bytes are immutable CAS objects; their digest pointers are written only in
   the envelope.
5. Publish or replace an envelope through one temp-file rename. That rename is
   the sole visibility point for its ref's `RefRecord` and OCI metadata.
6. Add one Store publication seam that accepts a `RefRecord` plus optional OCI
   config and manifest bodies or prepared digest pointers, prepares bodies when
   supplied, then atomically publishes their envelope. The seam rejects invalid
   refs, malformed envelopes, and missing prepared bodies before rename.
7. Add `image_ref_get`: one tuple read returning `RefRecord` plus optional
   config and image-manifest bodies from one decoded envelope. `oci push`,
   `oci save`, and `oci history` use this API, not independent config and
   manifest reads. `ref_get`, `image_config_get`, and `image_manifest_get`
   decode envelopes and retain proven-legacy fallback for compatibility.
8. Route every OCI-image writer through this Store seam: `lightr oci import`,
   `lightr oci pull`, top-level `lightr tag`, `lightr oci tag`, top-level
   `lightr rmi`, and `lightr oci rmi`. Tags publish destination ref and copied
   optional OCI pointers in one envelope. Removes delete one ref envelope in
   one ref-level visibility action; CAS bodies remain garbage-collection
   candidates.
9. Do not claim atomic ordering across multiple ref files, legacy sidecars,
   CAS body writes, ref history, or names/log indexes. CAS preparation precedes
   publication; only one ref envelope has one atomic visibility point.

## Consequences

- Readers cannot observe a newly published envelope with partially updated
  config or manifest pointers.
- Existing plain refs remain usable. Migration is lazy: a new publication for a
  ref writes its envelope; no bulk rewrite is required.
- New Store tests must prove frozen-frame round trips through all three read
  APIs and `image_ref_get`; reject every malformed tagged frame without legacy
  fallback; legacy plain-ref compatibility; body-preparation failure leaves the
  prior envelope visible; and a failed pre-rename write exposes no new envelope.
- Concurrent-reader/writer tests must alternate two complete envelopes while
  readers call `image_ref_get`, and prove every observed tuple is complete and
  equals one published tuple, never a mixed tuple.
- OCI import, pull, both tag verbs, and both remove verbs must prove they use
  the atomic Store seam. Push, save, and history tests must prove tuple reads.
- This ADR does not promise crash recovery, multi-ref transactions, atomic
  garbage collection, cross-operation transactions, or safety for old binaries
  that write legacy sidecars concurrently with envelope-aware binaries.
