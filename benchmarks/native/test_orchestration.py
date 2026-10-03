import argparse
import json
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

from campaign import Campaign, SCENARIOS, fixture, main, scenario_selection
from test_deadline import FAMILY, coordinate


class FixtureTests(unittest.TestCase):
    def test_scenario_selection_rejects_empty_unknown_and_duplicates(self):
        self.assertEqual(scenario_selection(",".join(SCENARIOS)), SCENARIOS)
        self.assertEqual(scenario_selection("direct,memo-hit"), ("direct", "memo-hit"))
        for value in ("", "memo-hit,", "unknown", "memo-hit,memo-hit", " direct"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "nonempty, known and unique"):
                scenario_selection(value)

    def test_unique_deterministic_payloads_and_modes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = fixture(root / "first", 2)
            second = fixture(root / "second", 2)
            self.assertEqual(first, second)
            entries = first["entries"]
            self.assertEqual(len(entries), 4)
            self.assertEqual(entries["file-00000000"]["size"], 4096)
            self.assertNotEqual(entries["file-00000000"]["sha256"], entries["file-00000001"]["sha256"])
            self.assertEqual(entries["file-00000000"]["mode"], 0o755)
            self.assertEqual(entries["file-00000001"]["mode"], 0o644)

    def test_untimed_deadline_retains_failure_before_acceptance(self):
        code = """import sys, time
from pathlib import Path
print('retained', flush=True)
Path(sys.argv[-1]).touch()
time.sleep(2)
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            campaign = Campaign(argparse.Namespace(source_sha="a" * 40), root)
            with coordinate(root), self.assertRaisesRegex(ValueError, "deadline exceeded"):
                campaign.command([campaign.python, "-I", "-c", code], timeout_s=0.2)
            row = json.loads((root / "commands.jsonl").read_text())
            self.assertTrue(row["timed_out"])
            self.assertEqual(row["exit_class"], "deadline")
            self.assertEqual(row["stdout"], "retained\n")
            self.assertEqual((root / "logs/000001.stdout").read_bytes(), b"retained\n")
            self.assertEqual(campaign.rows, [])

    def test_main_execution_failures_keep_logs_and_remove_success_summaries(self):
        for interrupt in (True, False):
            with self.subTest(interrupt=interrupt), tempfile.TemporaryDirectory() as temporary:
                root, out = Path(temporary), Path(temporary) / "result"
                argv = ["campaign.py", "--binary", "unused", "--source-dir", "unused", "--source-sha", "a" * 40,
                        "--build-receipt", "unused", "--out", str(out)]
                def fail(campaign):
                    (campaign.out / "summary.json").write_text("stale")
                    (campaign.out / "summary.md").write_text("stale")
                    campaign.command([campaign.python, "-I", "-c", FAMILY,
                        "no" if interrupt else "yes", "yes" if interrupt else "no"], timeout_s=0.2)
                with coordinate(root, interrupt=interrupt), patch("deadline.RECOVERY_S", 0.2), patch.object(Campaign, "run", fail), patch.object(sys, "argv", argv):
                    self.assertEqual(main(), 1)
                self.assertEqual(json.loads((out / "metadata.json").read_text())["status"], "failed")
                self.assertEqual(json.loads((out / "failure.json").read_text())["type"], "KeyboardInterrupt" if interrupt else "CleanupDeadline")
                self.assertEqual(json.loads((out / "commands.jsonl").read_text())["exit_class"], "interrupt" if interrupt else "cleanup_failure")
                self.assertEqual((out / "logs/000001.stderr").read_bytes(), b"retained stderr\n")
                self.assertTrue((out / "logs/000001.stdout").read_bytes())
                self.assertFalse((out / "summary.json").exists())
                self.assertFalse((out / "summary.md").exists())
