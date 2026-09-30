"""Shell conformance: real checksum/tar/install, fixture CLI/cargo/host; not Linux qualification."""
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/r1-linux-x86_64-rc.yml"
DOWNLOAD = "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"

def run_text(document, name, job="verify"):
    return next(step["run"] for step in document["jobs"][job]["steps"] if step.get("name") == name)

class Fixture:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="r1 r3 ")
        self.root = Path(self.tmp.name)
        tools = self.root / "tools"
        tools.mkdir()
        self.env = dict(os.environ, PATH=f"{tools}:{os.environ['PATH']}", CANDIDATE_SHA="a" * 40,
                        WORKFLOW_SHA="a" * 40, ARTIFACT_ID="123", ARTIFACT_SOURCE="https://fixture/artifacts/123",
                        RUSTFLAGS="-D warnings", LIGHTR_NET_TESTS="1", CALLS=str(self.root / "calls"),
                        SMOKE=str(self.root / "smoke"), MODE="1")
        for name, code in {
            "uname": "print('Linux' if sys.argv[1] == '-s' else 'x86_64')",
            "rustc": "print('rustc fixture')",
            "cargo": """args = sys.argv[1:]
if 'oci::tests::pull_tests::test_pull_alpine_network_gated' in args: assert os.environ.get('LIGHTR_NET_TESTS') == '1', 'network witness not enabled at invocation'
with open(os.environ['CALLS'], 'a') as f: f.write(json.dumps(['cargo'] + args) + '\\n')
mode = os.environ['MODE']
if mode == 'exit': sys.exit(1)
if mode != 'empty':
    if '--exact' in args: print('test ' + ('wrong' if mode == 'wrong' else args[-2]) + ' ... ok')
    summary = f"test result: ok. {mode if mode.isdigit() else '1'} passed; 0 failed; {1 if mode == 'ignored' else 0} ignored; 0 measured; 0 filtered out; finished in 0.01s"
    print(summary + ('\\n' + summary if mode == 'duplicate' else ''))
""",
        }.items():
            path = tools / name
            path.write_text(f"#!{sys.executable}\nimport os, sys, json\n{code}\n")
            path.chmod(0o755)
        return self
    def __exit__(self, *args):
        self.tmp.cleanup()
    def execute(self, script, cwd=None):
        return subprocess.run(["bash", "-c", script], cwd=cwd or self.root, env=self.env,
                              capture_output=True, text=True, timeout=30)
    def artifact(self, document, defect=None):
        (self.root / "Cargo.toml").write_text('[workspace.package]\nversion = "0.1.0"\n')
        receipt = self.root / "r1-receipt"
        receipt.mkdir(exist_ok=True)
        for name in ("commands", "witnesses"):
            if not (receipt / f"{name}.jsonl").exists(): (receipt / f"{name}.jsonl").write_text("")
        (receipt / "env.json").write_text(json.dumps({key: self.env[key] for key in ("LIGHTR_NET_TESTS", "RUSTFLAGS")}))
        binary = self.root / "lightr"
        binary.write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> "$SMOKE"\nif [ "${SMOKE_FAIL:-}" = "$1" ]; then exit 1; fi\ncase "$1" in --version|--help) printf "lightr fixture\\n";; *) exit 2;; esac\n')
        binary.chmod(0o755)
        dist = self.root / "packaging/dist"
        dist.mkdir(parents=True)
        self.tar = dist / "lightr-0.1.0-linux-x86_64.tar.gz"
        with tarfile.open(self.tar, "w:gz") as archive: archive.add(binary, arcname="lightr")
        self.checksum = Path(str(self.tar) + ".sha256")
        self.checksum.write_text(f"{hashlib.sha256(self.tar.read_bytes()).hexdigest()}  {self.tar.name}\n")
        if defect == "corrupt": self.tar.write_bytes(b"corrupt")
        if defect == "missing": self.tar.unlink()
        if defect == "checksum": self.checksum.unlink()
        if defect == "name": self.checksum.write_text(self.checksum.read_text().replace(self.tar.name, "other.tar.gz"))
        if defect == "extra": self.checksum.write_text(self.checksum.read_text() * 2)
        result = self.execute(run_text(document, "Verify artifact and checksum"))
        if result.returncode:
            raise ValueError("R1 artifact conformance: " + result.stdout + result.stderr)
        self.r1 = receipt / "R1-linux-x86_64.json"
        data = json.loads(self.r1.read_text())
        assert data["commands"][-1]["argv"] == ["sha256sum", "-c", self.checksum.name] and data["env"] == {"LIGHTR_NET_TESTS": "1", "RUSTFLAGS": "-D warnings"}

    def install(self, document):
        download = self.root / "r1"
        for directory in ("packaging", "r1-receipt"):
            shutil.copytree(self.root / directory, download / directory)
        return self.execute(run_text(document, "Verify install smoke and cleanup", "clean-install"))

def probe_witnesses(document, expected):
    with Fixture() as fixture:
        result = fixture.execute(run_text(document, "Run required OCI witnesses"))
        try:
            witnesses = [json.loads(line) for line in (fixture.root / "r1-receipt/witnesses.jsonl").read_text().splitlines()]
            commands = [json.loads(line) for line in (fixture.root / "r1-receipt/commands.jsonl").read_text().splitlines()]
            calls = [json.loads(line) for line in (fixture.root / "calls").read_text().splitlines()]
            assert result.returncode == 0 and {row["name"] for row in witnesses} == expected and len(witnesses) == len(expected) and len(commands) == len(expected) + 1
            assert [row["argv"] for row in commands] == calls and all(row["exit_code"] == 0 for row in commands)
            assert all(row["outcome"] == "passed" and row["negative_control"] == ("reject" in row["name"]) for row in witnesses)
            fixture.artifact(document)
            receipt = json.loads(fixture.r1.read_text())
            assert receipt["witnesses"] == witnesses and receipt["commands"][:-1] == commands and receipt["negative_controls"] == [row for row in witnesses if row["negative_control"]]
        except (OSError, AssertionError, KeyError) as exc:
            raise ValueError("R1 executed witness/receipt conformance failed") from exc
    with Fixture() as fixture:
        fixture.env["MODE"] = "10"
        if fixture.execute(run_text(document, "Run required OCI witnesses")).returncode == 0:
            raise ValueError("R1 accepted wrong executed witness count")

def probe_install(document):
    with Fixture() as fixture:
        fixture.artifact(document)
        result = fixture.install(document)
        try:
            assert result.returncode == 0, result.stdout + result.stderr
            assert (fixture.root / "smoke").read_text().splitlines() == ["--version", "--help"]
            receipt = json.loads((fixture.root / "r3-receipt/R3-linux-x86_64.json").read_text())
            commands = receipt["commands"]
            assert commands[0]["argv"] == ["sha256sum", "-c", fixture.checksum.name]
            assert [row["argv"][0].split("/")[-1] for row in commands] == ["sha256sum", "tar", "install", "lightr", "lightr", "rm"]
            assert all(row["exit_code"] == 0 for row in commands) and not Path(commands[-1]["argv"][-1]).exists() and receipt["sha256"] == json.loads(fixture.r1.read_text())["sha256"]
        except (OSError, AssertionError, KeyError) as exc:
            raise ValueError("R3 executed install/smoke/cleanup conformance failed") from exc

class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.document = yaml.safe_load(WORKFLOW.read_text())
    def test_r1_artifact_negative_controls(self):
        for defect in ("corrupt", "missing", "checksum", "name", "extra"):
            with self.subTest(defect=defect), Fixture() as fixture, self.assertRaises(ValueError):
                fixture.artifact(self.document, defect)

    def test_exact_witness_count_and_name(self):
        for mode in ("1", "0", "10", "ignored", "duplicate", "empty", "wrong", "exit"):
            with self.subTest(mode=mode), Fixture() as fixture:
                fixture.env["MODE"] = mode
                result = fixture.execute(run_text(self.document, "Run required OCI witnesses"))
                self.assertEqual(result.returncode == 0, mode == "1", result.stdout + result.stderr)

    def test_corrupt_missing_identity_and_binary_reject_before_install(self):
        for defect in ("corrupt", "missing", "checksum", "binary", "sha", "binary_sha", "recompressed", "replacement_pair"):
            with self.subTest(defect=defect), Fixture() as fixture:
                fixture.artifact(self.document)
                data = json.loads(fixture.r1.read_text())
                if defect == "corrupt": fixture.tar.write_bytes(b"corrupt")
                if defect == "missing": fixture.tar.unlink()
                if defect == "checksum": fixture.checksum.unlink()
                if defect == "sha": data["candidate_sha"] = "b" * 40
                if defect == "binary_sha": data["binary_sha256"] = "0" * 64
                if defect in ("recompressed", "replacement_pair"):
                    fixture.tar.write_bytes(gzip.compress(gzip.decompress(fixture.tar.read_bytes()), mtime=0))
                    self.assertNotEqual(hashlib.sha256(fixture.tar.read_bytes()).hexdigest(), data["sha256"])
                    with tarfile.open(fixture.tar) as archive: self.assertEqual(hashlib.sha256(archive.extractfile("lightr").read()).hexdigest(), data["binary_sha256"])
                    if defect == "replacement_pair": fixture.checksum.write_text(f"{hashlib.sha256(fixture.tar.read_bytes()).hexdigest()}  {fixture.tar.name}\n")
                if defect == "binary":
                    with tarfile.open(fixture.tar, "w:gz") as archive: archive.add(fixture.root / "lightr", arcname="other")
                    data["sha256"] = hashlib.sha256(fixture.tar.read_bytes()).hexdigest()
                    fixture.checksum.write_text(f"{data['sha256']}  {fixture.tar.name}\n")
                fixture.r1.write_text(json.dumps(data))
                self.assertNotEqual(fixture.install(self.document).returncode, 0)
                self.assertFalse((fixture.root / "smoke").exists())
                log = fixture.root / "r3-receipt/commands.jsonl"
                self.assertFalse(log.exists() and any(json.loads(line)["argv"][0] == "install" for line in log.read_text().splitlines()))

    def test_smoke_and_cleanup_noop_mutations_red(self):
        for line in ('run "$HOME/.local/bin/lightr" --version', 'run "$HOME/.local/bin/lightr" --help', 'run rm -rf "$HOME"', 'run sha256sum -c "$ARTIFACT.sha256"'):
            candidate = copy.deepcopy(self.document)
            step = candidate["jobs"]["clean-install"]["steps"][1]
            step["run"] = step["run"].replace(line, 'run sha256sum "$ARTIFACT"' if "sha256sum" in line else "run true")
            with self.subTest(line=line), self.assertRaises(ValueError): probe_install(candidate)

    def test_smoke_failure_blocks_receipt(self):
        for flag in ("--version", "--help"):
            with self.subTest(flag=flag), Fixture() as fixture:
                fixture.artifact(self.document)
                fixture.env["SMOKE_FAIL"] = flag
                self.assertNotEqual(fixture.install(self.document).returncode, 0)
                self.assertFalse((fixture.root / "r3-receipt/R3-linux-x86_64.json").exists())

if __name__ == "__main__":
    unittest.main()
