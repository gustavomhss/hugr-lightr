# Native campaign evidence core

**Orchestration pending.** Pure stdlib Unix helpers/tests, not a runnable campaign or benchmark result. Measurement doctrine: [accepted ADR-0012](../../docs/adr/0012-bench-doctrine.md).

- `require(cond, msg)` raises `ValueError`, including under optimized Python.
- `tree(path)` returns `{"entries": {...}, "sha256": "..."}`: descendant kinds/modes, file size/SHA-256, raw symlink targets and empty directories; the root is excluded. Unix descriptor-relative no-follow opens and stat checks reject observed changes. Root parents are trusted; this is not atomic source capture or an ABA-race guarantee. The manifest hash covers compact sorted-key UTF-8 entries JSON with `ensure_ascii=False`.
- `memo(stderr)` requires exactly one `lightr-json: ` row with exactly `key`/`hit`/`exit_code`, strict boolean/integer types, a lowercase 64-hex key and no duplicate fields.
- `verify_memo(row, expected_hit, expected_exit, expected_key=None, different_key=None)` checks metadata; output, process exit and execution counters remain caller checks.
- `coverage(rows, sizes, rounds, scenarios)` returns exact nonempty `(size, scenario, iteration)` samples; rows require `validated=True`, explicit setup/warmup/sample phases and zero-based iterations. Only samples count; rounds >=3.
- `summarize(values)` returns n/min/p50/nearest-rank p95/max/sample_stddev for >=3 finite numbers, with overflow-safe midpoint and finite outputs.

Controls: `python3 -B -m unittest discover -s benchmarks/native -p 'test_campaign.py' -v` (also run with `-O`). Frozen follow-up CLI: `campaign.py --binary PATH --source-dir PATH --source-sha SHA --rounds N --warmups N --sizes INTEGERS --out DIR`; defaults 21 rounds, 2 warmups, `1000,10000`, minimum 3 rounds. Linux x86_64/GNU time, clean tracked HEAD/binary binding and fresh evidence output are required. Scenarios: snapshot-cold, snapshot-warm, hydrate, direct Python, native memo MISS/HIT, input invalidation and failed commands. Cold means fresh CAS/index/home, not flushed OS caches. Timing/provenance/raw bodies/output-counter checks and complete-coverage-only publication belong to follow-up orchestration. Scope is native reproducibility, not sandbox/Docker/VM comparison; no performance factor is claimed.
