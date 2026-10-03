"""Build-oracle wiring controls; actual Cargo build occurs in manual workflow."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import build
from deadline import _Outcome
from provenance import validate_receipt


class BuildTests(unittest.TestCase):
    def test_clean_release_receipt_and_rejected_builds(self):
        for defect in (None, "head-mismatch", "dirty-before", "dirty-after", "postflight-error", "build-failure", "missing-binary", "timeout", "interrupt"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "source"
                source.mkdir()
                source = source.resolve()
                binary = source / "target/release/lightr"
                output = root / "receipt.json"
                sha, builds = "a" * 40, []

                def execute(argv, **kwargs):
                    if argv[:2] == ["git", "rev-parse"]:
                        return subprocess.CompletedProcess(argv, 0, ("b" * 40 if defect == "head-mismatch" else sha) + "\n", "")
                    if argv[:2] == ["git", "status"]:
                        if defect == "postflight-error" and builds:
                            raise subprocess.CalledProcessError(19, argv, output="git output", stderr="git diagnostic")
                        dirty = defect == "dirty-before" or defect == "dirty-after" and builds
                        return subprocess.CompletedProcess(argv, 0, " M Cargo.toml\n" if dirty else "", "")
                    if argv[-1] == "--version":
                        return subprocess.CompletedProcess(argv, 0, argv[0] + " 1.96.0 (fixture)\n", "")
                    raise AssertionError(argv)

                def cargo(argv, env, cwd, timeout_s):
                    self.assertEqual(argv, ["cargo", "+1.96.0", "build", "--locked", "--release", "--bin", "lightr"])
                    self.assertNotIn("GH_TOKEN", env)
                    self.assertEqual(env["CARGO_INCREMENTAL"], "0")
                    self.assertEqual(timeout_s, 1200)
                    builds.append(argv)
                    if defect == "interrupt":
                        error = KeyboardInterrupt("fixture interrupt")
                        error.stdout, error.stderr, error.returncode = b"build output\n", b"build error\n", -9
                        raise error
                    if defect != "missing-binary":
                        binary.parent.mkdir(parents=True)
                        binary.write_bytes(b"explicit fake build-control bytes, not a measured binary")
                    return _Outcome(1, 7 if defect == "build-failure" else -9 if defect == "timeout" else 0,
                                    b"build output\n", b"build error\n", defect == "timeout", False)

                with patch.object(build.subprocess, "run", side_effect=execute), patch.object(build, "execute", side_effect=cargo):
                    if defect is None:
                        receipt = build.build(source, sha, output)
                        digest = hashlib.sha256(binary.read_bytes()).hexdigest()
                        self.assertEqual(validate_receipt(output.read_text(), source, sha, binary, digest), receipt)
                        self.assertFalse(Path(str(output) + ".failure.json").exists())
                    else:
                        with self.assertRaises(KeyboardInterrupt if defect == "interrupt" else subprocess.CalledProcessError if defect == "postflight-error" else ValueError):
                            build.build(source, sha, output)
                        failure = json.loads(Path(str(output) + ".failure.json").read_text())
                        self.assertEqual(failure["status"], "failed")
                        self.assertGreaterEqual(failure["completed_unix_ns"], failure["started_unix_ns"])
                        self.assertTrue(failure["error"])
                        self.assertEqual(failure["stage"], "preflight" if defect in ("head-mismatch", "dirty-before") else "cargo" if defect in ("build-failure", "timeout", "interrupt") else "postflight")
                        if defect == "timeout":
                            self.assertTrue(failure["timed_out"])
                        if output.exists():
                            self.assertEqual(json.loads(output.read_text())["status"], "failed")
                self.assertEqual(len(builds), 0 if defect in ("head-mismatch", "dirty-before") else 1)
                if builds:
                    prefix = str(output) + (".failure" if defect == "interrupt" else "")
                    self.assertEqual(Path(prefix + ".stdout").read_bytes(), b"build output\n")
                    self.assertEqual(Path(prefix + ".stderr").read_bytes(), b"build error\n")
                    if defect == "postflight-error":
                        self.assertEqual(Path(str(output) + ".failure.stderr").read_text(), "git diagnostic")


if __name__ == "__main__":
    unittest.main()
