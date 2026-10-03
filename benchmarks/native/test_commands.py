import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from commands import Commands
import commands
from deadline import CleanupDeadline
from test_deadline import FAMILY, PYTHON, coordinate


class CommandTests(unittest.TestCase):
    def subject(self, root):
        subject = Commands()
        subject.out, subject.sequence, subject.context, subject.meta = root, 0, {}, {}
        subject.args, subject.python = SimpleNamespace(source_sha="a" * 40), PYTHON
        subject.env = {"PATH": "/usr/bin:/bin", "HOME": str(root), "LC_ALL": "C"}
        (root / "logs").mkdir()
        (root / "work").mkdir()
        return subject

    def test_actual_interrupt_and_cleanup_failure_keep_bytes_and_identity(self):
        for interrupt in (True, False):
            with self.subTest(interrupt=interrupt), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                subject = self.subject(root)
                error_type = KeyboardInterrupt if interrupt else CleanupDeadline
                with coordinate(root, interrupt=interrupt), patch("deadline.RECOVERY_S", 0.2):
                    with self.assertRaises(error_type) as caught:
                        subject.command([PYTHON, "-I", "-c", FAMILY,
                            "no" if interrupt else "yes", "yes" if interrupt else "no"], timeout_s=0.2)
                    row = json.loads((root / "commands.jsonl").read_text())
                    self.assertEqual(row["exit_class"], "interrupt" if interrupt else "cleanup_failure")
                    self.assertFalse(row["validated"])
                    self.assertEqual(row["pid"], caught.exception.pid)
                    self.assertEqual((root / "logs/000001.stdout").read_bytes(), caught.exception.stdout)
                    self.assertTrue(caught.exception.stdout)
                    self.assertEqual((root / "logs/000001.stderr").read_bytes(), b"retained stderr\n")

    def test_success_and_spawn_failure_are_distinct(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subject = self.subject(root)
            row = subject.command([PYTHON, "-I", "-c", "print('retained success')"])
            self.assertEqual(row["exit_class"], "process")
            self.assertEqual(row["stdout"], "retained success\n")
            with self.assertRaises(FileNotFoundError):
                subject.command([str(root / "absent-command")])
            rows = [json.loads(line) for line in (root / "commands.jsonl").read_text().splitlines()]
            self.assertEqual(rows[-1]["exit_class"], "execution_error")
            self.assertIsNone(rows[-1]["pid"])

    def test_persistence_fault_preserves_original_interrupt_and_other_sinks(self):
        for sink in ("raw", "jsonl"):
            with self.subTest(sink=sink), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                subject = self.subject(root)
                real_write = Path.write_bytes
                def write(path, data):
                    if path.suffix == ".stdout":
                        raise OSError(28, "No space left on device")
                    return real_write(path, data)
                fault = patch.object(Path, "write_bytes", write) if sink == "raw" else patch.object(commands, "append", side_effect=OSError(28, "No space left on device"))
                with coordinate(root, interrupt=True), fault, self.assertRaises(KeyboardInterrupt) as caught:
                    subject.command([PYTHON, "-I", "-c", FAMILY, "no", "yes"])
                self.assertTrue(caught.exception.stdout)
                self.assertIn("persistence failed", caught.exception.__notes__[0])
                self.assertEqual((root / "logs/000001.stderr").read_bytes(), b"retained stderr\n")
                if sink == "raw":
                    self.assertEqual(json.loads((root / "commands.jsonl").read_text())["exit_class"], "interrupt")

    def test_exit_deadline_and_timed_usage_rejections(self):
        for usage in ("valid", None, "not-json", "infinite", "negative", "extra"):
            with self.subTest(usage=usage), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                subject = self.subject(root)
                metrics = {"user_s": 0.01, "system_s": 0, "max_rss_kib": 123, "exit": 0}
                if usage == "infinite": metrics["user_s"] = float("inf")
                if usage == "negative": metrics["max_rss_kib"] = -1
                if usage == "extra": metrics["extra"] = 1
                if usage is not None:
                    (root / "logs/000001.usage").write_text("not-json" if usage == "not-json" else json.dumps(metrics))
                outcome = SimpleNamespace(pid=1, returncode=0, stdout=b"ok", stderr=b"", timed_out=False, group_gone=False)
                with patch.object(commands, "execute", return_value=outcome):
                    if usage == "valid":
                        self.assertEqual(subject.command([PYTHON], timed=True)["max_rss_kib"], 123)
                    else:
                        with self.assertRaises(ValueError): subject.command([PYTHON], timed=True)
                    outcome.timed_out = True
                    with self.assertRaisesRegex(ValueError, "deadline exceeded"): subject.command([PYTHON])
                with self.assertRaisesRegex(ValueError, "unexpected exit"):
                    subject.command([PYTHON, "-I", "-c", "raise SystemExit(7)"])

    def test_usage_metadata_fault_keeps_original_and_attempts_jsonl(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subject = self.subject(root)
            original = FileNotFoundError("missing timed wrapper")
            outcome = SimpleNamespace(pid=1, returncode=0, stdout=b"", stderr=b"", timed_out=False, group_gone=False)
            for failed in (True, False):
                with patch.object(commands, "execute", side_effect=original if failed else None, return_value=outcome), patch.object(Path, "is_file", side_effect=PermissionError("usage metadata denied")):
                    with self.assertRaises(FileNotFoundError if failed else PermissionError) as caught:
                        subject.command([PYTHON], timed=True)
                if failed:
                    self.assertIs(caught.exception, original)
                    self.assertIn("PermissionError", original.__notes__[0])
                    self.assertEqual(json.loads((root / "commands.jsonl").read_text())["exit_class"], "execution_error")


if __name__ == "__main__":
    unittest.main()
