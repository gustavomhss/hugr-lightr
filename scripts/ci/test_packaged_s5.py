"""Execute release/S5 shell recipes with recorded tools; not a VZ boot witness.

Discovered by existing Required CI test_*.py runner. Real tar/hash operations
check packaged bytes; fake Apple/build tools check invocation and failure paths.
"""
import hashlib
import json
import os
import plistlib
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
RELEASE = "packaging/release.sh"
HARNESS = "spikes/s5-vz-boot-arm64/run-s5-arm64.sh"
PAYLOAD = b"fixture-cli\n"
TOOLS = r'''
import json, os, pathlib, plistlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps([name, str(pathlib.Path(sys.argv[0]).absolute()), args]) + "\n")
if name == "uname":
    print(os.environ.get("HOST_OS", "Darwin") if args == ["-s"] else os.environ.get("HOST_ARCH", "arm64"))
elif name == "cargo":
    binary = pathlib.Path(os.environ["FIXTURE_ROOT"]) / "target/release/lightr"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(pathlib.Path(os.environ["SELECTED"]).read_bytes() if os.environ.get("S5") else b"fixture-cli\n")
    binary.chmod(0o755)
elif name == "strip":
    with open(args[0], "ab") as binary: binary.write(b"stripped\n")
elif name == "codesign":
    if os.environ.get("SIGN_FAIL"):
        sys.exit(1)
    if "-s" in args:
        with open(args[-1], "ab") as binary: binary.write(b"# ad-hoc-vz\n")
    elif "--verify" in args:
        sys.exit(int(os.environ.get("VERIFY_FAIL", "0")))
    elif "-d" in args:
        if os.environ.get("PLIST_FIXTURE"):
            sys.stdout.buffer.write(pathlib.Path(os.environ["PLIST_FIXTURE"]).read_bytes())
        else:
            sys.stdout.buffer.write(plistlib.dumps({"com.apple.security.virtualization": os.environ.get("ENTITLEMENT", "true") == "true"}))
elif name == "lipo":
    sys.exit(1) if os.environ.get("LIPO_FAIL") else print(os.environ.get("BINARY_ARCH", "arm64"))
elif name == "plutil":
    # Portable stand-in parses real plist bytes. macOS type regression below
    # removes this tool and runs Apple's plutil against those same bytes.
    assert args[:3] == ["-extract", r"com\.apple\.security\.virtualization", "raw"]
    if os.environ.get("ENTITLEMENT_MISSING"): sys.exit(1)
    value = plistlib.loads(sys.stdin.buffer.read())["com.apple.security.virtualization"]
    if "-expect" in args:
        assert args == args[:3] + ["-expect", "bool", "-o", "-", "-"]
        if type(value) is not bool: sys.exit(1)
    else:
        assert args == args[:3] + ["-o", "-", "-"]
    print(str(value).lower() if type(value) is bool else value)
elif name == "lightr":
    if args[:2] == ["engine", "ls"]: print("vz available fixture")
    elif args[0] == "run":
        if args[-1] == "s5-boot-ok": print("s5-boot-ok")
        else: sys.exit(7)
elif name not in ("pack", "swiftc"):
    raise SystemExit("unexpected tool: " + name)
'''


class PackagedS5Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="packaged s5 ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        for path in (RELEASE, HARNESS, "packaging/vz.entitlements", "Cargo.toml"):
            dest = self.root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, dest)
        self.tools = self.root / "tools"
        self.tools.mkdir()
        for name in ("uname", "cargo", "strip", "codesign", "lipo", "plutil", "swiftc", "pack"):
            self.executable(self.tools / name, TOOLS)
        self.selected = self.root / "extracted bytes/lightr"
        self.selected.parent.mkdir()
        self.executable(self.selected, TOOLS)
        pack = self.root / "scripts/build-linux-pack.sh"
        pack.parent.mkdir()
        pack.write_text('#!/bin/bash\nexec "$FAKE_TOOLS/pack" "$@"\n')
        self.kernel = self.root / "supplied Image"
        self.kernel.write_bytes(b"kernel fixture")
        self.oci = self.root / "supplied OCI"
        self.oci.mkdir()
        self.log = self.root / "calls.jsonl"
        self.env = dict(os.environ, PATH=f"{self.tools}:/usr/bin:/bin", HOME=str(self.root / "home"),
                        FIXTURE_ROOT=str(self.root), CALL_LOG=str(self.log),
                        SELECTED=str(self.selected), FAKE_TOOLS=str(self.tools),
                        LIGHTR_KERNEL=str(self.kernel), ALPINE_OCI_DIR=str(self.oci),
                        COPYFILE_DISABLE="1") # exclude macOS fixture xattrs from tar
        # Do not inherit caller input/store overrides into the fixtures.
        for key in ("ALPINE_TAR", "LIGHTR_STORE_DIR", "LIGHTR_LINUX_PACK"):
            self.env.pop(key, None)

    def executable(self, path, body):
        path.write_text(f"#!{sys.executable}\n" + body)
        path.chmod(0o755)

    def run_script(self, path, *args, **env):
        result = subprocess.run(["bash", str(self.root / path), *map(str, args)],
                                cwd=self.root, env=dict(self.env, **env),
                                capture_output=True, text=True, timeout=60)
        self.calls = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return result

    def successful(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def named(self, name):
        return [call for call in self.calls if call[0] == name]

    def test_macos_recipe_packages_stripped_entitled_vz_bytes(self):
        result = self.run_script(RELEASE)
        self.successful(result)
        self.assertEqual(self.named("cargo")[0][2], ["build", "--locked", "--release", "--bin", "lightr", "--features", "vz"])
        signed = self.named("codesign")
        self.assertEqual(signed[0][2][:4], ["-s", "-", "--entitlements", str(self.root / "packaging/vz.entitlements")])
        self.assertEqual(signed[1][2], ["--verify", "--strict", signed[0][2][-1]])
        self.assertLess(self.calls.index(self.named("strip")[0]), self.calls.index(signed[0]))
        self.assertNotEqual(signed[0][2][-1], str(self.root / "target/release/lightr"))
        self.assert_artifact("darwin-arm64-unsigned", PAYLOAD + b"stripped\n# ad-hoc-vz\n")
        self.assertIn("unsigned: no Developer ID; not notarized", result.stdout)

    def assert_artifact(self, target, payload):
        artifacts = list((self.root / "packaging/dist").glob("*.tar.gz"))
        self.assertEqual(len(artifacts), 1)
        artifact = artifacts[0]
        self.assertTrue(artifact.name.endswith(f"-{target}.tar.gz"), artifact.name)
        with tarfile.open(artifact) as archive:
            self.assertEqual(archive.getnames(), ["lightr"])
            self.assertEqual(archive.extractfile("lightr").read(), payload)
            self.assertEqual(archive.getmember("lightr").mode, 0o755)
        self.assertEqual(Path(str(artifact) + ".sha256").read_text(),
                         f"{hashlib.sha256(artifact.read_bytes()).hexdigest()}  {artifact.name}\n")

    def test_linux_recipe_has_no_vz_or_codesign(self):
        self.successful(self.run_script(RELEASE, HOST_OS="Linux", HOST_ARCH="x86_64"))
        self.assertEqual(self.named("cargo")[0][2], ["build", "--locked", "--release", "--bin", "lightr"])
        self.assertEqual(self.named("codesign"), [])
        self.assert_artifact("linux-x86_64", PAYLOAD + b"stripped\n")

    def test_recipe_sign_or_verify_failure_prevents_artifact(self):
        for env in ({"SIGN_FAIL": "1"}, {"VERIFY_FAIL": "1"}):
            with self.subTest(env=env):
                self.assertNotEqual(self.run_script(RELEASE, **env).returncode, 0)
                self.assertEqual(list((self.root / "packaging/dist").glob("*.tar.gz")), [])

    def test_selector_runs_only_supplied_bytes_and_inputs(self):
        before = self.selected.read_bytes()
        result = self.run_script(HARNESS, "--binary", self.selected.relative_to(self.root), S5="1")
        self.successful(result)
        self.assertIn("ALL ASSERTIONS PASSED", result.stdout)
        self.assertEqual(self.named("cargo"), [])
        self.assertEqual(self.named("swiftc"), [])
        self.assertTrue(self.named("codesign"))
        self.assertFalse(any("-s" in call[2] or "--force" in call[2] for call in self.named("codesign")))
        self.assertEqual(self.selected.read_bytes(), before)
        cli = self.named("lightr")
        self.assertEqual([call[2][:2] for call in cli], [["engine", "install-pack"], ["engine", "ls"], ["oci", "import"], ["run", "--engine"], ["run", "--engine"]])
        self.assertTrue(all(call[1] == str(self.selected) for call in cli))
        self.assertEqual(cli[2][2], ["oci", "import", str(self.oci), "--name", "alpine"])
        self.assertEqual(self.named("pack")[0][2], ["--arch", "aarch64", "--out", str(self.root / "build/linux-pack-arm64"), "--kernel", str(self.kernel)])

    def test_legacy_invocation_builds_and_signs(self):
        self.successful(self.run_script(HARNESS, S5="1"))
        self.assertEqual(self.named("cargo")[0][2], ["build", "--locked", "--release", "--bin", "lightr", "--features", "vz"])
        self.assertIn("-s", self.named("codesign")[0][2])
        self.assertTrue(all(call[1] == str(self.root / "target/release/lightr") for call in self.named("lightr")))

    def test_selector_requires_real_plist_boolean_true(self):
        # No VZ/Apple Silicon required: real plutil on macOS; typed plist parser
        # stand-in elsewhere. codesign supplies plist bytes, not fabricated raw.
        if sys.platform == "darwin":
            (self.tools / "plutil").unlink()
        fixture = self.root / "entitlements.plist"
        for value, reason in ((True, None), ("true", "of boolean type"),
                              (1, "of boolean type"), (False, "is not true")):
            with self.subTest(value=value, type=type(value).__name__):
                fixture.write_bytes(plistlib.dumps({"com.apple.security.virtualization": value}))
                self.log.unlink(missing_ok=True)
                before = self.selected.read_bytes()
                result = self.run_script(HARNESS, "--binary", self.selected, PLIST_FIXTURE=str(fixture))
                if reason is None:
                    self.successful(result)
                    self.assertTrue(self.named("pack"))
                else:
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn(reason, result.stderr)
                    self.assertEqual(self.named("pack"), [])
                    self.assertEqual(self.named("lightr"), [])
                self.assertEqual(self.selected.read_bytes(), before)

    def test_selector_rejects_bad_host_arch_signature_and_entitlement(self):
        for env, reason in (
            ({"HOST_ARCH": "x86_64"}, "native Apple Silicon"),
            ({"HOST_OS": "Linux"}, "native Apple Silicon"),
            ({"BINARY_ARCH": "x86_64"}, "must be arm64 Mach-O"),
            ({"BINARY_ARCH": "x86_64 arm64"}, "must be arm64 Mach-O"),
            ({"LIPO_FAIL": "1"}, "cannot read --binary Mach-O"),
            ({"VERIFY_FAIL": "1"}, "signature verification failed"),
            ({"ENTITLEMENT_MISSING": "1"}, "lacks virtualization entitlement"),
            ({"ENTITLEMENT": "false"}, "entitlement is not true"),
        ):
            with self.subTest(env=env):
                self.log.unlink(missing_ok=True)
                result = self.run_script(HARNESS, "--binary", self.selected, **env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stderr)
                self.assertEqual(self.named("lightr"), [])
                self.assertEqual(self.named("pack"), [])

    def test_selector_usage_missing_and_nonexecutable_paths_fail(self):
        for args, reason in ((["--binary"], "usage:"), (["--typo", "x"], "usage:"),
                             (["--binary", "missing"], "not an executable file"),
                             (["--binary", self.kernel], "not an executable file")):
            with self.subTest(args=args):
                result = self.run_script(HARNESS, *args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stderr)

    def test_supplied_tar_preserves_legacy_input_precedence(self):
        tar = self.root / "supplied alpine.tar"
        tar.write_bytes(b"OCI fixture")
        self.successful(self.run_script(HARNESS, "--binary", self.selected, ALPINE_TAR=str(tar)))
        self.assertEqual(self.named("lightr")[2][2], ["oci", "import", str(tar), "--name", "alpine"])


if __name__ == "__main__":
    unittest.main()
