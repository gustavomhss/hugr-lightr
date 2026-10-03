import contextlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from deadline import CleanupDeadline, execute

PYTHON = str(Path(sys.executable).resolve())
FAMILY = """import json, os, subprocess, sys, time
from pathlib import Path
root = Path(sys.argv[-1]).parent
escape, stay = sys.argv[1:3]
child = subprocess.Popen([sys.executable, '-I', '-c', 'import signal\\nwhile True: signal.pause()'], start_new_session=escape == 'yes')
(root / 'identity.json').write_text(json.dumps({'leader': os.getpid(), 'child': child.pid, 'escape': escape == 'yes'}))
print(os.getpgrp(), child.pid, flush=True)
print('retained stderr', file=sys.stderr, flush=True)
Path(sys.argv[-1]).touch()
if stay == 'no': os._exit(0)
while True: time.sleep(3600)
"""


def process_state(pid):
    result = subprocess.run(['/bin/ps', '-o', 'stat=', '-p', str(pid)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
    if result.returncode == 1 and not result.stdout:
        return "gone"
    if result.returncode != 0 or not result.stdout.strip():
        raise AssertionError(f"cannot observe process {pid}: {result.stderr!r}")
    return result.stdout.decode().strip()


def kill_group(pid):
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return "already gone"
    except PermissionError:
        state = process_state(pid)
        if state == "gone" or state.startswith("Z"):
            return f"not signalable: {state}"
        raise
    return "SIGKILL sent"


@contextlib.contextmanager
def coordinate(root, parent_delay=0, interrupt=False):
    """Real readiness, independent watchdog, and finally cleanup of owned controls."""
    ready, started, children = root / "ready", [], []
    real_popen = subprocess.Popen
    old_handler = signal.getsignal(signal.SIGALRM)

    def alarm(signum, frame):
        raise AssertionError("independent process-control watchdog expired")

    signal.signal(signal.SIGALRM, alarm)
    watchdog = real_popen([PYTHON, '-I', '-c',
        'import os,signal,time; parent=os.getppid(); time.sleep(12); '
        'os.kill(parent,signal.SIGALRM) if os.getppid()==parent else None'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    timer = None

    def spawning(argv, **kwargs):
        nonlocal timer
        child = real_popen([*argv, str(ready)], **kwargs)
        children.append(child)
        deadline = time.monotonic() + 8
        while not ready.exists():
            if child.poll() is not None or time.monotonic() >= deadline:
                raise AssertionError("control child did not signal readiness")
            time.sleep(0.01)
        time.sleep(parent_delay)
        started.append(time.monotonic())
        if interrupt:
            timer = threading.Timer(0.05, os.kill, args=(os.getpid(), signal.SIGINT))
            timer.start()
        return child

    try:
        with patch("deadline.Popen", side_effect=spawning):
            yield started
    finally:
        try:
            if timer is not None:
                timer.cancel()
                timer.join()
            identity = root / "identity.json"
            if identity.exists():
                facts = json.loads(identity.read_text())
                state = process_state(facts["child"])
                if state != "gone" and not state.startswith("Z"):
                    kill_group(facts["child"] if facts["escape"] else facts["leader"])
            for child in children:
                if child.poll() is None:
                    kill_group(child.pid)
                try:
                    child.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    child.stdout.close()
                    child.stderr.close()
                    child.wait(timeout=2)
        finally:
            try:
                watchdog.kill()
                watchdog.wait(timeout=2)
            finally:
                signal.signal(signal.SIGALRM, old_handler)


class DeadlineTests(unittest.TestCase):
    def env(self, root):
        return {"PATH": "/usr/bin:/bin", "HOME": str(root), "LIGHTR_HOME": str(root), "LC_ALL": "C"}

    def assert_stopped(self, pid):
        state = process_state(pid)
        self.assertTrue(state == "gone" or state.startswith("Z"), f"process {pid} still running: {state}")

    def test_whole_group_after_delayed_parent_scheduling(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with coordinate(root, parent_delay=1.1) as started:
                result = execute([PYTHON, '-I', '-c', FAMILY, 'no', 'no'], self.env(root), root, 0.2)
                self.assertLess(time.monotonic() - started[0], 1.5)
                group, grandchild = map(int, result.stdout.split())
                self.assertEqual(group, result.pid)
                self.assertNotEqual(group, os.getpgrp())
                self.assertTrue(result.timed_out)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"retained stderr\n")
                self.assertEqual(process_state(group), "gone")
                self.assert_stopped(grandchild)  # Observe BEFORE the test's finally cleanup.

    def test_actual_keyboard_interrupt_cleans_owned_family(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with coordinate(root, interrupt=True):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    execute([PYTHON, '-I', '-c', FAMILY, 'no', 'yes'], self.env(root), root)
                facts = json.loads((root / 'identity.json').read_text())
                self.assertEqual(process_state(facts['leader']), "gone")
                self.assert_stopped(facts['child'])
                self.assertIsNotNone(caught.exception.returncode)
                self.assertEqual(caught.exception.stderr, b"retained stderr\n")
                group, grandchild = map(int, caught.exception.stdout.split())
                self.assertEqual(group, caught.exception.pid)
                self.assertEqual(process_state(group), "gone")
                self.assert_stopped(grandchild)

    def test_original_exception_is_preserved_with_retained_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = RuntimeError("injected communication failure")
            real_communicate = subprocess.Popen.communicate

            def communicating(child, *args, **kwargs):
                if not hasattr(child, 'control_interrupted'):
                    child.control_interrupted = True
                    raise original
                return real_communicate(child, *args, **kwargs)

            with coordinate(root):
                with patch.object(subprocess.Popen, 'communicate', communicating), self.assertRaises(RuntimeError) as caught:
                    execute([PYTHON, '-I', '-c', FAMILY, 'no', 'yes'], self.env(root), root)
                self.assertIs(caught.exception, original)
                self.assertEqual(original.stderr, b"retained stderr\n")
                group, grandchild = map(int, original.stdout.split())
                self.assertEqual(process_state(group), 'gone')
                self.assert_stopped(grandchild)

    def test_escaped_pipe_has_named_bounded_recovery_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with coordinate(root) as started:
                with patch('deadline.RECOVERY_S', 0.2), self.assertRaises(CleanupDeadline) as caught:
                    execute([PYTHON, '-I', '-c', FAMILY, 'yes', 'no'], self.env(root), root, 0.2)
                self.assertLess(time.monotonic() - started[0], 1.5)
                self.assertEqual(caught.exception.returncode, 0)
                self.assertEqual(caught.exception.stderr, b"retained stderr\n")
                facts = json.loads((root / 'identity.json').read_text())
                self.assertEqual(process_state(facts['leader']), "gone")
                self.assertFalse(process_state(facts['child']).startswith('Z'))
                self.assertNotEqual(process_state(facts['child']), 'gone')

    def test_normal_completion_and_invalid_deadlines(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            argv = [PYTHON, '-I', '-c', "print('normal')"]
            result = execute(argv, self.env(root), root)
            self.assertFalse(result.timed_out)
            self.assertEqual(result.stdout, b"normal\n")
            for invalid in (0, -1, float("nan"), float("inf"), True):
                with self.subTest(timeout=invalid), self.assertRaisesRegex(ValueError, "finite and positive"):
                    execute(argv, self.env(root), root, invalid)
