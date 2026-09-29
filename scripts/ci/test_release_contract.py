"""Release contract guard: parser-backed matrix plus installer checksum teeth."""
import copy
import hashlib
import io
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/release.yml"
INSTALLER = ROOT / "packaging/install.sh"
EXPECTED_TARGETS = {
    ("macos-14", "darwin", "arm64", "aarch64-apple-darwin"),
    ("ubuntu-latest", "linux", "x86_64", "x86_64-unknown-linux-gnu"),
}
REMOTE_ACTIONS = ("actions/upload-artifact@", "softprops/action-gh-release@")


def release_targets(document):
    try:
        entries = document["jobs"]["build"]["strategy"]["matrix"]["include"]
    except (KeyError, TypeError) as exc:
        raise ValueError("release build matrix missing") from exc
    if not isinstance(entries, list) or not entries:
        raise ValueError("release build matrix empty")
    targets = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("release matrix entry malformed")
        try:
            targets.add(tuple(entry[key] for key in ("runner", "os-tag", "arch-tag", "rust-target")))
        except KeyError as exc:
            raise ValueError("release matrix field missing") from exc
    if len(targets) != len(entries):
        raise ValueError("release matrix duplicate target")
    return targets


def validate_target_matrix(document):
    targets = release_targets(document)
    if targets != EXPECTED_TARGETS:
        raise ValueError(f"public artifact matrix mismatch: {targets}")


def validate_owner_gate(document):
    trigger = document.get("on", document.get(True))
    if not isinstance(trigger, dict) or set(trigger) != {"workflow_dispatch"}:
        raise ValueError("release workflow must be manual-dispatch only")
    inputs = trigger["workflow_dispatch"].get("inputs")
    if not isinstance(inputs, dict) or set(inputs) != {"candidate_sha", "release_tag"}:
        raise ValueError("manual release inputs mismatch")
    if not all(inputs[name].get("required") is True for name in inputs):
        raise ValueError("manual release input is not required")
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        raise ValueError("release jobs missing")
    remote_count = 0
    for name, job in jobs.items():
        steps = job.get("steps", []) if isinstance(job, dict) else []
        if any(action in str(step.get("uses", "")) for step in steps for action in REMOTE_ACTIONS):
            remote_count += 1
            if job.get("environment") != "G-PUBLISH":
                raise ValueError(f"remote action without G-PUBLISH gate: {name}")
    if remote_count != 2:
        raise ValueError("expected upload and draft-release remote actions")
    build = jobs.get("build", {})
    entries = build.get("strategy", {}).get("matrix", {}).get("include", [])
    macos = [entry for entry in entries if entry.get("os-tag") == "darwin"]
    if len(macos) != 1 or macos[0].get("features") != "vz":
        raise ValueError("macOS artifact must build lightr-cli with vz")
    if "--features \"${{ matrix.features }}\"" not in str(build):
        raise ValueError("macOS feature matrix is not used by build command")
    if "${{ inputs.release_tag }}" not in str(jobs.get("release", {})):
        raise ValueError("draft release does not use owner-selected tag")


class ReleaseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.safe_load(WORKFLOW.read_text())

    def test_public_artifact_matrix_is_exact(self):
        validate_target_matrix(self.document)

    def test_remote_release_requires_manual_owner_gate(self):
        validate_owner_gate(self.document)

    def test_matrix_mutation_is_rejected(self):
        mutated = copy.deepcopy(self.document)
        mutated["jobs"]["build"]["strategy"]["matrix"]["include"].append({
            "runner": "windows-latest", "os-tag": "windows", "arch-tag": "x86_64",
            "rust-target": "x86_64-pc-windows-msvc",
        })
        with self.assertRaises(ValueError):
            validate_target_matrix(mutated)

    def test_owner_gate_mutations_are_rejected(self):
        tag_trigger = copy.deepcopy(self.document)
        tag_trigger[True] = {"push": {"tags": ["v*"]}}
        with self.assertRaises(ValueError):
            validate_owner_gate(tag_trigger)

        ungated_upload = copy.deepcopy(self.document)
        ungated_upload["jobs"]["build"].pop("environment")
        with self.assertRaises(ValueError):
            validate_owner_gate(ungated_upload)

        no_vz = copy.deepcopy(self.document)
        no_vz["jobs"]["build"]["strategy"]["matrix"]["include"][0]["features"] = ""
        with self.assertRaises(ValueError):
            validate_owner_gate(no_vz)

        missing_upload = copy.deepcopy(self.document)
        missing_upload["jobs"]["build"]["steps"] = [
            step for step in missing_upload["jobs"]["build"]["steps"]
            if "upload-artifact" not in step.get("uses", "")
        ]
        with self.assertRaises(ValueError):
            validate_owner_gate(missing_upload)

    def test_release_uploads_individual_checksum_files(self):
        files = self.document["jobs"]["release"]["steps"][-1]["with"]["files"]
        self.assertIn("dist/*.tar.gz", files)
        self.assertIn("dist/*.sha256", files)
        self.assertIn("dist/SHA256SUMS", files)

    def test_installer_rejects_checksum_hash_and_filename_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "lightr-0.1.0-linux-x86_64.tar.gz"
            with tarfile.open(artifact, "w:gz") as archive:
                payload = b"#!/bin/sh\necho lightr 0.1.0\n"
                info = tarfile.TarInfo("lightr")
                info.mode = 0o755
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            for checksum, expected in (
                (f"{'0' * 64}  {artifact.name}\n", "checksum mismatch"),
                (f"{digest}  wrong-name.tar.gz\n", "invalid checksum entry"),
            ):
                with self.subTest(expected=expected):
                    checksum_file = root / "fixture.sha256"
                    checksum_file.write_text(checksum)
                    result = self.run_installer(root, artifact, checksum_file)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(expected, result.stderr)

    def run_installer(self, root, artifact, checksum):
        script = root / "install.sh"
        script.write_text(INSTALLER.read_text().replace(
            "__PLACEHOLDER__RELEASES_URL__", "https://release.invalid"
        ).replace("__PLACEHOLDER__VERSION__", "0.1.0"))
        bin_dir = root / "bin"
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / "uname").write_text("#!/bin/sh\n[ \"$1\" = -s ] && echo Linux || echo x86_64\n")
        (bin_dir / "curl").write_text(
            "#!/bin/sh\ncase \"$4\" in *.sha256) cp \"$FIXTURE_CHECKSUM\" \"$3\" ;; *) cp \"$FIXTURE_ARTIFACT\" \"$3\" ;; esac\n"
        )
        os.chmod(bin_dir / "uname", 0o755)
        os.chmod(bin_dir / "curl", 0o755)
        home = root / "home"
        home.mkdir(exist_ok=True)
        env = dict(os.environ, PATH=f"{bin_dir}:/usr/bin:/bin", HOME=str(home),
                   FIXTURE_ARTIFACT=str(artifact), FIXTURE_CHECKSUM=str(checksum))
        return subprocess.run(["sh", str(script)], env=env, capture_output=True,
                              text=True, timeout=15)


if __name__ == "__main__":
    unittest.main()
