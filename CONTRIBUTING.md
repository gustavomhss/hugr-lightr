# Contributing to HuGR Lightr

## Toolchain

`rust-toolchain.toml` pins **Rust 1.96.0** — rustup installs it on demand.
No other toolchain is supported for CI-relevant work.

## Build & test

```
cargo build --release            # single binary: target/release/lightr
cargo build --release --features vz   # + the macOS Virtualization.framework engine
cargo build --workspace          # debug bin (acceptance tests exec target/debug/lightr)
cargo test --workspace           # full suite
```

## The gates (must be green before merge)

Run locally with `scripts/gate.sh`, or individually:

```
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

CI (`.github/workflows/ci.yml`) additionally enforces:

- **Godfile guard:** no source `.rs` file may exceed **400 LOC**
  (examples/tests directories excluded — see the workflow for the exact
  filter). If your change pushes a file over, split it into cohesive
  modules; don't ask for an exemption.
- **Windows cross-clippy** (`--target x86_64-pc-windows-gnu -D warnings`) —
  catches cfg-gated dead code on the platform you didn't build.

## Integration and aggregate gate

The same `.github/workflows/ci.yml` runs for PRs targeting `main` and
`fix/snapshot-integrity`. `Required CI` fails unless all nine mandatory job
results are exactly `success`; a failed, skipped, cancelled or missing job is
not acceptance. The intentionally disabled release job is not a verification
job and remains outside this aggregate. Existing native/campaign controls are
additional evidence, not a substitute for the complete CI configuration.

The integration branch requires `Required CI` from GitHub Actions, strict
up-to-date checks and administrator enforcement. Never bypass this rule,
remove a failing target, suppress warnings, or merge from old check results.
Read the exact PR head and tested merge before integration; confirm the parent
PR's new checks afterwards. An in-scope repair PR may fix an already-red
integration branch only after the repair candidate's full gates succeed.

Reproduce the Windows cross-check with the pinned compiler:

```sh
RUSTFLAGS="-D warnings" cargo +1.96.0 check --locked --workspace --target x86_64-pc-windows-gnu
python3 -m unittest discover -s scripts/ci -p 'test_*.py' -v
```

## The ADR rule

Code is written **only against Accepted ADRs** (`docs/adr/`). If your change
embodies a new architectural decision — a new engine, seam, on-disk format,
dependency posture — write the ADR first and get it Accepted. A PR that
smuggles in an undecided decision will be closed, however good the code.

## The tense law (for any doc, comment, or commit that states a number)

A performance/footprint/benchmark number may be stated **only** if it was
actually measured, and it must carry its run context (named hardware or the
public CI runner) plus a reproduce path. The measured ledgers are
`docs/benchmarks/RESULTS.md` (Linux, CI) and `docs/spec/benchmark-results.md`
(macOS, Intel box). Anything not yet measured is an explicit **target**,
cited to its precedent — never phrased as a measurement. Absent competitors
in comparisons print SKIP, never a fabricated number.

## Fail-closed

Unsupported paths return an honest error; they never silently degrade,
no-op, or fabricate success. If you can't enforce a flag on an engine,
error — don't ignore it. `docs/spec/parity-audit.md` is the truth ledger;
if your change affects a row, update the row in the same PR.

## PR expectations

- Integrate one cohesive change with its tests and documentation; do not open
  separate PRs for each helper or review correction. Use directed tests and a
  warmed build during iteration, then resolve cold review before activating the
  full merge-candidate CI. Changed candidates still require fresh checks.
- `benchmark-evidence` runs on PRs, main pushes and manual dispatch, not feature
  branch pushes. Updated PRs cancel superseded runs of the same workflow/PR;
  main and manual executions remain independent. Cancelled old heads are not
  green qualification for the current candidate.

- Branch → PR → merge; gates green before merge. Keep PRs scoped to one
  concern.
- Say **what** changed and **why** (link the ADR/issue/parity row).
- New behavior comes with a test that fails without the change.
- English, lean, evidence-cited. Commits use `Co-Authored-By` trailers where
  applicable.

The current ARM macOS runner is separate from the pinned Intel runner. Both
remain required, alongside the earlier ARM baseline; changing a job label must
not silently remove coverage of an environment that produced a real failure.
A single documented `expect` at the Windows-only temporary cleanup statement
acknowledges Clippy's Unix-specific readonly warning. It does not compile on
Unix, change global lint policy or add a native permission-manipulation API.

See the official platform distinction in
[Permissions::set_readonly](https://doc.rust-lang.org/std/fs/struct.Permissions.html#method.set_readonly).
The exact socket witness runs via Cargo with `--features vz`, records the
executable hash and every iteration, and stops on its first failure. It is
not a retry-until-success rule or an explanation of an older intermittent fault.

macOS CI keeps `-D warnings` AND the repository's Swift runtime rpath:
`RUSTFLAGS="-D warnings -C link-arg=-Wl,-rpath,/usr/lib/swift"`.
Cargo's environment RUSTFLAGS replaces target rustflags; omitting the latter
can compile a vz test executable which then fails before test enumeration.

CI caches registry data and target outputs only, never ~/.cargo/bin. Keys must
include OS, architecture, job/target and the pinned toolchain/configuration, so
an ARM runner cannot replace the Intel runner's toolchain executable. No old-key
fallback is used by the repaired workflow.
