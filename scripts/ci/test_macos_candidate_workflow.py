"""Closed hosted workflow contract and executable source/host guard controls.
Depends on the runtime helper/fixtures landed before this workflow slice.
"""
import copy
import os
from pathlib import Path
import subprocess
import sys
import unittest
import yaml
import macos_candidate as m
from test_macos_candidate import Fixture, IDENTITY

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/macos-arm64-candidate.yml"
PINS = ["actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
        "dtolnay/rust-toolchain@ebb3d1676050bfd0971c36c1e215b5751473994d",
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
        "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"]
HOST_IDENTITY = IDENTITY + 'test "$(uname -s)" = Darwin\ntest "$(uname -m)" = arm64\ntest "$(sysctl -n hw.optional.arm64)" = 1\n'
GUARDS = ('set -euo pipefail\npython3 -m venv "$RUNNER_TEMP/macos-guards"\n'
          '"$RUNNER_TEMP/macos-guards/bin/python" -m pip install PyYAML==6.0.2\n'
          '"$RUNNER_TEMP/macos-guards/bin/python" scripts/ci/test_macos_candidate.py --require-apple-controls\n'
          '"$RUNNER_TEMP/macos-guards/bin/python" scripts/ci/test_macos_candidate_workflow.py\n')

def contract(doc):
    m.require(set(doc) == {"name", True, "permissions", "env", "jobs"}, "closed workflow keys")
    m.require(doc[True] == {"workflow_dispatch": {"inputs": {"candidate_sha": {"description": "Immutable lowercase 40-character candidate commit", "required": True, "type": "string"}}}}, "manual dispatch only")
    m.require(doc["permissions"] == {"contents": "read"} and doc["env"] == {"CANDIDATE_SHA": "${{ inputs.candidate_sha }}", "WORKFLOW_SHA": "${{ github.sha }}"}, "read permissions/identity env")
    m.require(set(doc["jobs"]) == {"build", "clean-install"}, "closed jobs")
    for name, job in doc["jobs"].items():
        extra = {"outputs"} if name == "build" else {"needs", "permissions"}
        m.require(set(job) == {"runs-on", "timeout-minutes", "env", "steps"} | extra and job["runs-on"] == "macos-14", "closed native jobs; no skips/tolerance")
        steps = job["steps"]
        expected = [PINS[0], "identity", PINS[1], "guards", "build", PINS[2], PINS[2]] if name == "build" else [PINS[0], "identity", PINS[3], "install", PINS[2]]
        m.require(len(steps) == len(expected), "missing/extra steps")
        for index, (step, kind) in enumerate(zip(steps, expected)):
            keys = {"uses", "with"} if "@" in kind else {"name", "shell", "run"}
            if name == "build" and kind in ("build", PINS[2]) and index != 6: keys.add("id")
            if index == len(steps) - 1: keys.add("if")
            m.require(set(step) == keys, "closed steps; no skips/tolerance")
            if "@" not in kind:
                run = {"identity": HOST_IDENTITY, "guards": GUARDS, "build": "python3 scripts/ci/macos_candidate.py build", "install": "python3 scripts/ci/macos_candidate.py install"}[kind]
                m.require(step["run"] == run and step["shell"] == "bash", "exact executable commands")
            else:
                m.require(step["uses"] == kind, "pinned closed actions")
                settings = step["with"]
                if kind == PINS[0]: expected_settings = dict(ref="${{ inputs.candidate_sha }}", **{"persist-credentials": False})
                elif kind == PINS[1]: expected_settings = dict(toolchain="1.96.0", targets="aarch64-apple-darwin")
                elif kind == PINS[3]: expected_settings = {"artifact-ids": "${{ needs.build.outputs.artifact-id }}", "merge-multiple": True, "path": "candidate"}
                else:
                    path = "macos-install/" if name != "build" else ("macos-build/" if index == 6 else f"packaging/dist/{m.ARTIFACT}\npackaging/dist/{m.ARTIFACT}.sha256\nmacos-build/\n")
                    artifact_name = "macos-install" if name != "build" else ("macos-build-logs" if index == 6 else "macos-candidate")
                    expected_settings = {"name": artifact_name + "-${{ inputs.candidate_sha }}", "path": path, "if-no-files-found": "error", "retention-days": 30}
                m.require(settings == expected_settings, "immutable download or receipt/log retention")
            if "if" in step: m.require(step["if"] == "${{ always() }}", "mandatory log retention")
        if name == "build":
            m.require(job["env"] == {"LIGHTR_NET_TESTS": "1", "RUSTFLAGS": "-D warnings -C link-arg=-Wl,-rpath,/usr/lib/swift"} and job["outputs"] == {"artifact-id": "${{ steps.upload.outputs.artifact-id }}", "receipt-sha256": "${{ steps.build.outputs.receipt-sha256 }}"}, "witness env/immutable outputs")
            m.require(steps[4]["id"] == "build" and steps[5]["id"] == "upload", "output step IDs")
        else:
            m.require(job["needs"] == "build" and job["permissions"] == {"contents": "read", "actions": "read"}, "fresh dependent install/read permissions")
            m.require(job["env"] == {"ARTIFACT_ID": "${{ needs.build.outputs.artifact-id }}", "RECEIPT_SHA256": "${{ needs.build.outputs.receipt-sha256 }}", "ARTIFACT_SOURCE": "https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }}/artifacts/${{ needs.build.outputs.artifact-id }}"}, "receipt/artifact binding")

class Tests(unittest.TestCase):
    def test_workflow_and_mutations(self):
        doc = yaml.safe_load(WORKFLOW.read_text()); contract(doc)
        mutations = [lambda d: d["jobs"].update(publish={}), lambda d: d["permissions"].update(contents="write"), lambda d: d.update(permissions={})]
        for job in doc["jobs"]:
            for key, value in (("if", False), ("continue-on-error", True), ("permissions", {"contents": "write"})):
                mutations.append(lambda d, j=job, k=key, v=value: d["jobs"][j].update({k: v}))
            for i in range(len(doc["jobs"][job]["steps"])):
                for key, value in (("if", False), ("continue-on-error", True), ("run", "true"), ("uses", "evil/action@main")):
                    mutations.append(lambda d, j=job, n=i, k=key, v=value: d["jobs"][j]["steps"][n].update({k: v}))
                mutations.append(lambda d, j=job, n=i: d["jobs"][j]["steps"].pop(n))
                for key in doc["jobs"][job]["steps"][i].get("with", {}):
                    mutations.append(lambda d, j=job, n=i, k=key: d["jobs"][j]["steps"][n]["with"].pop(k))
        for mutation in mutations:
            changed = copy.deepcopy(doc); mutation(changed)
            with self.assertRaises(ValueError): contract(changed)
    def test_actual_source_host_guard(self):
        script = yaml.safe_load(WORKFLOW.read_text())["jobs"]["build"]["steps"][1]["run"]
        for defect in (None, "sha", "workflow", "head", "os", "arch", "capability"):
            with self.subTest(defect=defect), Fixture() as f:
                if defect == "sha": os.environ["CANDIDATE_SHA"] = "A" * 40
                if defect == "workflow": os.environ["WORKFLOW_SHA"] = "b" * 40
                if defect == "head": f.tool(f.root / "tools", "git", "print('b' * 40)")
                if defect in ("os", "arch"): f.tool(f.root / "tools", "uname", "print('Linux' if sys.argv[1] == '-s' else 'arm64')" if defect == "os" else "print('Darwin' if sys.argv[1] == '-s' else 'x86_64')")
                if defect == "capability": f.tool(f.root / "tools", "sysctl", "print('0')")
                result = subprocess.run(["bash", "-c", script], capture_output=True)
                self.assertEqual(result.returncode == 0, defect is None)
    def test_hosted_guard_rejects_non_darwin(self):
        script = str(Path(m.__file__).with_name("test_macos_candidate.py"))
        code = f"import runpy, sys; sys.path.insert(0, {str(Path(script).parent)!r}); sys.platform='linux'; sys.argv=[{script!r}, '--require-apple-controls']; runpy.run_path({script!r}, run_name='__main__')"
        result = subprocess.run([sys.executable, "-S", "-c", code], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hosted guard requires Darwin Apple controls", result.stderr)
    def test_hosted_guard_rejects_skipped_or_missing_apple_controls(self):
        script = str(Path(m.__file__).with_name("test_macos_candidate.py"))
        for skipped in (True, False):
            with self.subTest(skipped=skipped):
                test = "Tests.test_real_macos_architecture_and_entitlement_controls" if skipped else "Tests.test_raw_output_and_witness"
                setup = "unittest.skipUnless=lambda *_: unittest.skip('controlled skip'); " if skipped else ""
                code = f"import runpy, sys, unittest; sys.path.insert(0, {str(Path(script).parent)!r}); sys.platform='darwin'; {setup}sys.argv=[{script!r}, '--require-apple-controls', {test!r}]; runpy.run_path({script!r}, run_name='__main__')"
                result = subprocess.run([sys.executable, "-S", "-c", code], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("hosted guard skipped Apple controls", result.stderr)

if __name__ == "__main__":
    unittest.main()
