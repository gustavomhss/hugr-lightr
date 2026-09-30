"""Repair regression: execute unsigned release shell with metadata-writing codesign fake."""
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TARGET = "aarch64-apple-darwin"
CREDENTIALS = ("APPLE_CERT", "APPLE_CERT_PASSWORD", "AC_API_KEY", "AC_API_KEY_ID")
FAKE_CODESIGN = r'''
import json, os, pathlib, plistlib, sys
args = sys.argv[1:]
with open("calls.jsonl", "a") as log:
    log.write(json.dumps(args) + "\n")
binary = pathlib.Path(args[-1])
mode = os.environ["FIXTURE_MODE"]
if "-s" in args:
    if mode == "codesignfail": sys.exit(1)
    metadata = plistlib.load(open(args[args.index("--entitlements") + 1], "rb")) if "--entitlements" in args else {}
    if mode == "missing": metadata.clear()
    if mode in ("false", "string", "integer"):
        metadata["com.apple.security.virtualization"] = {"false": False, "string": "true", "integer": 1}[mode]
    binary.write_bytes(b"ad-hoc\n" + plistlib.dumps(metadata))
elif "--verify" in args:
    sys.exit(1 if mode == "verifyfail" or not binary.read_bytes().startswith(b"ad-hoc\n") else 0)
elif "-d" in args:
    if mode == "extractfail": sys.exit(1)
    sys.stdout.buffer.write(b"invalid plist" if mode == "malformed" else binary.read_bytes().split(b"\n", 1)[1])
else:
    sys.exit("unexpected codesign invocation")
'''


class ReleaseSigningTests(unittest.TestCase):
    def setUp(self):
        document = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
        self.steps = document["jobs"]["build"]["steps"]
        self.matrix = document["jobs"]["build"]["strategy"]["matrix"]["include"]

    def shell(self, name, matrix=None):
        matches = [step["run"] for step in self.steps if step.get("name") == name]
        self.assertEqual(len(matches), 1, f"missing or duplicate release step: {name}")
        self.assertIsInstance(matches[0], str)
        self.assertTrue(matches[0].strip(), f"empty release step: {name}")
        script = matches[0]
        substitutions = {"matrix.rust-target": TARGET, "matrix.os-tag": "darwin",
                         "matrix.arch-tag": "arm64", "inputs.release_tag": "v0.1.0"}
        if matrix is not None:
            substitutions.update({f"matrix.{key}": value for key, value in matrix.items()})
        for key, value in substitutions.items():
            script = script.replace("${{ " + key + " }}", value)
        return script

    def run_fixture(self, mode="valid", missing=CREDENTIALS):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        binary = root / "target" / TARGET / "release/lightr"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"unsigned fixture\n")
        (root / "packaging").mkdir()
        (root / "packaging/vz.entitlements").write_bytes((ROOT / "packaging/vz.entitlements").read_bytes())
        tools = root / "bin"
        tools.mkdir()
        (tools / "codesign").write_text(f"#!{sys.executable}\n" + FAKE_CODESIGN)
        (tools / "codesign").chmod(0o755)
        env = dict(os.environ, PATH=f"{tools}:{os.environ['PATH']}", RUNNER_TEMP=str(root),
                   GITHUB_ENV=str(root / "state"), GITHUB_OUTPUT=str(root / "output"), FIXTURE_MODE=mode)
        env.update({key: "" if key in missing else "fixture-only" for key in CREDENTIALS})
        def execute(script):
            return subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
                                  cwd=root, env=env, capture_output=True, text=True, timeout=15)
        result = execute(self.shell("Sign and notarize (macOS)"))
        if result.returncode == 0:
            env.update(line.split("=", 1) for line in (root / "state").read_text().splitlines())
            packaged = execute(self.shell("Package tarball and checksum"))
            packaged.stdout = result.stdout + packaged.stdout
            result = packaged
        return root, binary, result

    def test_unsigned_metadata_and_package_identity(self):
        for missing in (CREDENTIALS,) + tuple((key,) for key in CREDENTIALS):
            with self.subTest(missing=missing):
                root, binary, result = self.run_fixture(missing=missing)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((root / "state").read_text(), "SIGNING_DONE=false\n")
                calls = [json.loads(line) for line in (root / "calls.jsonl").read_text().splitlines()]
                path = str(binary.relative_to(root))
                self.assertEqual(calls, [["-s", "-", "--force", "--entitlements", "packaging/vz.entitlements", path],
                                         ["--verify", "--strict", path], ["-d", "--entitlements", ":-", path]])
                artifact = root / "lightr-0.1.0-darwin-arm64-unsigned.tar.gz"
                with tarfile.open(artifact) as archive:
                    self.assertEqual(archive.extractfile("lightr").read(), binary.read_bytes())
                self.assertTrue(artifact.with_name(artifact.name + ".sha256").is_file())

    def test_failures_stop_before_state_and_packaging(self):
        for mode in ("missing", "false", "string", "integer", "malformed", "codesignfail", "verifyfail", "extractfail"):
            with self.subTest(mode=mode):
                root, _, result = self.run_fixture(mode)
                self.assertNotEqual(result.returncode, 0, f"{mode}: accepted invalid signature/entitlement")
                self.assertFalse((root / "state").exists(), f"{mode}: wrote signing state")
                self.assertFalse((root / "output").exists(), f"{mode}: packaged artifact")
                self.assertEqual(list(root.glob("*.tar.gz")), [], f"{mode}: partial package")

    def test_unsigned_status_is_explicit(self):
        root, _, result = self.run_fixture()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("unsigned (ad-hoc virtualization entitlement; no Developer ID; not notarized)", result.stdout)
        self.assertEqual((root / "state").read_text(), "SIGNING_DONE=false\n")

    def test_release_build_matrix_argv_is_exact(self):
        self.assertEqual([(entry["rust-target"], entry["features"]) for entry in self.matrix],
                         [(TARGET, "vz"), ("x86_64-unknown-linux-gnu", "")])
        with tempfile.TemporaryDirectory() as tmp:
            cargo = Path(tmp) / "cargo"
            cargo.write_text(f"#!{sys.executable}\nimport json, sys; print(json.dumps(sys.argv[1:]))\n")
            cargo.chmod(0o755)
            for entry in self.matrix:
                with self.subTest(target=entry["rust-target"]):
                    script = self.shell("Build release binary", matrix=entry)
                    result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", script], text=True,
                                            cwd=tmp, env=dict(os.environ, PATH=f"{tmp}:{os.environ['PATH']}"),
                                            capture_output=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    expected = ["build", "--locked", "--release", "-p", "lightr-cli", "--target", entry["rust-target"]]
                    if entry["features"]:
                        expected += ["--features", entry["features"]]
                    self.assertEqual(json.loads(result.stdout), expected)


if __name__ == "__main__":
    unittest.main()
