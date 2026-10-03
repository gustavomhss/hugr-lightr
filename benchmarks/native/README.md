# Native campaign evidence core

Manual Linux x86_64 stdlib Python (3.11+) campaign. The scoped execution below is measured; other machines and sources require their own run. Measurement doctrine: [accepted ADR-0012](../../docs/adr/0012-bench-doctrine.md).

- `require(cond, msg)` raises `ValueError`, including under optimized Python.
- `tree(path)` returns `{"entries": {...}, "sha256": "..."}`: descendant kinds/modes, file size/SHA-256, raw symlink targets and empty directories; the root is excluded. Unix descriptor-relative no-follow opens and stat checks reject observed changes. Root parents are trusted; this is not atomic source capture or an ABA-race guarantee. The manifest hash covers compact sorted-key UTF-8 entries JSON with `ensure_ascii=False`.
- `memo(stderr)` requires exactly one `lightr-json: ` row with exactly `key`/`hit`/`exit_code`, strict boolean/integer types, a lowercase 64-hex key and no duplicate fields.
- `verify_memo(row, expected_hit, expected_exit, expected_key=None, different_key=None)` checks metadata; output, process exit and execution counters remain caller checks.
- `coverage(rows, sizes, rounds, scenarios)` returns exact nonempty `(size, scenario, iteration)` samples; rows require `validated=True`, explicit setup/warmup/sample phases and zero-based iterations. Only samples count; rounds >=3.
- `summarize(values)` returns n/min/p50/nearest-rank p95/max/sample_stddev for >=3 finite numbers, with overflow-safe midpoint and finite outputs.

Controls: `python3 -B -m unittest discover -s benchmarks/native -p 'test_*.py' -v` (also with `-O`). Run `python3 benchmarks/native/campaign.py --binary PATH --source-dir PATH --source-sha SHA --build-receipt PATH --rounds N --warmups N --sizes INTEGERS --out DIR`; defaults 21 rounds, 2 warmups, `1000,10000`, minimum 3 rounds. The required duplicate-rejecting schema-1 receipt binds complete release build, clean source before/after, exact pinned Cargo argv/toolchain, paths and binary hash; metadata retains its content/hash plus a separate clean harness Git HEAD and campaign/evidence/deadline/commands SHA-256s. The trusted workflow is the build oracle, not cryptographic proof against a malicious owner. Eight serial size/scenario blocks cover snapshot cold/warm, hydrate, direct Python, native MISS/HIT, invalidation and failed commands; order is not randomized. The load1 gate is startup-only, not continual quiet-runner isolation. Each row marks overload from the maximum before/after load1/5/15 values versus logical CPUs; summaries count overloaded samples and retain every sample. Cold means fresh CAS/index/home, not OS-cache flush. Commands have a 120-second initial communication deadline plus separate 5-second recovery grace; only owned groups are killed, outputs retained, and recovery failures are explicit. No retries or expansion. Metadata/raw/commands JSON and byte logs retain provenance and validated phases; full coverage precedes JSON/Markdown summaries, exceptions retain failure.json and remove partial summaries. Cleanup is owned-case-only; upload JSON/JSONL and logs, not fixtures/CAS. Wall ns includes the GNU wrapper; GNU CPU seconds have 0.01-s display resolution and RSS is peak KiB, not summed memory. Setup/assertions are untimed. Native reproducibility only, no sandbox/Docker/VM factor claim.

## Measured execution: 2026-10-03

[Run 37136450654](https://github.com/gusmhs/hugr-lightr/actions/runs/37136450654) completed once, with 336 measured samples, 32 excluded warmups and 241 setup/probe commands. All 609 commands have retained stdout/stderr. The 24 controls ran on Linux; an independent artifact audit recomputed coverage, workload digests, memo key/counter relations and every summary statistic, with corruption controls. Hydrate acceptance checked whole-tree file bytes/modes, empty directory and raw symlink target; its measured rung was `copyrange`. Destination and counter files are not retained for post-hoc inspection.

- Product: `64db16ac29664ee9078f96b6f30ee9ca7b03174d`; harness: `4d02e4f865bf4f56a52d8dc3627a106f88624ef8`.
- Build: `cargo +1.96.0 build --locked --release --bin lightr`; binary SHA-256: `480f0eec14c5c289a92a999ea0a3b2d3422c8f010e0e02597aaf70fe9e288f12`. The binary is not included in the evidence artifact; identity is cross-checked through the trusted receipt and campaign metadata.
- Hardware: GitHub-hosted Microsoft-hypervisor VM, Intel Xeon Platinum 8573C, 4 logical CPUs / 2 cores, MemTotal 16,372,440 KiB. Ubuntu 24.04.5, kernel `6.17.0-1022-azure`, image `20260927.320.1`; filesystem reported `ext2/ext3`, 4096-byte blocks.
- Datasets: 1,000 / 10,000 unique 4096-byte files, plus empty directory and symlink. Workload reads one file and hashes its bytes 4096 times (16 MiB), identically for direct/native commands.
- Sampling: 21 samples and 2 warmups per dataset/scenario, serial blocks; no samples dropped. All measured rows were below the declared overload threshold; startup-only load gating does not prove continual host quietness.
- [Evidence artifact 11278854661](https://github.com/gusmhs/hugr-lightr/actions/runs/37136450654/artifacts/11278854661), retention 30 days; uploaded ZIP SHA-256: `3d975232977dc25242641d81761382fb3a5c518a0e8eaea69ba3dbc990f11b3a`. Includes receipt, hardware/goldens, raw/command JSONL, CPU/RSS/wall summaries and byte logs.

Wall times in **milliseconds**, each cell **median / nearest-rank p95 / sample standard deviation**:

| Scenario | 1,000 files | 10,000 files |
|---|---:|---:|
| snapshot-cold | 660.653 / 755.124 / 44.599 | 6891.064 / 7062.746 / 120.674 |
| snapshot-warm | 13.019 / 14.587 / 0.882 | 79.115 / 80.536 / 1.027 |
| hydrate | 21.051 / 21.705 / 0.393 | 181.373 / 183.703 / 1.072 |
| direct | 39.328 / 40.039 / 0.465 | 39.198 / 39.831 / 0.582 |
| memo-miss | 51.201 / 52.122 / 2.290 | 107.871 / 108.980 / 1.299 |
| memo-hit | 8.074 / 8.254 / 0.132 | 45.148 / 46.201 / 0.703 |
| input-invalidation | 48.631 / 51.610 / 2.602 | 85.584 / 88.319 / 1.261 |
| failed-command | 46.720 / 47.887 / 0.625 | 84.237 / 86.450 / 3.726 |

HIT avoided child execution, changed input produced a different-key MISS, and exit 7 was executed again rather than cached. With 10,000 inputs, HIT was slower than the direct baseline for this workload. These measurements establish neither Docker/VM superiority nor B1–B8 regression-budget enforcement or in-binary benchmark parity.

### Reproduce on Linux x86_64

Use a clean harness checkout at the recorded revision, Rust 1.96.0, GNU `/usr/bin/time`, and a separate frozen product worktree. `product`, receipt and output paths below must be new:

```sh
git worktree add --detach product 64db16ac29664ee9078f96b6f30ee9ca7b03174d
python3 benchmarks/native/preflight.py
python3 benchmarks/native/build.py --source-dir "$PWD/product" --source-sha 64db16ac29664ee9078f96b6f30ee9ca7b03174d --out "$PWD/native-build.json"
python3 benchmarks/native/campaign.py --binary "$PWD/product/target/release/lightr" --source-dir "$PWD/product" --source-sha 64db16ac29664ee9078f96b6f30ee9ca7b03174d --build-receipt "$PWD/native-build.json" --rounds 21 --warmups 2 --sizes 1000,10000 --out "$PWD/native-results"
```

## Cache calibration: parallel metadata candidate

[Same-runner A/B run 37156020089](https://github.com/gusmhs/hugr-lightr/actions/runs/37156020089)
compared baseline `1e9e022a7d899a70b3d2955f0669b21cfa9ffabc` with candidate
`df293e7ebfa322611e1c9434c67bdb33f7c4f412`. Both used clean locked Rust 1.96.0
release builds. Hardware: GitHub-hosted Linux x86_64, AMD EPYC 9V74, four logical
CPUs, Ubuntu 24.04.5, kernel `6.17.0-1022-azure`. These numbers compare variants
on this host, not against the earlier Xeon campaign.

The candidate preserves the sequential ignore-aware traversal and indexed result
order, using the existing Rayon pool for metadata queries on trees with at least
2048 selected paths. Small trees stay serial. Input/stat validation, manifest/key
formats and index publication remain; temporary path/metadata vectors cost memory.

Both variants ran 21 samples plus two warmups per size/scenario (126 measured
samples each), baseline blocks before candidate blocks, not randomized. All
samples were retained; none exceeded the declared overload threshold. The direct
Python workload is unchanged. Median / p95 wall time, **milliseconds**:

| Files / scenario | Baseline | Candidate |
|---|---:|---:|
| 1k direct | 32.674 / 33.112 | 32.849 / 33.111 |
| 1k MISS | 44.562 / 45.741 | 45.256 / 47.843 |
| 1k HIT | 8.227 / 8.345 | 8.096 / 8.411 |
| 10k direct | 33.065 / 33.850 | 33.222 / 35.207 |
| 10k MISS | 109.900 / 177.676 | 93.193 / 96.023 |
| 10k HIT | 49.537 / 50.960 | 31.933 / 34.690 |

10k HIT median improved 35.5%; its median peak RSS rose from 13,056 to 13,864 KiB.
The 1k MISS p95 rose 4.6%, within the predeclared 5% control limit. Full raw
distributions, including high-tail MISS samples, remain in the artifact; no
universal speedup or other-platform qualification follows from this run.

Untimed real-binary guards verified baseline-created cache replay by the candidate
and reverse replay, content/mode/symlink/explicit-env invalidation and repeated
exit-7 execution. Large-tree Rust controls also cover ignore rules, current modes,
raw link targets and racily-clean rehashing.

[Shared-path qualification 37156854301](https://github.com/gusmhs/hugr-lightr/actions/runs/37156854301)
subsequently completed all eight scenarios (336 samples) at source/harness
`25fd8bd0e7f59687d84aa0aa395c554f0cb8722a`, whose runtime matches the A/B candidate.
Independent artifact checks verified exact coverage, deterministic goldens,
memo/counters, raw logs and recomputed statistics with corruption controls.
This separate GitHub runner reported AMD EPYC 7763 / four logical CPUs; it is
functional/shared-path qualification, not a same-host comparison with the A/B.
[Artifact 11285618765](https://github.com/gusmhs/hugr-lightr/actions/runs/37156854301/artifacts/11285618765),
ZIP SHA-256 `8801fab3b07c8c188d51897816d0a9496267f95f905385fb4faee563d6bdc5d8`.

[Artifact 11285547335](https://github.com/gusmhs/hugr-lightr/actions/runs/37156020089/artifacts/11285547335):
ZIP SHA-256 `0012b26cbc3c7e22746bfbc5b52b163d22bf8cb713d00d1de6360d825c97d98a`.
Download while retained; build receipts, hardware, compatibility outputs, raw
samples, summaries and byte logs identify both exact variants.

To reproduce the reduced experiment, use a clean harness checkout at
`25fd8bd0e7f59687d84aa0aa395c554f0cb8722a` or a later revision with `--scenarios`.
Use the build/measurement commands above for each source in separate worktrees
on the same host; build both before timing,
then add `--scenarios direct,memo-miss,memo-hit` to each campaign invocation.
`--scenarios` defaults to all eight cases; an explicit subset must be nonempty,
known and unique. Metadata and exact sample coverage bind the selection.
Run `python3 benchmarks/native/compatibility.py --base BASE_BINARY --candidate
CANDIDATE_BINARY --out NEW_DIRECTORY` for the untimed guards. Existing source
receipts are historical evidence, not proof of a newly built candidate.
