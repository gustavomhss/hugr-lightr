"""Pure evidence helpers for the pending native campaign (ADR-0012)."""

import hashlib
import json
import math
import os
import re
import stat
import statistics

__all__ = ["require", "tree", "memo", "verify_memo", "coverage", "summarize"]


def require(cond, msg):
    """Raise an explicit error; validation must survive Python's -O flag."""
    if not cond:
        raise ValueError(msg)


def _state(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def tree(path):
    """Unix descriptor-relative descendants, raw links, modes and file hashes.

    Root parents are trusted. No-follow opens pin directories and file handles;
    stat checks reject observed changes, not all concurrent/ABA mutations.
    The root is excluded from compact sorted-key UTF-8 JSON manifest hashing.
    """
    root = os.fsdecode(path).rstrip("/") or "/"
    initial = os.stat(root, follow_symlinks=False)
    require(stat.S_ISDIR(initial.st_mode), f"not a directory: {root}")
    entries = {}

    def visit(directory, prefix):
        with os.scandir(directory) as iterator:
            names = sorted(child.name for child in iterator)
        for leaf in names:
            info = os.stat(leaf, dir_fd=directory, follow_symlinks=False)
            name = f"{prefix}/{leaf}" if prefix else leaf
            entry = {"mode": stat.S_IMODE(info.st_mode)}
            if stat.S_ISLNK(info.st_mode):
                entry.update(kind="symlink", target=os.readlink(leaf, dir_fd=directory))
            else:
                is_dir = stat.S_ISDIR(info.st_mode)
                require(is_dir or stat.S_ISREG(info.st_mode), f"unsupported fixture entry: {name}")
                flags = os.O_RDONLY | os.O_NOFOLLOW | (os.O_DIRECTORY if is_dir else os.O_NONBLOCK)
                child = os.open(leaf, flags, dir_fd=directory)
                try:
                    require(_state(os.fstat(child)) == _state(info), f"entry changed: {name}")
                    if is_dir:
                        entry.update(kind="dir")
                        visit(child, name)
                    else:
                        digest = hashlib.sha256()
                        for chunk in iter(lambda: os.read(child, 512 * 1024), b""):
                            digest.update(chunk)
                        entry.update(kind="file", size=info.st_size, sha256=digest.hexdigest())
                    require(_state(os.fstat(child)) == _state(info), f"entry changed: {name}")
                finally:
                    os.close(child)
            after = os.stat(leaf, dir_fd=directory, follow_symlinks=False)
            require(_state(after) == _state(info), f"entry changed: {name}")
            entries[name] = entry

    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        require(_state(os.fstat(descriptor)) == _state(initial), "root changed")
        visit(descriptor, "")
        require(_state(os.fstat(descriptor)) == _state(initial), "root changed")
        require(_state(os.stat(root, follow_symlinks=False)) == _state(initial), "root changed")
    finally:
        os.close(descriptor)
    entries = dict(sorted(entries.items()))
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return {"entries": entries, "sha256": hashlib.sha256(encoded).hexdigest()}


def _key(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _memo_row(row):
    require(isinstance(row, dict) and set(row) == {"key", "hit", "exit_code"},
            "memo row must contain exactly key, hit, exit_code")
    require(_key(row["key"]), "memo key must be 64 lowercase hex characters")
    require(type(row["hit"]) is bool, "memo hit must be a strict boolean")
    require(type(row["exit_code"]) is int, "memo exit_code must be a strict integer")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON field: {key}")
        result[key] = value
    return result


def memo(stderr):
    """Parse exactly one lightr-json row; other diagnostic lines are retained by caller."""
    require(isinstance(stderr, str), "memo stderr must be text")
    rows = [line for line in stderr.splitlines() if line.lstrip().startswith("lightr-json")]
    require(len(rows) == 1, "expected exactly one lightr-json row")
    require(rows[0].startswith("lightr-json: "), "malformed lightr-json prefix")
    row = json.loads(rows[0][len("lightr-json: "):], object_pairs_hook=_unique_object)
    _memo_row(row)
    return row


def verify_memo(row, expected_hit, expected_exit, expected_key=None, different_key=None):
    """Validate metadata; the caller must separately check output and execution counter."""
    _memo_row(row)
    require(type(expected_hit) is bool and type(expected_exit) is int,
            "invalid expected memo hit/exit")
    require(row["hit"] is expected_hit, "unexpected memo HIT/MISS")
    require(row["exit_code"] == expected_exit, "unexpected memo exit_code")
    for key in (expected_key, different_key):
        require(key is None or _key(key), "invalid expected memo key")
    require(expected_key is None or row["key"] == expected_key, "memo key mismatch")
    require(different_key is None or row["key"] != different_key, "memo key did not change")


def coverage(rows, sizes, rounds, scenarios):
    """Return exact (size, scenario, iteration) sample coverage or fail.

    Rows must declare phase setup/warmup/sample and validated=True. Setup and
    warmup rows do not count. Sample iterations are zero-based.
    """
    sizes, scenarios = list(sizes), list(scenarios)
    require(sizes and all(type(size) is int and size > 0 for size in sizes),
            "sizes must be nonempty positive integers")
    require(len(set(sizes)) == len(sizes), "duplicate sizes")
    require(type(rounds) is int and rounds >= 3, "rounds must be an integer >= 3")
    require(scenarios and all(isinstance(s, str) and s for s in scenarios),
            "scenarios must be nonempty names")
    require(len(set(scenarios)) == len(scenarios), "duplicate scenarios")
    expected = {(size, scenario, i) for size in sizes for scenario in scenarios
                for i in range(rounds)}
    seen = set()
    for row in rows:
        require(isinstance(row, dict), "coverage row must be an object")
        require(row.get("phase") in ("setup", "warmup", "sample"), "unknown/missing phase")
        require(row.get("validated") is True, "unvalidated command row")
        if row["phase"] != "sample":
            continue
        require(type(row.get("size")) is int and type(row.get("iteration")) is int
                and isinstance(row.get("scenario"), str), "malformed sample identity")
        identity = (row["size"], row["scenario"], row["iteration"])
        require(identity in expected, f"unexpected sample: {identity}")
        require(identity not in seen, f"duplicate sample: {identity}")
        seen.add(identity)
    require(seen, "empty measured coverage")
    require(seen == expected, f"missing samples: {sorted(expected - seen)}")
    return seen


def summarize(values):
    """Summarize >=3 finite numbers, retaining all samples and nearest-rank p95."""
    values = list(values)
    require(len(values) >= 3, "statistics require at least three values")
    require(all(type(v) in (int, float) and math.isfinite(v) for v in values),
            "statistics require finite numbers")
    values.sort()
    middle = values[len(values) // 2]
    if len(values) % 2 == 0:
        low, high = values[len(values) // 2 - 1:len(values) // 2 + 1]
        middle = low + (high - low) / 2 if (low >= 0) == (high >= 0) else (low + high) / 2
    try:
        result = {"n": len(values), "min": values[0], "p50": middle,
                  "p95": values[math.ceil(0.95 * len(values)) - 1], "max": values[-1],
                  "sample_stddev": statistics.stdev(values)}
    except OverflowError as error:
        raise ValueError("statistics results must be finite") from error
    require(all(math.isfinite(value) for value in result.values()), "statistics results must be finite")
    return result
