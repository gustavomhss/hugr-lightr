"""Fail-closed contract and mutation teeth for R1 Linux RC workflow."""
import copy
import json
import textwrap
import unittest
from pathlib import Path

import yaml
import test_packaged_s5 as packaged_s5
from test_r1_r3_execution import probe_witnesses, probe_install, DOWNLOAD


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/r1-linux-x86_64-rc.yml"
WITNESSES = {
    "oci::tests::integrity_tests::test_write_through_symlink_component_rejects_import_without_ref",
    "store::image_ref::tests::concurrent_tuple_reads_never_observe_mixed_publication",
    "oci::tests::import_tests::test_import_layout_two_layers_whiteout_and_hydrate",
    "oci::load::load_tests::save_load_roundtrip_lossless",
    "oci::tests::pull_tests::test_pull_alpine_network_gated",
    "oci::tests::import_tests::test_path_escape_rejects_import_without_ref",
    "oci::layer::unix::tests::cleanup_removes_owned_stage_before_drop",
    "oci::layer::unix::tests::cleanup_rejects_replaced_stage_and_preserves_both_trees",
}
FORBIDDEN = ("softprops/action-gh-release@", "gh release", "cargo publish", "git tag", "git push")
CHECKOUT = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
TOOLCHAIN = "dtolnay/rust-toolchain@ebb3d1676050bfd0971c36c1e215b5751473994d"
UPLOAD = "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
EXPECTED_RUNS = {
    "Verify immutable candidate identity": """
        set -euo pipefail
        case "$CANDIDATE_SHA" in
          [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
          *) echo "candidate_sha must be a lowercase 40-character commit SHA" >&2; exit 1 ;;
        esac
        git cat-file -e "${CANDIDATE_SHA}^{commit}"
        test "$(git rev-parse HEAD)" = "$CANDIDATE_SHA"
        test "$WORKFLOW_SHA" = "$CANDIDATE_SHA"
    """,
}


def trigger(document):
    return document.get("on", document.get(True))


def steps(document):
    try:
        values = document["jobs"]["verify"]["steps"]
    except (KeyError, TypeError) as exc:
        raise ValueError("R1 verify steps missing") from exc
    if not isinstance(values, list) or not values:
        raise ValueError("R1 verify steps empty")
    return values


def all_text(document):
    return json.dumps(document["jobs"])


def step_named(document, name):
    for step in steps(document):
        if step.get("name") == name:
            return step
    raise ValueError(f"R1 step missing: {name}")


def require_run_line(document, step_name, line):
    run = step_named(document, step_name).get("run", "")
    if line not in (run_line.lstrip() for run_line in run.splitlines()):
        raise ValueError(f"R1 executable control missing: {line}")


def require_exact_run(document, step_name):
    actual = step_named(document, step_name).get("run", "").strip()
    expected = textwrap.dedent(EXPECTED_RUNS[step_name]).strip()
    if actual != expected:
        raise ValueError(f"R1 executable path changed: {step_name}")


def validate(document):
    permissions = {"verify": {"contents": "read"}, "clean-install": {"actions": "read"}}
    jobs = document.get("jobs", {})
    if not isinstance(jobs, dict) or set(jobs) != set(permissions):
        raise ValueError("R1/R3 jobs must be exactly verify and clean-install")
    if document.get("permissions") != permissions["verify"] or any(not isinstance(job, dict) or "uses" in job or "if" in job or job.get("continue-on-error") or job.get("permissions", document["permissions"]) != permissions[name] for name, job in jobs.items()):
        raise ValueError("R1/R3 permissions, job skip/tolerance, or reusable-job surface changed")
    for name, job in jobs.items():
        required = job.get("steps")
        if not isinstance(required, list) or not required or any(not isinstance(step, dict) or "if" in step or "continue-on-error" in step for step in required):
            raise ValueError(f"R1/R3 required steps missing/empty/malformed or skip/tolerance set: {name}")
    event = trigger(document)
    if not isinstance(event, dict) or set(event) != {"workflow_dispatch"}:
        raise ValueError("R1 workflow must be manual-dispatch only")
    inputs = event["workflow_dispatch"].get("inputs")
    if not isinstance(inputs, dict) or set(inputs) != {"candidate_sha"}:
        raise ValueError("R1 workflow requires only candidate_sha")
    if inputs["candidate_sha"].get("required") is not True:
        raise ValueError("candidate_sha must be required")
    job = document.get("jobs", {}).get("verify")
    if not isinstance(job, dict) or job.get("runs-on") != "ubuntu-24.04":
        raise ValueError("R1 must run on pinned Linux runner")
    if job.get("env", {}).get("WORKFLOW_SHA") != "${{ github.sha }}":
        raise ValueError("R1 workflow revision must be bound to candidate")
    checkout = steps(document)[0]
    if checkout.get("uses") != CHECKOUT or checkout.get("with", {}).get("ref") != "${{ inputs.candidate_sha }}":
        raise ValueError("R1 checkout must use candidate_sha exactly")
    if step_named(document, "Install pinned Rust").get("uses") != TOOLCHAIN:
        raise ValueError("R1 toolchain action must be pinned")
    if step_named(document, "Upload R1 receipt").get("uses") != UPLOAD:
        raise ValueError("R1 artifact action must be pinned")
    for step_name in EXPECTED_RUNS:
        require_exact_run(document, step_name)
    for step_name, line in (
        ("Verify immutable candidate identity", 'git cat-file -e "${CANDIDATE_SHA}^{commit}"'),
        ("Verify immutable candidate identity", 'test "$(git rev-parse HEAD)" = "$CANDIDATE_SHA"'),
        ("Run required OCI witnesses", "cargo +1.96.0 test --locked -p lightr-oci --lib |& tee r1-receipt/oci-full.log"),
        ("Build locked Linux artifact", "bash packaging/release.sh |& tee r1-receipt/package.log"),
        ("Verify artifact and checksum", 'test -s "$ARTIFACT"'),
        ("Verify artifact and checksum", 'test -s "$CHECKSUM"'),
        ("Verify artifact and checksum", 'test "$(wc -l < "$CHECKSUM")" -eq 1'),
        ("Verify artifact and checksum", "grep -Eq '^[0-9a-f]{64}  [^[:space:]]+$' \"$CHECKSUM\""),
        ("Verify artifact and checksum", 'test "$(awk \'{print $2}\' "$CHECKSUM")" = "$ARTIFACT_NAME"'),
        ("Verify artifact and checksum", '(cd "$(dirname "$CHECKSUM")" && sha256sum -c "$(basename "$CHECKSUM")")'),
        ("Run required OCI witnesses", 'for witness in "${WITNESSES[@]}"; do'),
        ("Run required OCI witnesses", 'cargo +1.96.0 test --locked -p "$package" --lib -- "$witness" --exact |& tee "r1-receipt/${witness##*::}.log"'),
    ):
        require_run_line(document, step_name, line)
    text = all_text(document)
    if "R1-linux-x86_64.json" not in text:
        raise ValueError("R1 receipt JSON missing")
    witness_env = step_named(document, "Run required OCI witnesses").get("env", {})
    if witness_env.get("LIGHTR_NET_TESTS") != "1":
        raise ValueError("R1 pull witness is not enabled")
    for witness in WITNESSES:
        if witness not in text:
            raise ValueError(f"R1 witness missing: {witness}")
    for forbidden in FORBIDDEN:
        if forbidden in text:
            raise ValueError(f"R1 forbidden remote action: {forbidden}")
    uses = [str(step.get("uses", "")) for step in steps(document)]
    if set(uses) != {"", CHECKOUT, TOOLCHAIN, UPLOAD}:
        raise ValueError("R1 action surface changed")
    if uses.count(UPLOAD) != 1:
        raise ValueError("R1 must upload exactly one receipt artifact")
    probe_witnesses(document, WITNESSES)
    install = document["jobs"].get("clean-install", {})
    if job.get("outputs", {}).get("artifact-id") != "${{ steps.upload.outputs.artifact-id }}" or step_named(document, "Upload R1 receipt").get("id") != "upload":
        raise ValueError("R1 immutable artifact output binding missing")
    for key, value in {"CANDIDATE_SHA": "${{ inputs.candidate_sha }}", "WORKFLOW_SHA": "${{ github.sha }}", "ARTIFACT_ID": "${{ needs.verify.outputs.artifact-id }}"}.items():
        if install.get("env", {}).get(key) != value:
            raise ValueError(f"R3 identity binding missing: {key}")
    if install.get("needs") != "verify" or install.get("runs-on") != "ubuntu-24.04" or "if" in install:
        raise ValueError("R3 requires successful R1 on fresh Ubuntu runner")
    download, smoke, upload = install.get("steps", [None] * 3)
    if download.get("uses") != DOWNLOAD or download.get("with", {}).get("artifact-ids") != "${{ needs.verify.outputs.artifact-id }}" or upload.get("uses") != UPLOAD or "uses" in smoke or upload.get("with", {}).get("path") != "r3-receipt/" or upload.get("with", {}).get("if-no-files-found") != "error":
        raise ValueError("R3 requires immutable R1 download and full r3-receipt/ upload with if-no-files-found: error")
    probe_install(document)


class R1LinuxRcContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.safe_load(WORKFLOW.read_text())

    def test_clean_workflow_meets_r1_contract(self):
        validate(self.document)

    def test_all_required_steps_reject_skip_and_tolerance(self):
        for job_name, job in self.document["jobs"].items():
            for index, step in enumerate(job["steps"]):
                for key, value in (("if", False), ("if", True), ("continue-on-error", False), ("continue-on-error", True)):
                    candidate = copy.deepcopy(self.document)
                    candidate["jobs"][job_name]["steps"][index][key] = value
                    with self.subTest(job=job_name, step=step["name"], key=key, value=value), self.assertRaisesRegex(ValueError, "required steps"): validate(candidate)

    def test_linux_recipe_executes_locked_cli_build_and_valid_artifact(self):
        # Reuse exact --locked --release --bin lightr argv and artifact conformance.
        fixture = packaged_s5.PackagedS5Tests("test_linux_recipe_has_no_vz_or_codesign")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.test_linux_recipe_has_no_vz_or_codesign()

    def test_candidate_missing_mismatch_and_artifact_controls_reject(self):
        for mutate in (
            lambda doc: doc[True]["workflow_dispatch"].pop("inputs"),
            lambda doc: doc["jobs"]["verify"]["steps"][0]["with"].pop("ref"),
            lambda doc: doc["jobs"]["verify"]["steps"][1].update({"run": "true"}),
            lambda doc: doc["jobs"]["verify"]["steps"][5].update({"run": "true"}),
        ):
            candidate = copy.deepcopy(self.document)
            mutate(candidate)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                validate(candidate)

    def test_identity_and_checksum_command_substitution_rejects(self):
        for step_name, line in (
            ("Verify immutable candidate identity", 'git cat-file -e "${CANDIDATE_SHA}^{commit}"'),
            ("Verify immutable candidate identity", 'test "$(git rev-parse HEAD)" = "$CANDIDATE_SHA"'),
            ("Verify artifact and checksum", 'test "$(wc -l < "$CHECKSUM")" -eq 1'),
            ("Verify artifact and checksum", "grep -Eq '^[0-9a-f]{64}  [^[:space:]]+$' \"$CHECKSUM\""),
            ("Verify artifact and checksum", 'test "$(awk \'{print $2}\' "$CHECKSUM")" = "$ARTIFACT_NAME"'),
            ("Verify artifact and checksum", '(cd "$(dirname "$CHECKSUM")" && sha256sum -c "$(basename "$CHECKSUM")")'),
        ):
            candidate = copy.deepcopy(self.document)
            step = step_named(candidate, step_name)
            step["run"] = step["run"].replace(line, "echo " + line)
            with self.subTest(step=step_name, line=line), self.assertRaises(ValueError):
                validate(candidate)

    def test_each_witness_removal_rejects(self):
        for witness in WITNESSES:
            candidate = copy.deepcopy(self.document)
            step = step_named(candidate, "Run required OCI witnesses")
            step["run"] = step["run"].replace(witness, "removed_witness")
            with self.subTest(witness=witness), self.assertRaises(ValueError):
                validate(candidate)

    def test_witness_loop_and_command_comment_substitution_reject(self):
        for line in (
            'for witness in "${WITNESSES[@]}"; do',
            'cargo +1.96.0 test --locked -p "$package" --lib -- "$witness" --exact |& tee "r1-receipt/${witness##*::}.log"',
        ):
            candidate = copy.deepcopy(self.document)
            step = step_named(candidate, "Run required OCI witnesses")
            step["run"] = step["run"].replace(line, "# " + line)
            with self.subTest(line=line), self.assertRaises(ValueError):
                validate(candidate)

    def test_unreachable_identity_and_missing_witness_assertion_reject(self):
        candidate = copy.deepcopy(self.document)
        identity = step_named(candidate, "Verify immutable candidate identity")
        identity["run"] = identity["run"].replace(
            'git cat-file -e "${CANDIDATE_SHA}^{commit}"',
            'if false; then git cat-file -e "${CANDIDATE_SHA}^{commit}"; fi',
        )
        with self.assertRaises(ValueError):
            validate(candidate)

        candidate = copy.deepcopy(self.document)
        witnesses = step_named(candidate, "Run required OCI witnesses")
        witnesses["run"] = "\n".join(
            line for line in witnesses["run"].splitlines() if "grep -Eq '^test result" not in line
        )
        with self.assertRaises(ValueError):
            validate(candidate)

    def test_full_oci_suite_removal_rejects(self):
        candidate = copy.deepcopy(self.document)
        step = step_named(candidate, "Run required OCI witnesses")
        step["run"] = step["run"].replace(
            "cargo +1.96.0 test --locked -p lightr-oci --lib |& tee r1-receipt/oci-full.log\n",
            "",
        )
        with self.assertRaises(ValueError):
            validate(candidate)

    def test_publish_mutations_reject(self):
        for forbidden in FORBIDDEN:
            candidate = copy.deepcopy(self.document)
            step_named(candidate, "Verify immutable candidate identity")["run"] += "\n" + forbidden
            with self.subTest(forbidden=forbidden), self.assertRaises(ValueError):
                validate(candidate)

    def test_unknown_action_rejects(self):
        candidate = copy.deepcopy(self.document)
        step_named(candidate, "Upload R1 receipt")["uses"] = "softprops/action-gh-release@v2"
        with self.assertRaises(ValueError):
            validate(candidate)

    def test_action_pin_relocation_rejects(self):
        candidate = copy.deepcopy(self.document)
        toolchain = step_named(candidate, "Install pinned Rust")
        toolchain["uses"] = CHECKOUT
        step_named(candidate, "Verify immutable candidate identity")["uses"] = TOOLCHAIN
        with self.assertRaises(ValueError):
            validate(candidate)

    def test_r1_r3_binding_skip_network_and_publication_mutations_reject(self):
        for key in ("needs", "env", "permissions"):
            candidate = copy.deepcopy(self.document)
            candidate["jobs"]["clean-install"].pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError): validate(candidate)
        for scope, key in ((scope, key) for scope in ("step", "verify", "clean-install") for key in ("if", "continue-on-error")):
            candidate = copy.deepcopy(self.document)
            (candidate["jobs"]["clean-install"]["steps"][1] if scope == "step" else candidate["jobs"][scope])[key] = False if scope != "step" and key == "if" else True
            with self.subTest(scope=scope, key=key), self.assertRaises(ValueError): validate(candidate)
        candidate = copy.deepcopy(self.document)
        step = step_named(candidate, "Run required OCI witnesses")
        step["run"] = step["run"].replace('command cargo "$@"', 'unset LIGHTR_NET_TESTS\ncommand cargo "$@"')
        with self.assertRaises(ValueError): validate(candidate)
        for scope, patch in ((None, {"permissions": {"contents": "write"}}),
                             ("verify", {"permissions": {"contents": "write"}}),
                             ("clean-install", {"permissions": "write-all"}),
                             ("jobs", {"publish": {"permissions": {"contents": "write"}, "steps": [{"run": "gh release create forbidden"}]}}),
                             ("upload", {"with": {"if-no-files-found": "error"}}),
                             ("upload", {"with": {"path": "r3-receipt/last-output", "if-no-files-found": "error"}}),
                             ("upload", {"with": {"path": "r3-receipt/"}}),
                             ("upload", {"with": {"path": "r3-receipt/", "if-no-files-found": "warn"}}),
                             ("clean-install", {"env": {"PUBLISH": "gh release create forbidden"}})):
            candidate = copy.deepcopy(self.document)
            target = candidate if scope is None else candidate["jobs"] if scope == "jobs" else candidate["jobs"]["clean-install"]["steps"][-1] if scope == "upload" else candidate["jobs"][scope]
            target.update(patch)
            with self.subTest(scope=scope, patch=patch), self.assertRaises(ValueError): validate(candidate)


if __name__ == "__main__":
    unittest.main()
