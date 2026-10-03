"""Build a tracked-clean frozen source and retain release-profile provenance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from deadline import CleanupDeadline, execute


def require(condition, message):
    if not condition:
        raise ValueError(message)


def build(source, sha, output):
    output = Path(output).absolute()
    require(not output.exists(), "build receipt already exists")
    failure = Path(str(output) + ".failure.json")
    require(not failure.exists(), "build failure evidence already exists")
    env = {k: os.environ[k] for k in ("PATH", "HOME", "RUSTUP_HOME", "RUSTFLAGS") if k in os.environ}
    env.update(LC_ALL="C", CARGO_HTTP_MULTIPLEXING="false", GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL=os.devnull, CARGO_INCREMENTAL="0")
    state = {"source_sha": sha, "started_unix_ns": time.time_ns(), "stage": "preflight"}
    failure.write_text(json.dumps(state, indent=2) + "\n")
    receipt = None

    def command(argv):
        return subprocess.run(argv, cwd=source, env=env, check=True, capture_output=True,
                              text=True, timeout=30).stdout.strip()

    def clean():
        require(command(["git", "rev-parse", "HEAD"]) == sha, "build source HEAD mismatch")
        require(not command(["git", "status", "--porcelain", "--untracked-files=no"]), "tracked build source dirty")

    argv = ["cargo", "+1.96.0", "build", "--locked", "--release", "--bin", "lightr"]
    try:
        source = Path(source).resolve(strict=True)
        require(re.fullmatch(r"[0-9a-f]{40}", sha), "immutable source SHA required")
        clean()
        receipt = {"schema": 1, "source_sha": sha, "tracked_clean_before": True,
                   "profile": "release", "argv": argv, "cwd": str(source),
                   "cargo_version": command(["cargo", "+1.96.0", "--version"]),
                   "rustc_version": command(["rustc", "+1.96.0", "--version"]),
                   "started_unix_ns": state["started_unix_ns"], "status": "started"}
        require(receipt["cargo_version"].startswith("cargo 1.96.0 "), "pinned Cargo required")
        output.write_text(json.dumps(receipt, indent=2) + "\n")
        state["stage"] = "cargo"
        result = execute(argv, env, source, timeout_s=1200)
        Path(str(output) + ".stdout").write_bytes(result.stdout)
        Path(str(output) + ".stderr").write_bytes(result.stderr)
        print(result.stdout.decode(errors="replace"), end="")
        print(result.stderr.decode(errors="replace"), end="", file=sys.stderr)
        receipt["exit"] = result.returncode
        state.update(exit=result.returncode, timed_out=result.timed_out)
        require(not result.timed_out, "release build communication deadline exceeded")
        require(result.returncode == 0, "release build failed")
        state["stage"] = "postflight"
        clean()
        binary = source / "target/release/lightr"
        require(binary.is_file() and not binary.is_symlink(), "release binary missing")
        receipt.update(tracked_clean_after=True, binary=str(binary),
                       binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                       completed_unix_ns=time.time_ns(), status="complete")
    except BaseException as error:
        state.update(completed_unix_ns=time.time_ns(), status="failed",
                     error=str(error), error_type=type(error).__name__,
                     exit=getattr(error, "returncode", state.get("exit")),
                     deadline_error=isinstance(error, (subprocess.TimeoutExpired, CleanupDeadline)))
        for field in ("stdout", "stderr"):
            if hasattr(error, field):
                data = getattr(error, field) or b""
                Path(str(output) + ".failure." + field).write_bytes(data.encode() if isinstance(data, str) else data)
        failure.write_text(json.dumps(state, indent=2) + "\n")
        if receipt is not None:
            receipt["status"] = "failed"
        raise
    finally:
        if receipt is not None:
            output.write_text(json.dumps(receipt, indent=2) + "\n")
    failure.unlink()
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    build(args.source_dir, args.source_sha, args.out)
