# ADR-0023 — Apply native explicit env and isolate legacy cached results

- **Status:** Accepted (owner decision, 2026-10-02)

## Context and authority

The published 0.1.1 foreground native memo path keys `env_explicit` but does not
apply it to the child. Correcting only spawn would still replay incorrect legacy
results. The owner authorized versioning only the explicit-env contribution,
preserving keys without explicit env; recorded answer: **"Versionar env
(Recommended)"** (maintainer session, 2026-10-02).

## Decision

1. Apply `RunSpec.env_explicit` to the native foreground child after runtime
   config. Explicit values override inherited/generated values; empty explicit
   env leaves parent-env passthrough unchanged.
2. Change the non-empty RUN explicit-env contribution tag from
   `b"\x03env_explicit\0"` to `b"\x03env_explicit/v2\0"`. Keep sorted `key=value\0`
   encoding and global `b"lightr/run/v1\0"` domain. Both key builders use the same
   contributor; empty explicit env still contributes no bytes.
3. Legacy explicit-env records become MISS; corrected runs memoize normally.
   Do not delete old AC records or CAS objects. Preserve LRR1, refs and store layout.

This is a narrowly authorized exception to the previously frozen RUN env encoding,
not a BUILD/VZ key change, server-side change or new release authorization.

## Verification

Real child tests must prove env application/override, MISS then HIT, changed-env
invalidation, legacy explicit-env AC rejection and unchanged no-env key/replay.
The legacy fixture reconstructs 0.1.1 encoding independently and seeds a valid
LRR1 record from an actual child that ran without env overrides.
