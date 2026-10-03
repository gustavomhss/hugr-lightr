"""Validate the trusted workflow's release receipt; this is not cryptographic attestation."""

import hashlib
import json
import re
import time
from pathlib import Path

from evidence import _unique_object, require


def validate_receipt(raw, source_dir, source_sha, binary, binary_sha256):
    receipt = json.loads(raw, object_pairs_hook=_unique_object)
    expected = {"schema": 1, "status": "complete", "source_sha": source_sha,
                "tracked_clean_before": True, "tracked_clean_after": True, "profile": "release",
                "argv": ["cargo", "+1.96.0", "build", "--locked", "--release", "--bin", "lightr"],
                "cwd": str(source_dir), "exit": 0, "binary": str(binary), "binary_sha256": binary_sha256}
    dynamic = {"cargo_version", "rustc_version", "started_unix_ns", "completed_unix_ns"}
    require(isinstance(receipt, dict) and set(receipt) == set(expected) | dynamic, "build receipt schema mismatch")
    require(re.fullmatch(r"[0-9a-f]{40}", source_sha) and re.fullmatch(r"[0-9a-f]{64}", binary_sha256),
            "invalid source/binary identities")
    require(Path(source_dir).is_absolute() and Path(binary).is_absolute(), "receipt paths must be absolute")
    for key, value in expected.items():
        require(type(receipt[key]) is type(value) and receipt[key] == value, f"build receipt mismatch: {key}")
    for tool in ("cargo", "rustc"):
        require(isinstance(receipt[tool + "_version"], str) and
                receipt[tool + "_version"].startswith(tool + " 1.96.0 "), f"build receipt toolchain mismatch: {tool}")
    started, completed = receipt["started_unix_ns"], receipt["completed_unix_ns"]
    require(type(started) is int and type(completed) is int and 0 < started <= completed <= time.time_ns(),
            "invalid build receipt timestamps")
    return receipt


def harness_identity(script, git_head, tracked_status):
    require(re.fullmatch(r"[0-9a-f]{40}", git_head), "invalid harness Git HEAD")
    require(not tracked_status, "tracked harness worktree is dirty")
    directory = Path(script).resolve().parent
    return {"git_sha": git_head, "tracked_clean": True, "repo_root": str(directory.parents[1]),
            "file_sha256": {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                            for name in ("campaign.py", "evidence.py", "deadline.py")}}
