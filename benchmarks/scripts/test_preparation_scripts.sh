#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
GIT_BIN=$(command -v git)
TMP=$(mktemp -d)

cleanup() {
    rm -rf "$TMP"
}
trap cleanup EXIT

fail() {
    printf 'test failure: %s\n' "$1" >&2
    exit 1
}

expect_failure() {
    if "$@"; then
        fail "command unexpectedly succeeded: $*"
    fi
}

ROOT="$TMP/root"
mkdir -p "$ROOT/benchmarks/scripts" "$ROOT/benchmarks/runner" "$ROOT/target/release"
for script in 00_verify_environment.sh 01_clone_repos.sh 02_extract_dockerfiles.sh 03_convert_to_lightr.sh 04_build_runner.sh 05_dry_run.sh 06_full_suite.sh verify_hashes.sh; do
    cp "$SCRIPT_DIR/$script" "$ROOT/benchmarks/scripts/$script"
done

"$GIT_BIN" init -q "$ROOT"
"$GIT_BIN" -C "$ROOT" config user.email benchmark@example.test
"$GIT_BIN" -C "$ROOT" config user.name benchmark-test
mkdir -p "$ROOT/fixtures/present"
printf 'fixture\n' > "$ROOT/fixtures/present/data.txt"
"$GIT_BIN" -C "$ROOT" add fixtures
"$GIT_BIN" -C "$ROOT" commit -qm fixture
LOCAL_COMMIT=$("$GIT_BIN" -C "$ROOT" rev-parse HEAD)

REMOTE_SOURCE="$TMP/remote-source"
REMOTE_BARE="$TMP/remote.git"
"$GIT_BIN" init -q "$REMOTE_SOURCE"
"$GIT_BIN" -C "$REMOTE_SOURCE" config user.email benchmark@example.test
"$GIT_BIN" -C "$REMOTE_SOURCE" config user.name benchmark-test
printf 'remote\n' > "$REMOTE_SOURCE/file.txt"
"$GIT_BIN" -C "$REMOTE_SOURCE" add file.txt
"$GIT_BIN" -C "$REMOTE_SOURCE" commit -qm remote
REMOTE_COMMIT=$("$GIT_BIN" -C "$REMOTE_SOURCE" rev-parse HEAD)
"$GIT_BIN" -C "$REMOTE_SOURCE" tag -a v1 -m v1
REMOTE_TAG=$("$GIT_BIN" -C "$REMOTE_SOURCE" rev-parse refs/tags/v1)
"$GIT_BIN" init -q --bare "$REMOTE_BARE"
"$GIT_BIN" -C "$REMOTE_SOURCE" remote add origin "$REMOTE_BARE"
"$GIT_BIN" -C "$REMOTE_SOURCE" push -q origin HEAD:main refs/tags/v1

printf '%s\n' \
    'source_evidence:' \
    '  projects:' \
    '  - id: local-fixture' \
    '    repo: local' \
    "    commit: $LOCAL_COMMIT" \
    '  - id: remote-fixture' \
    "    repo: $REMOTE_BARE" \
    '    tag: v1' \
    "    raw_tag_object: $REMOTE_TAG" \
    "    peeled_commit: $REMOTE_COMMIT" \
    'scenarios:' \
    '- id: supported-fixture' \
    '  availability: supported' \
    '  fixture:' \
    '    project: local-fixture' \
    '    path: fixtures/present' \
    > "$ROOT/benchmarks/benchmark-spec.yaml"

BIN="$TMP/bin"
mkdir -p "$BIN"
printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'case "$*" in' \
    "  'version --format {{.Client.Version}}') printf '28.3.2\\n' ;;" \
    "  'version --format {{.Server.Version}}') printf '28.3.2\\n' ;;" \
    "  *) printf 'unexpected docker arguments: %s\\n' \"\$*\" >&2; exit 1 ;;" \
    'esac' \
    > "$BIN/docker"
chmod +x "$BIN/docker"
printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'printf "%s\\n" "$*" >> "${CARGO_LOG:?}"' \
    'if [[ "$PWD" == */benchmarks/runner ]]; then' \
    '  mkdir -p target/release' \
    "  printf '%s\\n' '#!/usr/bin/env bash' 'printf \"%s\\n\" \"\$*\" >> \"\${RUNNER_LOG:?}\"' > target/release/bench-runner" \
    '  chmod +x target/release/bench-runner' \
    'else' \
    '  mkdir -p target/release' \
    "  printf '%s\\n' '#!/usr/bin/env bash' 'exit 0' > target/release/lightr" \
    '  chmod +x target/release/lightr' \
    'fi' \
    > "$BIN/cargo"
chmod +x "$BIN/cargo"

export GIT_BIN
export CARGO_BIN="$BIN/cargo"
export CARGO_LOG="$TMP/cargo.log"
export DOCKER_BIN="$BIN/docker"
export RUNNER_LOG="$TMP/runner.log"

bash "$ROOT/benchmarks/scripts/00_verify_environment.sh"
bash "$ROOT/benchmarks/scripts/verify_hashes.sh"

cp "$ROOT/benchmarks/benchmark-spec.yaml" "$TMP/spec.good"
perl -0pi -e 's/raw_tag_object: [0-9a-f]+/raw_tag_object: deadbeef/' "$ROOT/benchmarks/benchmark-spec.yaml"
expect_failure bash "$ROOT/benchmarks/scripts/verify_hashes.sh"
mv "$TMP/spec.good" "$ROOT/benchmarks/benchmark-spec.yaml"
bash "$ROOT/benchmarks/scripts/verify_hashes.sh"

bash "$ROOT/benchmarks/scripts/01_clone_repos.sh"
[[ $("$GIT_BIN" -C "$ROOT/benchmarks/work/repos/remote-fixture" rev-parse HEAD) == "$REMOTE_COMMIT" ]] || fail 'clone did not checkout peeled commit'

cp "$ROOT/benchmarks/benchmark-spec.yaml" "$TMP/spec.good"
perl -0pi -e 's#path: fixtures/present#path: fixtures/absent#' "$ROOT/benchmarks/benchmark-spec.yaml"
expect_failure bash "$ROOT/benchmarks/scripts/02_extract_dockerfiles.sh"
mv "$TMP/spec.good" "$ROOT/benchmarks/benchmark-spec.yaml"
bash "$ROOT/benchmarks/scripts/02_extract_dockerfiles.sh"

bash "$ROOT/benchmarks/scripts/03_convert_to_lightr.sh"
printf '[workspace]\n' > "$ROOT/benchmarks/runner/Cargo.toml"
bash "$ROOT/benchmarks/scripts/04_build_runner.sh"
if ! grep -Fqx -- 'build --bin lightr --release' "$CARGO_LOG"; then
    fail 'lightr CLI build command changed'
fi
if ! grep -Fqx -- 'build --release' "$CARGO_LOG"; then
    fail 'runner build command changed'
fi
CHUNK=2 TOTAL_CHUNKS=7 bash "$ROOT/benchmarks/scripts/05_dry_run.sh"
CHUNK=6 TOTAL_CHUNKS=7 ROUNDS=9 bash "$ROOT/benchmarks/scripts/06_full_suite.sh"
if ! grep -F -- '--chunk 2 --chunks 7 --rounds 3' "$RUNNER_LOG" >/dev/null; then
    fail 'dry run did not execute selected chunk'
fi
if ! grep -F -- '--chunk 6 --chunks 7 --rounds 9' "$RUNNER_LOG" >/dev/null; then
    fail 'full suite did not execute selected chunk'
fi

printf 'preparation script tests passed\n'
