"""Command evidence survives owned-group execution exceptions before acceptance."""
import json
import math
import os
from pathlib import Path
import time
from types import SimpleNamespace

from deadline import CleanupDeadline, execute
from evidence import require

TIME = "/usr/bin/time"
USAGE = '{"user_s":%U,"system_s":%S,"max_rss_kib":%M,"exit":%x}'


def append(path, row):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")


class Commands:
    """Mixin requiring campaign out/context/sequence/env/meta/args/python fields."""

    def command(self, argv, phase="setup", timed=False, env=None, exit_code=0, cwd=None, timeout_s=120):
        argv = list(map(str, argv))
        require(argv and Path(argv[0]).is_absolute(), "command needs an absolute executable")
        self.sequence += 1
        prefix = self.out / "logs" / f"{self.sequence:06d}"
        usage = prefix.with_suffix(".usage")
        actual = [TIME, "-q", "-f", USAGE, "-o", str(usage), "--", *argv] if timed else argv
        before, start, failure = os.getloadavg(), time.perf_counter_ns(), None
        try:
            result = execute(actual, env or self.env, cwd or self.out / "work", timeout_s)
        except BaseException as error:
            failure = error
            result = SimpleNamespace(stdout=getattr(error, "stdout", b""), stderr=getattr(error, "stderr", b""),
                pid=getattr(error, "pid", None), returncode=getattr(error, "returncode", None),
                timed_out=isinstance(error, CleanupDeadline), group_gone=None)
        wall, after = time.perf_counter_ns() - start, os.getloadavg()
        def persist(action):
            try:
                return action()
            except BaseException as error:
                if failure is None:
                    raise
                failure.add_note(f"command evidence persistence failed: {type(error).__name__}: {error}")
        persist(lambda: prefix.with_suffix(".stdout").write_bytes(result.stdout))
        persist(lambda: prefix.with_suffix(".stderr").write_bytes(result.stderr))
        row = {**self.context, "phase": phase, "timed": timed, "validated": False,
               "command_id": self.sequence, "argv": argv, "executed_argv": actual,
               "exit": result.returncode, "stdout": result.stdout.decode("utf-8", "backslashreplace"),
               "stderr": result.stderr.decode("utf-8", "backslashreplace"), "pid": result.pid,
               "timed_out": result.timed_out, "timeout_s": timeout_s, "group_gone_on_kill": result.group_gone,
               "exit_class": "interrupt" if isinstance(failure, KeyboardInterrupt) else
                   "cleanup_failure" if isinstance(failure, CleanupDeadline) else
                   "execution_error" if failure is not None else "deadline" if result.timed_out else "process",
               "source_sha": self.args.source_sha, "binary_sha256": self.meta.get("binary_sha256"),
               "mode": "direct" if argv[0] == self.python else "native" if argv[0] ==
                       str(getattr(self, "binary", None)) else "setup", "cwd": str(cwd or self.out / "work"),
               "env": env or self.env, "umask": "022", "load_before": before, "load_after": after,
               "overloaded": max((*before, *after)) > (self.meta.get("logical_cpus") or os.cpu_count()),
               "logs_prefix": str(prefix.relative_to(self.out))}
        if failure is not None:
            row.update(error=str(failure), error_type=type(failure).__name__)
        if timed:
            row.update(wall_ns=wall, usage_text=persist(lambda: usage.read_text(errors="backslashreplace") if usage.is_file() else None))
        persist(lambda: append(self.out / "commands.jsonl", row))
        if failure is not None:
            raise failure
        require(not result.timed_out, f"command {self.sequence} deadline exceeded after {timeout_s}s")
        if timed:
            metrics = json.loads(row["usage_text"] or "null")
            require(isinstance(metrics, dict) and set(metrics) ==
                    {"user_s", "system_s", "max_rss_kib", "exit"}, "invalid GNU-time usage")
            require(type(metrics["max_rss_kib"]) is int and metrics["max_rss_kib"] >= 0
                    and type(metrics["exit"]) is int and metrics["exit"] == result.returncode,
                    "invalid GNU-time RSS/exit")
            require(all(type(metrics[k]) in (int, float) and math.isfinite(metrics[k])
                        and metrics[k] >= 0 for k in ("user_s", "system_s")), "invalid CPU usage")
            row.update({k: metrics[k] for k in ("user_s", "system_s", "max_rss_kib")})
        require(result.returncode == exit_code, f"unexpected exit for command {self.sequence}")
        return row
