"""Executable fixture controls; real tar/hash/install and macOS signature inspection.
Fixture host/cargo/inspection tools do not qualify hosted OCI or VZ execution.
"""
import contextlib
import gzip
import io
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch
import macos_candidate as m

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = '''set -euo pipefail
python3 -c 'import sys; sys.path.insert(0, "scripts/ci")
from pathlib import Path
from tempfile import TemporaryDirectory
from macos_candidate import Evidence
with TemporaryDirectory() as directory:
    Evidence(Path(directory) / "identity").host()'
'''

class Fixture:
    def __init__(self, version="0.1.0"):
        self.version = version
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="macos candidate ")
        self.root = Path(self.tmp.name); self.old = Path.cwd(); os.chdir(self.root)
        helper = self.root / "scripts/ci/macos_candidate.py"; helper.parent.mkdir(parents=True)
        helper.symlink_to(ROOT / "scripts/ci/macos_candidate.py")
        Path("Cargo.toml").write_text(f'# version = "9.9.9"\n[package]\nversion = "8.8.8"\n[workspace.package]\nversion = "{self.version}"\n')
        tools = self.root / "tools"; tools.mkdir()
        self.env = patch.dict(os.environ, PATH=f"{tools}:{os.environ['PATH']}", CANDIDATE_SHA="a" * 40, WORKFLOW_SHA="a" * 40, LIGHTR_NET_TESTS="1", RUSTFLAGS="-D warnings", GITHUB_OUTPUT=str(self.root / "output"), ARTIFACT_ID="123", ARTIFACT_SOURCE="https://fixture/123")
        self.env.start()
        self.tool(tools, "git", "print(os.environ.get('HEAD_SHA', os.environ['CANDIDATE_SHA']))")
        for name, body in {"uname": "print('Darwin' if sys.argv[1] == '-s' else 'arm64')", "sysctl": "print('1' if sys.argv[-1] == 'hw.optional.arm64' else 'fixture VM')", "sw_vers": "print('fixture macOS')", "rustc": "print('host: aarch64-apple-darwin')", "file": "print('Mach-O 64-bit executable arm64')", "lipo": "print(os.environ.get('ARCH', 'arm64'))", "codesign": "print(os.environ.get('PLIST', '<plist><dict><key>com.apple.security.virtualization</key><true/></dict></plist>') if '-d' in sys.argv else '')", "cargo": "name = sys.argv[-3] if '--exact' in sys.argv else None\nprint(('test ' + name + ' ... ok\\n' if name else '') + 'test result: ok. ' + os.environ.get('COUNT', '1') + ' passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s')"}.items(): self.tool(tools, name, body)
        # Packaging is fixture-only; tar, shasum, install, smoke, rm remain real.
        self.tool(tools, "codesign", "print('<?xml version=\"1.0\"?>' + os.environ.get('PLIST', '<plist><dict><key>com.apple.security.virtualization</key><true/></dict></plist>') if '-d' in sys.argv else '')")
        package = self.root / "packaging"; package.mkdir()
        (package / "release.sh").write_text("exit 0\n")
        self.tar = package / "dist" / f"lightr-{self.version}-darwin-arm64-unsigned.tar.gz"; self.tar.parent.mkdir()
        self.pack()
        return self
    def tool(self, directory, name, body):
        path = directory / name; path.write_text(f"#!{sys.executable} -S\nimport os, sys\n{body}\n"); path.chmod(0o755)
    def pack(self, name="lightr", mode=0o755, content=None, kind=tarfile.REGTYPE):
        content = content or f'#!/bin/sh\ncase "$1" in --version) echo "${{VERSION_OUTPUT:-lightr {self.version} (aaaaaaa, 2026-09-30)}}";; --help) echo help;; *) exit 1;; esac\n'.encode()
        with tarfile.open(self.tar, "w:gz") as tar:
            info = tarfile.TarInfo(name); info.mode = mode; info.type = kind; info.size = len(content) if kind == tarfile.REGTYPE else 0
            tar.addfile(info, io.BytesIO(content))
        Path(str(self.tar) + ".sha256").write_text(f"{m.digest(self.tar)}  {self.tar.name}\n")
    def build(self, snapshot=None):
        subprocess.run(["bash", "-c", IDENTITY], check=True)
        if snapshot:
            for name, content in snapshot.items():
                path = Path(name); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
        else: m.build()
        (self.root / "candidate").symlink_to(self.root, target_is_directory=True)
        os.environ["RECEIPT_SHA256"] = m.digest("macos-build/receipt.json")
    def __exit__(self, *args):
        self.env.stop(); os.chdir(self.old); self.tmp.cleanup()

class Tests(unittest.TestCase):
    def setUp(self):
        output = contextlib.redirect_stdout(io.StringIO()); output.__enter__(); self.addCleanup(output.__exit__, None, None, None)
    def test_build_install_receipts(self):
        for version in ("0.1.0", "0.1.1"):
            self.check_build_install_receipts(version)
    def check_build_install_receipts(self, version):
        with Fixture(version) as f:
            f.build(); m.install()
            build = json.loads(Path("macos-build/receipt.json").read_text()); install = json.loads(Path("macos-install/receipt.json").read_text())
            self.assertEqual([row["name"] for row in build["witnesses"]], m.WITNESSES)
            expected = [m.CARGO] + [["lightr-store" if arg == "lightr-oci" and name.startswith("store::") else arg for arg in m.CARGO] + ["--", name, "--exact", "--nocapture"] for name in m.WITNESSES]
            self.assertEqual([row["argv"] for row in build["commands"] if row["argv"][0] == "cargo"], expected)
            cleanup = re.findall(r"fn (cleanup_\w+)\(", (ROOT / "crates/lightr-oci/src/oci/layer/unix.rs").read_text())
            self.assertEqual({name.split("::")[-1] for name in m.WITNESSES if "::cleanup_" in name}, set(cleanup)); self.assertTrue(cleanup)
            self.assertEqual(install["qualification"], m.QUALIFICATION)
            self.assertEqual(build["sha256"], install["sha256"])
            for receipt in (build, install):
                self.assertEqual(receipt["version"], version)
                self.assertEqual(receipt["artifact"], f.tar.name)
                self.assertEqual(receipt["binary_version"], f"lightr {version} (aaaaaaa, 2026-09-30)")
                self.assertEqual(receipt["build_date_utc"], "2026-09-30")
            self.assertEqual(build["build"], "lightr --locked --release --features vz")
            self.assertEqual(Path("output").read_text(), f"receipt-sha256={m.digest('macos-build/receipt.json')}\nartifact-path=packaging/dist/{f.tar.name}\nchecksum-path=packaging/dist/{f.tar.name}.sha256\n")
            self.assertEqual(len([row for row in build["commands"] if row["argv"][-1] == "--version"]), 1)
            smoke = [row for row in install["commands"] if row["argv"][-1] in ("--version", "--help")]
            self.assertEqual(len(smoke), 2); self.assertTrue(all(row["output"] and row["exit_code"] == 0 for row in smoke))
            self.assertFalse(Path(smoke[0]["env"]["HOME"]).exists())
    def test_archive_identity_and_install_negative_controls(self):
        snapshot = None
        for defect in ("replacement", "missing", "missing-checksum", "missing-receipt", "binary", "mode", "symlink", "checksum", "duplicate", "receipt", "receipt-identity", "binary-hash", "identity", "arch", "plist", "bool", "smoke", "cleanup", "wrong-sha", "wrong-version", "bad-date"):
            with self.subTest(defect=defect), Fixture() as f:
                f.build(snapshot)
                if snapshot is None: snapshot = {str(path.relative_to(f.root)): path.read_bytes() for path in f.root.rglob("*") if path.is_file() and ("macos-build" in path.parts or path.parent == f.tar.parent)}
                if defect == "replacement":
                    f.tar.write_bytes(gzip.compress(gzip.decompress(f.tar.read_bytes()), mtime=0)); Path(str(f.tar) + ".sha256").write_text(f"{m.digest(f.tar)}  {f.tar.name}\n")
                if defect == "missing": f.tar.unlink()
                if defect == "missing-checksum": Path(str(f.tar) + ".sha256").unlink()
                if defect == "missing-receipt": Path("macos-build/receipt.json").unlink()
                if defect in ("receipt-identity", "binary-hash"):
                    receipt = json.loads(Path("macos-build/receipt.json").read_text()); receipt["candidate_sha" if defect == "receipt-identity" else "binary_sha256"] = "b" * 40 if defect == "receipt-identity" else "0" * 64
                    Path("macos-build/receipt.json").write_text(json.dumps(receipt)); os.environ["RECEIPT_SHA256"] = m.digest("macos-build/receipt.json")
                if defect in ("binary", "mode", "symlink", "smoke"):
                    f.pack(name="other" if defect == "binary" else "lightr", mode=0o644 if defect == "mode" else 0o755, kind=tarfile.SYMTYPE if defect == "symlink" else tarfile.REGTYPE, content=b"#!/bin/sh\nexit 1\n" if defect == "smoke" else None)
                    receipt = json.loads(Path("macos-build/receipt.json").read_text()); receipt["sha256"] = m.digest(f.tar)
                    if defect == "smoke": receipt["binary_sha256"] = __import__("hashlib").sha256(b"#!/bin/sh\nexit 1\n").hexdigest()
                    Path("macos-build/receipt.json").write_text(json.dumps(receipt)); os.environ["RECEIPT_SHA256"] = m.digest("macos-build/receipt.json")
                if defect in ("checksum", "duplicate"): Path(str(f.tar) + ".sha256").write_text("bad\n" if defect == "checksum" else Path(str(f.tar) + ".sha256").read_text() * 2)
                if defect == "receipt": os.environ["RECEIPT_SHA256"] = "0" * 64
                if defect == "identity": os.environ["WORKFLOW_SHA"] = "b" * 40
                if defect == "arch": os.environ["ARCH"] = "x86_64"
                if defect in ("plist", "bool"): os.environ["PLIST"] = "malformed" if defect == "plist" else '<plist><dict><key>com.apple.security.virtualization</key><string>true</string></dict></plist>'
                if defect == "cleanup": f.tool(f.root / "tools", "rm", "pass")
                if defect in ("wrong-sha", "wrong-version", "bad-date"):
                    os.environ["VERSION_OUTPUT"] = {"wrong-sha": "lightr 0.1.0 (bbbbbbb, 2026-09-30)", "wrong-version": "lightr 0.2.0 (aaaaaaa, 2026-09-30)", "bad-date": "lightr 0.1.0 (aaaaaaa, 2026-02-30)"}[defect]
                with self.assertRaises((ValueError, OSError)): m.install()
                self.assertFalse(Path("macos-install/receipt.json").exists())
                if defect not in ("smoke", "cleanup", "wrong-sha", "wrong-version", "bad-date"):
                    commands = json.loads(Path("macos-install/commands.json").read_text())
                    self.assertFalse(any(row["argv"][0] == "install" for row in commands))
    def test_witness_and_identity_controls(self):
        for count in ("0", "10"):
            with Fixture(), patch.dict(os.environ, COUNT=count), self.assertRaises(ValueError): m.build()
        valid = "test named ... ok\ntest result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 1s"
        m.witness(valid, "named")
        for text in ("", valid * 2, valid.replace("named", "other"), valid.replace("0 ignored", "1 ignored"), valid + "\nSKIPPED"):
            with self.assertRaises(ValueError): m.witness(text, "named")
        with Fixture() as f:
            f.tool(f.root / "tools", "cargo", "sys.exit(101)")
            with self.assertRaises(ValueError): m.build()
        with Fixture(), patch.dict(os.environ, LIGHTR_NET_TESTS="0"), self.assertRaises(ValueError): m.build()
        with Fixture(), patch.dict(os.environ, HEAD_SHA="b" * 40), self.assertRaises(ValueError): m.build()
    def test_source_identity_controls(self):
        for locale in ("C", "en_US.UTF-8"):
            for defect, sha in ((None, "a" * 40), ("sha39", "a" * 39), ("uppercase40", "A" * 40), ("main", "main"), ("sha41", "a" * 41), ("workflow", "a" * 40), ("head", "a" * 40)):
                with self.subTest(locale=locale, defect=defect), Fixture(), patch.dict(os.environ, LC_ALL=locale, CANDIDATE_SHA=sha, WORKFLOW_SHA=sha, HEAD_SHA=sha):
                    if defect == "workflow": os.environ["WORKFLOW_SHA"] = "b" * 40
                    if defect == "head": os.environ["HEAD_SHA"] = "b" * 40
                    result = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-c", IDENTITY], capture_output=True, text=True)
                    self.assertEqual(result.returncode == 0, defect is None, result.stderr)
                    e = m.Evidence("identity-control")
                    if defect is None: self.assertEqual(e.host()["candidate_sha"], sha)
                    else:
                        diagnostic = "checkout identity" if defect == "head" else "candidate identity"
                        self.assertIn(diagnostic, result.stderr)
                        with self.assertRaisesRegex(ValueError, diagnostic): e.host()
    def test_source_identity_mutations(self):
        source = (ROOT / "scripts/ci/macos_candidate.py").read_text()
        mutations = [('IDENTITY', None, 12),
                     ('re.fullmatch("[0-9a-f]{40}", sha)', 'True', 8),
                     ('sha == os.environ["WORKFLOW_SHA"]', 'True', 2),
                     ('self.run("git", "rev-parse", "HEAD") == sha', 'True', 2)]
        for before, after, failures in mutations:
            with self.subTest(mutation=before):
                if after is None: replacement = patch(__name__ + ".IDENTITY", "set -euo pipefail\ntrue\n")
                else:
                    self.assertEqual(source.count(before), 1)
                    mutant = types.ModuleType("mutant")
                    exec(compile(source.replace(before, after), "mutant", "exec"), mutant.__dict__)
                    replacement = patch(__name__ + ".m", mutant)
                with replacement:
                    result = unittest.TestResult(); Tests("test_source_identity_controls").run(result)
                self.assertEqual(result.errors, [], "unrelated identity harness error")
                self.assertEqual(len(result.failures), failures, "identity control accepted mutation")
    def test_source_version_and_receipt_controls(self):
        snapshot = None
        for phase in ("build", "install"):
            for defect in ("missing-file", "malformed", "missing-version", "wrong-type", "injected-version", "cli-version", "source-version", "receipt-version", "receipt-filename", "receipt-cli", "receipt-date", "checksum-filename"):
                if phase == "build" and defect in ("source-version", "receipt-version", "receipt-filename", "receipt-cli", "receipt-date", "checksum-filename"): continue
                with self.subTest(phase=phase, defect=defect), Fixture("0.1.1") as f:
                    if phase == "install":
                        f.build(snapshot)
                        if snapshot is None: snapshot = {str(path.relative_to(f.root)): path.read_bytes() for path in f.root.rglob("*") if path.is_file() and ("macos-build" in path.parts or path.parent == f.tar.parent)}
                    if defect == "missing-file": Path("Cargo.toml").unlink()
                    if defect in ("malformed", "missing-version", "wrong-type", "injected-version", "source-version"):
                        Path("Cargo.toml").write_text({"malformed": '[workspace.package\nversion = "0.1.1"', "missing-version": '[package]\nversion = "0.1.1"', "wrong-type": '[workspace.package]\nversion = 1', "injected-version": '[workspace.package]\nversion = "0.1.1/../../evil"', "source-version": '[workspace.package]\nversion = "0.1.0"'}[defect])
                    if defect == "cli-version": os.environ["VERSION_OUTPUT"] = "lightr 0.1.0 (aaaaaaa, 2026-09-30)"
                    if defect.startswith("receipt-"):
                        key, value = {"receipt-version": ("version", "0.1.0"), "receipt-filename": ("artifact", "../../evil.tar.gz"), "receipt-cli": ("binary_version", "lightr 0.1.1 (aaaaaaa, 2026-09-29)"), "receipt-date": ("build_date_utc", "2026-09-29")}[defect]
                        receipt = Path("macos-build/receipt.json"); data = json.loads(receipt.read_text()); data[key] = value
                        receipt.write_text(json.dumps(data)); os.environ["RECEIPT_SHA256"] = m.digest(receipt)
                    if defect == "checksum-filename": Path(str(f.tar) + ".sha256").write_text(f"{m.digest(f.tar)}  ../../evil.tar.gz\n")
                    with self.assertRaises(ValueError): getattr(m, phase)()
                    self.assertFalse(Path(f"macos-{'build' if phase == 'build' else 'install'}/receipt.json").exists())
                    if phase == "build": self.assertFalse(Path("output").exists())
    def test_declared_version_parser(self):
        for version in ("0.1.0", "0.1.1"):
            with Fixture(version): self.assertEqual(m.declared_version(), version)
        for content in (None, '', '[workspace.package\nversion = "0.1.1"', '[package]\nversion = "0.1.1"', '[workspace.package]\nversion = 1', '[workspace.package]\nversion = "../../evil"'):
            with Fixture():
                if content is None: Path("Cargo.toml").unlink()
                else: Path("Cargo.toml").write_text(content)
                with self.assertRaises(ValueError): m.declared_version()
    def test_source_captured_hugr_cli_version(self):
        # Build the actual CLI source as the approved package/version in a copy.
        # Cargo, build.rs, git SHA, and CLI execution are real, not metadata mocks.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns("target", "__pycache__", ".worktrees"))
            manifest = root / "Cargo.toml"
            manifest.write_text(manifest.read_text().replace(f'version = "{m.tomllib.loads(manifest.read_text())["workspace"]["package"]["version"]}"', 'version = "0.1.1"', 1))
            package = root / "crates/lightr-cli/Cargo.toml"
            old_name = m.tomllib.loads(package.read_text())["package"]["name"]
            package.write_text(package.read_text().replace(f'name = "{old_name}"', 'name = "hugr-lightr"', 1))
            env = dict(os.environ, SOURCE_DATE_EPOCH="1790726400")
            subprocess.run(["cargo", "+1.96.0", "build", "-p", "hugr-lightr", "--bin", "lightr"], cwd=root, env=env, check=True)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
            data = dict(version=m.tomllib.loads(manifest.read_text())["workspace"]["package"]["version"], candidate_sha=sha)
            e = m.Evidence(Path(directory) / "metadata")
            m.cli_version(e, root / "target/debug/lightr", data, env=env)
            self.assertEqual(data["build_date_utc"], "2026-09-30")
            self.assertTrue(data["binary_version"].startswith("lightr 0.1.1 ("))
            self.assertEqual(e.commands[0]["argv"], [str(root / "target/debug/lightr"), "--version"])
    def test_declared_version_mutations(self):
        source = (ROOT / "scripts/ci/macos_candidate.py").read_text()
        before = 'version = tomllib.load(manifest)["workspace"]["package"]["version"]'
        self.assertEqual(source.count(before), 1)
        for after in ('version = "0.1.0"', 'version = tomllib.load(manifest)["package"]["version"]'):
            mutant = types.ModuleType("mutant")
            exec(compile(source.replace(before, after), "mutant", "exec"), mutant.__dict__)
            with patch(__name__ + ".m", mutant):
                result = unittest.TestResult(); Tests("test_declared_version_parser").run(result)
            self.assertEqual(result.errors, [], "unrelated harness error")
            self.assertTrue(result.failures, "parser control accepted mutation")
    def test_archive_receipt_version_binding(self):
        with Fixture("0.1.1") as f:
            e = m.Evidence("archive-control")
            _, original = m.archive(e, f.tar.parent, "0.1.1")
            original["version"] = "0.1.1"
            for key, value in (("version", "0.1.0"), ("artifact", "../../evil.tar.gz"), ("artifact", "/tmp/evil.tar.gz"), ("artifact", "lightr-0.1.0-darwin-arm64-unsigned.tar.gz")):
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, "original receipt version/filename"):
                    m.archive(e, f.tar.parent, "0.1.1", dict(original, **{key: value}))
    def test_archive_receipt_binding_mutation(self):
        source = (ROOT / "scripts/ci/macos_candidate.py").read_text()
        before = 'require(expected["version"] == version and expected["artifact"] == artifact, "original receipt version/filename")'
        self.assertEqual(source.count(before), 1)
        mutant = types.ModuleType("mutant")
        exec(compile(source.replace(before, 'require(True, "mutant")'), "mutant", "exec"), mutant.__dict__)
        with patch(__name__ + ".m", mutant):
            result = unittest.TestResult(); Tests("test_archive_receipt_version_binding").run(result)
        self.assertEqual(result.errors, [], "unrelated harness error")
        self.assertEqual(len(result.failures), 4, "receipt control accepted mutation")
    def test_raw_output_and_witness(self):
        with Fixture():
            e = m.Evidence("raw-output")
            raw = b"\xff\xfe\n" + b"test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 1s\n"
            text = e.run(sys.executable, "-S", "-c", f"import os; os.write(1, {raw!r})")
            m.witness(text)
            self.assertEqual((e.path / "00.log").read_bytes(), raw)
            self.assertEqual(e.commands[0]["output"], raw.decode("utf-8", errors="replace"))
    def test_noop_smoke_cleanup_mutations(self):
        source = (ROOT / "scripts/ci/macos_candidate.py").read_text()
        changes = [
            ('version = e.run(str(binary), "--version", env=env)', 'version = "lightr 0.1.0 (aaaaaaa, 2026-09-30)"'),
            ('require(e.run(str(destination), "--help", env=env), "empty help smoke output")', 'e.run("true")'),
            ('e.run("rm", "-rf", str(home))', 'e.run("true")'),
        ]
        for before, after in changes:
            with self.subTest(command=before):
                self.assertEqual(source.count(before), 1)
                mutant = types.ModuleType("mutant")
                mutated = source.replace(before, after)
                if '"rm"' in before: mutated = mutated.replace('require(not home.exists(), "fresh HOME cleanup failed")', 'require(True, "mutant")')
                exec(compile(mutated, "mutant", "exec"), mutant.__dict__)
                with patch(__name__ + ".m", mutant):
                    result = unittest.TestResult(); Tests("test_build_install_receipts").run(result)
                self.assertEqual(result.testsRun, 1)
                self.assertEqual(result.errors, [], "mutation caused unrelated harness error")
                self.assertEqual(len(result.failures), 1, "positive control accepted no-op mutation")
    @unittest.skipUnless(sys.platform == "darwin", "Apple tool conformance requires Darwin; portable inspection fixtures still execute")
    def test_real_macos_architecture_and_entitlement_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "main.c"; source.write_text("int main(void) { return 0; }\n")
            for index, (arch, entitlement) in enumerate((("arm64", True), ("x86_64", True), ("arm64", "true"), ("arm64", False))):
                binary = root / "lightr"; plist = root / "entitlements.plist"
                plist.write_bytes(plistlib.dumps({"com.apple.security.virtualization": entitlement}))
                subprocess.run(["clang", "-arch", arch, str(source), "-o", str(binary)], check=True)
                subprocess.run(["codesign", "--force", "-s", "-", "--entitlements", str(plist), str(binary)], check=True)
                e = m.Evidence(root / f"logs-{index}")
                if arch == "arm64" and entitlement is True:
                    m.inspect(e, binary)
                    content = binary.read_bytes(); binary.write_bytes(content[:4096] + bytes([content[4096] ^ 1]) + content[4097:])
                    with self.assertRaises(ValueError): m.inspect(e, binary)
                else:
                    with self.assertRaises(ValueError): m.inspect(e, binary)
        Tests.apple_controls_executed = True

if __name__ == "__main__":
    apple = "--require-apple-controls" in sys.argv
    if apple:
        sys.argv.remove("--require-apple-controls")
        m.require(sys.platform == "darwin", "hosted guard requires Darwin Apple controls")
    result = unittest.main(exit=False).result
    m.require(not apple or (not result.skipped and getattr(Tests, "apple_controls_executed", False)), "hosted guard skipped Apple controls")
    sys.exit(not result.wasSuccessful())
