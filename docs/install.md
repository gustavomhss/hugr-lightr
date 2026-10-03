# Installing Lightr

Lightr is a single static binary — `lightr` — with no daemon and no runtime
services. "Install" means: get the binary onto your `PATH`, and (only if you
want to run Linux containers in a microVM on macOS) install one Linux pack and
codesign the binary with the virtualization entitlement.

> **Migration and release status.** Active development and delivery moved to
> [gusmhs/hugr-lightr](https://github.com/gusmhs/hugr-lightr); historical commits,
> authors, and receipts keep their original identities. Historical **0.1.1 was
> published** ([R4 receipt](plans/unix-first-go-live/evidence/R4-public-release.md)),
> but **still has the native `-e` bug**: explicit environment values are keyed but
> not applied to the foreground child. The source fix is on `main`
> ([ADR-0023](adr/0023-native-explicit-env-cache.md)); **0.1.2 qualification is
> pending**. Identical 0.1.1 GitHub assets are restored under the new repo; five
> anonymous downloads matched original hashes (release 402204175). Build from `main` for
> the fix; `cargo install hugr-lightr --version 0.1.1 --locked` still selects the
> historical package, not the fix. Public artifact support remains Linux x86_64
> and macOS arm64 only; macOS artifacts remain unsigned/ad-hoc, not notarized,
> and packaged VZ remains unvalidated. See [packaging](../packaging/README.md)
> and the platform matrix below.

---

## Prerequisites

- **Rust toolchain.** The repo pins its toolchain in
  [`rust-toolchain.toml`](../rust-toolchain.toml); `rustup` reads it
  automatically when you build inside the repo. If you do not have `rustup`,
  install it from <https://rustup.rs>.
- **Git**, to clone the repo.
- **(macOS, `vz` engine only)** Apple's Virtualization.framework (built into
  macOS) plus the ability to ad-hoc codesign (`codesign`, ships with Xcode
  command-line tools). Building the Linux pack additionally needs a Linux
  cross-toolchain / Docker — see [`docs/build.md`](build.md).

---

## Install from source

Clone the active repository, then build from its root:

```sh
git clone https://github.com/gusmhs/hugr-lightr
cd hugr-lightr

# Build the release binary (all engines except vz):
cargo build --release --bin lightr

# The binary lands at:
#   target/release/lightr
```

Put it on your `PATH` (pick one):

```sh
# Option A — symlink into a dir already on PATH
ln -sf "$(pwd)/target/release/lightr" /usr/local/bin/lightr

# Option B — copy it
cp target/release/lightr /usr/local/bin/lightr
```

Verify:

```sh
lightr --version
# Expected source version: lightr 0.1.1 (<git-sha>, <build-date>)
```

`--version` embeds the git SHA and build date so you always know exactly which
commit a binary came from.

### Enabling the Linux-container engine on macOS (`--features vz`)

The `vz` engine — which boots a real Linux microVM via Apple's
Virtualization.framework — is behind a Cargo feature. Build with it on:

```sh
cargo build --release --bin lightr --features vz
```

On macOS the `vz` binary needs the virtualization entitlement to talk to the
hypervisor. Ad-hoc codesign it with the entitlements file shipped in the repo:

```sh
codesign --entitlements packaging/vz.entitlements -s - target/release/lightr
```

The entitlements file is [`packaging/vz.entitlements`](../packaging/vz.entitlements);
it grants exactly one key, `com.apple.security.virtualization`. The `-s -`
performs an **ad-hoc** signature, which is sufficient for local development. A
Developer ID signature and notarization are separate from the explicitly
unsigned ad-hoc artifact permitted by [release policy](RELEASE.md#signing-policy).

> Without this codesign step, a `--features vz` binary will fail to start a VM
> on macOS (the hypervisor denies the unentitled process).

---

## The Linux pack (for the `vz` engine)

The `vz` engine boots a **pack**: a Linux `kernel` plus an `initrd` whose
`/init` is Lightr's guest PID 1 (`lightr-init`), plus a `pack.json` manifest.
Build one with the bundled recipe:

```sh
scripts/build-linux-pack.sh [--out <dir>] [--arch aarch64|x86_64]
```

This assembles `<out>/kernel`, `<out>/initrd`, and `<out>/pack.json`. The
kernel source is named and pinned in the script (mainline Linux tracked
against Apple's Containerization config). If a required cross-toolchain is
missing, the script detects it, prints the exact fix, and exits non-zero — it
never fabricates a kernel.

> See [`docs/build.md`](build.md) for the full kernel/init build details,
> including the no-Docker arm64 path using Apple's prebuilt Containerization
> kernel.

Register the pack into your Lightr home directory:

```sh
lightr engine install-pack <dir>
# → installed linux pack → ~/.lightr/packs/linux
```

`install-pack` structurally validates the pack (the `initrd` must be a real
cpio with an executable `/init`, the `kernel` must be non-empty) before copying
it to `~/.lightr/packs/linux/`. A malformed pack is rejected loudly.

Confirm the engine sees it:

```sh
lightr engine ls
# native    available     native process execution (no isolation — not a sandbox)
# ns        unavailable   ns engine requires Linux (this host is macos)
# vz        available     vz engine ready (pack: ~/.lightr/packs/linux)
# wsl       unavailable   wsl engine requires Windows + WSL2 (this host is macos)
```

`engine ls` probes each engine honestly and reports its real availability and
reason. Then:

```sh
lightr run --engine vz --rootfs @docker/alpine -- /bin/sh -c 'exit 7'
# → exits 7 (the REAL guest exit code, returned over the file channel)
```

---

## Shell completions and the man page

Lightr can print a completion script for your shell to stdout, and a roff man
page:

```sh
# Completions (bash | zsh | fish | powershell | elvish):
lightr completions zsh  > ~/.zfunc/_lightr          # zsh example
lightr completions bash > /usr/local/etc/bash_completion.d/lightr

# Man page:
lightr man > /usr/local/share/man/man1/lightr.1
```

Adjust the destination to wherever your shell / `man` looks. Both are generated
from the live CLI definition, so they never drift from the actual flags.

---

## Verify the install

```sh
lightr --version          # prints version + git-sha + build-date
lightr --help             # top-level command list + examples
lightr engine ls          # which execution engines are available here
```

Nothing runs in the background after any of these — Lightr is daemonless
(`pgrep lightr` returns nothing between invocations).

---

## Data directory

Lightr keeps all state under a single home directory:

- Default: `~/.lightr`
- Override: set the **`LIGHTR_HOME`** environment variable to any path.

Inside it you will find `store/` (the content-addressed store), `index/`,
`run/` (per-run directories: logs, control files), `packs/` (installed Linux
packs), `compose/` (compose stacks), and `units/` (generated supervisor units,
once you use `supervise install`). Deleting `~/.lightr` resets Lightr
completely.

---

## Platform support matrix (honest)

One codebase targets every desktop; the isolation engine differs per platform.
"Compiles + cross-checks clean" is **not** the same as "runtime validated" —
this table mirrors `docs/spec/parity-audit.md` ("Platform coverage") and marks
each tier exactly.

| Platform | Core (CAS / run / build) | Isolation engine | Runtime validated? |
|---|---|---|---|
| **macOS Intel x86_64** | ✅ | `vz` (x86_64 guest) | ✅ **runtime-validated end-to-end** (F-205/F-206, Intel i7-9750H, macOS 15.3.2) |
| macOS Apple Silicon | ✅ (same code) | `vz` (arm64 guest) | 🟡 **not validated** — code-complete; runbook at `spikes/s5-vz-boot-arm64/` |
| **Linux x86_64** | ✅ (same code) | `ns` (namespaces) | ✅ **runtime-validated on GitHub-hosted Linux CI** — cold-start benchmark (~30.8 ms, ~4.05× vs rootless podman, same isolation) + net-namespace isolation (`docs/benchmarks/RESULTS.md`) |
| Linux aarch64 | ✅ (same code) | `ns` | 🟡 **not validated** — same code as x86_64 (validated); aarch64 CI cross-check gated |
| Windows x86_64 | 🟡 code-complete | `wsl` (ns inside WSL2) | 🟡 **not validated** — code-complete; runbook (Windows box) gated |

**Read this literally:** runtime evidence below is not a public release-support
claim. The **macOS Intel x86_64 `vz`** path and the **Linux
x86_64 `ns`** path are both run end-to-end and proven (the latter on public
GitHub-hosted Linux CI). Apple Silicon `vz`, Linux **aarch64** `ns`, and Windows
`wsl` are written and compile/cross-check clean, with runbooks under `spikes/`,
but are **hardware-gated and not claimed validated**. Note: rootless `ns` is
**not** a hostile-tenant boundary (use `vz`/`fc`). The daemonless core (store,
memoized `run`/`build`, OCI import, time-axis verbs, compose, docker compat,
agent surface) is the same code on every platform and is fully tested.

---

## Distribution channels (historical 0.1.1; migration in progress)

- **Homebrew** — formula at [`packaging/lightr.rb`](../packaging/lightr.rb)
  selects the exact historical 0.1.1 URLs/hashes under the new repo. Formula
  metadata evaluation is not evidence of an actual Homebrew install.
- **`curl | sh` installer** — [`packaging/install.sh`](../packaging/install.sh)
  selects 0.1.1 under the new repo and verifies the matching artifact checksum.
  Both installer and formula select restored identical historical assets.
- **crates.io** — the eleven intended 0.1.1 packages were published
  ([publication receipt](plans/unix-first-go-live/evidence/R4-crates-publication.md));
  the CLI package is `hugr-lightr`, binary `lightr`. Published 0.1.1 is unchanged.
- **GitHub Releases** — [v0.1.1](https://github.com/gusmhs/hugr-lightr/releases/tag/v0.1.1)
  contains restored original bytes, not a rebuilt bug fix.
  Public artifacts remain Linux x86_64 and macOS arm64 only; the macOS artifact
  is explicitly `-unsigned` (ad-hoc, no Developer ID, not notarized).

For the native explicit-env fix, **build from `main`** as above. No 0.1.2 release
is qualified by this migration. Future publication requires separate qualification
and owner authorization; see [`docs/RELEASE.md`](RELEASE.md).
