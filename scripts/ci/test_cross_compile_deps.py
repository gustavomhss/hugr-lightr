"""Execute parsed CI dependency script with fake apt; not compiler qualification."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = {
    "aarch64-unknown-linux-gnu": ["gcc-aarch64-linux-gnu", "g++-aarch64-linux-gnu"],
    "x86_64-pc-windows-gnu": ["gcc-mingw-w64-x86-64", "g++-mingw-w64-x86-64"],
}


class CrossCompileDepsTests(unittest.TestCase):
    def setUp(self):
        self.jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
        steps = self.jobs["cross-compile"]["steps"]
        matches = [step for step in steps if step.get("name") == "Install cross-compile deps"]
        self.assertEqual(len(matches), 1, "dependency step missing or duplicated")
        self.step = matches[0]

    def execute(self, target, failure=""):
        with tempfile.TemporaryDirectory() as directory:
            tools = Path(directory)
            calls = tools / "calls"
            for name, code in {
                "sudo": "os.execvp(sys.argv[1], sys.argv[1:])",
                "apt-get": """with open(os.environ['CALLS'], 'a') as log:
    log.write(json.dumps([sys.argv[1:], os.environ.get('DEBIAN_FRONTEND')]) + '\\n')
if sys.argv[1] == os.environ['FAIL_APT']:
    print('fake apt-get ' + sys.argv[1] + ' failed', file=sys.stderr)
    sys.exit(42)
""",
            }.items():
                tool = tools / name
                tool.write_text(f"#!{sys.executable}\nimport os, sys, json\n{code}\n")
                tool.chmod(0o755)
            env = dict(os.environ, PATH=f"{tools}:{os.environ['PATH']}", TARGET=target,
                       CALLS=str(calls), FAIL_APT=failure)
            result = subprocess.run(["bash", "-c", self.step["run"]], env=env,
                                    capture_output=True, text=True, timeout=30)
            return result, [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []

    def test_matrix_and_step_wiring(self):
        job = self.jobs["cross-compile"]
        self.assertCountEqual(job["strategy"]["matrix"]["target"], ["x86_64-unknown-linux-gnu", *PACKAGES])
        self.assertEqual(self.step["if"], "matrix.target != 'x86_64-unknown-linux-gnu'")
        self.assertEqual(self.step["env"]["TARGET"], "${{ matrix.target }}")
        self.assertEqual(self.step["timeout-minutes"], 10)
        for item in (job, self.step):
            self.assertFalse(item.get("continue-on-error", False))
        check = next(step for step in job["steps"] if step.get("name") == "Cross-check")
        self.assertEqual(check["run"], "cargo check --workspace --target ${{ matrix.target }}")
        self.assertNotIn("if", check)
        self.assertFalse(check.get("continue-on-error", False))
        runner = "python3 -m unittest discover -s scripts/ci -p 'test_*.py' -v"
        discovery = [step for step in self.jobs["required-ci"]["steps"] if step.get("run") == runner]
        self.assertEqual(len(discovery), 1)
        self.assertNotIn("if", discovery[0])
        self.assertFalse(discovery[0].get("continue-on-error", False))

    def test_compiler_and_discovery_skip_tolerance_mutations_reject(self):
        check = next(step for step in self.jobs["cross-compile"]["steps"] if step.get("name") == "Cross-check")
        discovery = next(step for step in self.jobs["required-ci"]["steps"] if "unittest discover" in step.get("run", ""))
        for step in (check, discovery):
            for key, value in (("if", False), ("continue-on-error", True)):
                with self.subTest(step=step.get("name"), key=key):
                    step[key] = value
                    try:
                        with self.assertRaises(AssertionError):
                            self.test_matrix_and_step_wiring()
                    finally:
                        del step[key]

    def test_only_target_packages_installed(self):
        for target, packages in PACKAGES.items():
            with self.subTest(target=target):
                result, calls = self.execute(target)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [[['update'], 'noninteractive'],
                                        [['install', '-y', *packages, 'clang', 'lld'], 'noninteractive']])

    def test_empty_and_unknown_targets_fail_before_apt(self):
        for target in ("", "unknown"):
            with self.subTest(target=target):
                result, calls = self.execute(target)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Unsupported cross-compile target:", result.stderr)
                self.assertEqual(calls, [])

    def test_apt_failures_are_visible_and_stop_step(self):
        for target in PACKAGES:
            for failure in ("update", "install"):
                with self.subTest(target=target, failure=failure):
                    result, calls = self.execute(target, failure)
                    self.assertEqual(result.returncode, 42, result.stderr)
                    self.assertIn(f"fake apt-get {failure} failed", result.stderr)
                    self.assertEqual([call[0][0] for call in calls],
                                     ["update"] if failure == "update" else ["update", "install"])


if __name__ == "__main__":
    unittest.main()
