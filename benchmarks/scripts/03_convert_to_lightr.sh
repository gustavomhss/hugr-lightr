#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
: "${CARGO_BIN:?set CARGO_BIN to an absolute cargo binary path}"

case "$CARGO_BIN" in
    /*) ;;
    *) printf 'CARGO_BIN must be an absolute path: %s\n' "$CARGO_BIN" >&2; exit 1 ;;
esac
if [[ ! -x "$CARGO_BIN" ]]; then
    printf 'CARGO_BIN is not executable: %s\n' "$CARGO_BIN" >&2
    exit 1
fi

cd "$ROOT"
"$CARGO_BIN" build --bin lightr --release
if [[ ! -x "$ROOT/target/release/lightr" ]]; then
    printf 'lightr-cli build produced no executable: %s\n' "$ROOT/target/release/lightr" >&2
    exit 1
fi
