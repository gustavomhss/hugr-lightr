"""Untimed real-binary old-store replay and invalidation guards for a native A/B."""
import argparse
import hashlib
import os
from pathlib import Path

from campaign import Campaign, WORK, fixture, write_json
from evidence import memo, require, verify_memo


def check(base, candidate, out):
    out = Path(out).absolute()
    out.mkdir()
    campaign = Campaign(argparse.Namespace(source_sha="compatibility-guard"), out)
    tree = out / "fixtures" / "data"
    fixture(tree, 2100)
    first, counter = tree / "file-00000000", out / "work" / "counter"
    env = campaign.environment(out / "work")
    child = [campaign.python, "-I", "-c", WORK, str(first), str(counter), "0"]
    expected_count, observations = 0, []

    def invoke(binary, hit, prior=None, changed=None, env_args=()):
        nonlocal expected_count
        row = campaign.command([binary, "--json", "run", "--engine", "native", "--dir", tree,
            "--input", tree, *env_args, "--", *child], env=env, cwd=tree, exit_code=int(child[-1]))
        parsed = memo(row["stderr"])
        verify_memo(parsed, hit, int(child[-1]), prior, changed)
        expected_count += not hit
        require(counter.read_bytes() == b"x" * expected_count, "compatibility child execution mismatch")
        require(row["stdout"] == hashlib.sha256(first.read_bytes() * 4096).hexdigest() + "\n", "compatibility output mismatch")
        campaign.accept(row)
        observations.append({"binary": str(binary), "memo": parsed, "counter": expected_count})
        return parsed["key"]

    key = invoke(base, False)
    invoke(candidate, True, prior=key)  # Actual existing baseline AC record, same path/argv/env.
    original = first.read_bytes()
    first.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    # Force a distinct mtime without filesystem-granularity assumptions.
    previous = first.stat().st_mtime_ns
    os.utime(first, ns=(previous + 1_000_000_000, previous + 1_000_000_000))
    key = invoke(candidate, False, changed=key)
    invoke(base, True, prior=key)  # Reverse compatibility: original consumes candidate AC.
    first.chmod(0o644)
    key = invoke(candidate, False, changed=key)
    (tree / "link").unlink()
    (tree / "link").symlink_to("file-00000001")
    key = invoke(candidate, False, changed=key)
    key = invoke(candidate, False, changed=key, env_args=("-e", "CALIBRATION=one"))
    invoke(base, True, prior=key, env_args=("-e", "CALIBRATION=one"))
    child[-1] = "7"
    failed = invoke(candidate, False)
    invoke(candidate, False, prior=failed)
    write_json(out / "compatibility.json", {"status": "complete", "observations": observations})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    check(str(Path(args.base).resolve()), str(Path(args.candidate).resolve()), args.out)
