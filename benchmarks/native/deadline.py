"""Fixed communication deadlines for owned Unix process groups."""

import math
import os
import signal
import subprocess
import time
from collections import namedtuple
from subprocess import Popen

from evidence import require

_Outcome = namedtuple("Outcome", "pid returncode stdout stderr timed_out group_gone")
RECOVERY_S = 5


class CleanupDeadline(RuntimeError):
    """Recovery exhausted its grace; retained bytes and leader status are attached."""


def _close_pipes(child):
    for pipe in (child.stdout, child.stderr):
        if pipe is not None:
            pipe.close()


def _recover(child):
    deadline = time.monotonic() + RECOVERY_S
    group_gone, problem = False, None
    stdout, stderr = b"", b""
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        group_gone = True
    except BaseException as error:
        problem = error
    kill_error = problem
    try:
        stdout, stderr = child.communicate(timeout=max(0, deadline - time.monotonic()))
    except BaseException as error:
        problem = error
        stdout, stderr = getattr(error, "output", None) or b"", getattr(error, "stderr", None) or b""
    try:
        _close_pipes(child)
    except BaseException as error:
        problem = error
    try:
        child.wait(timeout=max(0, deadline - time.monotonic()))
    except BaseException as error:
        problem = error
    if problem is not None:
        expired = isinstance(problem, subprocess.TimeoutExpired)
        failure = CleanupDeadline(f"command cleanup deadline exceeded after {RECOVERY_S}s (pid={child.pid})") \
            if expired else RuntimeError(f"command cleanup failed (pid={child.pid}): {problem}")
        failure.pid, failure.returncode = child.pid, child.returncode
        failure.stdout, failure.stderr = stdout, stderr
        failure.kill_error = kill_error
        raise failure from problem
    return stdout, stderr, group_gone


def execute(argv, env, cwd, timeout_s=120):
    """Initial communication deadline defaults to 120s; recovery has a separate 5s grace.

    Kill only the owned group, close pipes and bound reaping; no implicit context
    manager wait. Trusted foreground workloads, not an adversarial sandbox.
    Interrupt/errors retain available bytes on the original exception. Escaped
    pipe holders cause CleanupDeadline, not an unbounded drain or wider kill.
    """
    require(type(timeout_s) in (int, float) and math.isfinite(timeout_s) and timeout_s > 0,
            "command deadline must be finite and positive")
    timed_out, group_gone = False, False
    child = Popen(argv, env=env, cwd=cwd, stdout=subprocess.PIPE,
                  stderr=subprocess.PIPE, umask=0o022, start_new_session=True)
    try:
        try:
            stdout, stderr = child.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            stdout, stderr, group_gone = _recover(child)
        except BaseException as original:
            try:
                stdout, stderr, group_gone = _recover(child)
            except BaseException as cleanup:
                original.stdout = getattr(cleanup, "stdout", b"")
                original.stderr = getattr(cleanup, "stderr", b"")
                original.pid, original.returncode = child.pid, child.returncode
                original.add_note(f"owned-group recovery failed: {cleanup}")
                raise original from cleanup
            original.stdout, original.stderr = stdout, stderr
            original.pid, original.returncode = child.pid, child.returncode
            raise
    finally:
        _close_pipes(child)
    return _Outcome(child.pid, child.returncode, stdout, stderr, timed_out, group_gone)
