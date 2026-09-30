"""Fail-closed contract and mutation teeth for R1 Linux RC workflow."""
import copy
import textwrap
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/r1-linux-x86_64-rc.yml"
RELEASE_SCRIPT = ROOT / "packaging/release.sh"
WITNESSES = {
    "oci::tests::integrity_tests::test_write_through_symlink_component_rejects_import_without_ref",
    "store::image_ref::tests::concurrent_tuple_reads_never_observe_mixed_publication",
    "oci::tests::import_tests::test_import_layout_two_layers_whiteout_and_hydrate",
    "oci::load::load_tests::save_load_roundtrip_lossless",
    "oci::tests::pull_tests::test_pull_alpine_network_gated",
    "oci::tests::import_tests::test_path_escape_rejects_import_without_ref",
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
    "Run required OCI witnesses": """
        set -euo pipefail
        mkdir -p r1-receipt
        cargo +1.96.0 test --locked -p lightr-oci --lib |& tee r1-receipt/oci-full.log
        declare -a WITNESSES=(
          'oci::tests::integrity_tests::test_write_through_symlink_component_rejects_import_without_ref'
          'store::image_ref::tests::concurrent_tuple_reads_never_observe_mixed_publication'
          'oci::tests::import_tests::test_import_layout_two_layers_whiteout_and_hydrate'
          'oci::load::load_tests::save_load_roundtrip_lossless'
          'oci::tests::pull_tests::test_pull_alpine_network_gated'
          'oci::tests::import_tests::test_path_escape_rejects_import_without_ref'
        )
        for witness in "${WITNESSES[@]}"; do
          package=lightr-oci
          if [[ "$witness" = store::* ]]; then package=lightr-store; fi
          cargo +1.96.0 test --locked -p "$package" --lib -- "$witness" --exact |& tee "r1-receipt/${witness##*::}.log"
          grep -Eq '^test result: ok\\. 1 passed; 0 failed; 0 ignored; [0-9]+ measured; [0-9]+ filtered out' "r1-receipt/${witness##*::}.log"
        done
    """,
    "Verify artifact and checksum": """
        set -euo pipefail
        VERSION="$(grep -A 10 '^\\[workspace\\.package\\]' Cargo.toml | grep '^version' | head -1 | sed 's/.*= *"\\(.*\\)"/\\1/')"
        ARTIFACT="packaging/dist/lightr-${VERSION}-linux-x86_64.tar.gz"
        CHECKSUM="${ARTIFACT}.sha256"
        ARTIFACT_NAME="$(basename "$ARTIFACT")"
        test -s "$ARTIFACT"
        test -s "$CHECKSUM"
        test "$(wc -l < "$CHECKSUM")" -eq 1
        grep -Eq '^[0-9a-f]{64}  [^[:space:]]+$' "$CHECKSUM"
        test "$(awk '{print $2}' "$CHECKSUM")" = "$ARTIFACT_NAME"
        sha256sum -c "$CHECKSUM"
        tar -tzf "$ARTIFACT" | grep -Fxq lightr
        SHA256="$(sha256sum "$ARTIFACT" | awk '{print $1}')"
        BINARY_SHA256="$(tar -xOf "$ARTIFACT" lightr | sha256sum | awk '{print $1}')"
        jq -n \\
          --arg candidate_sha "$CANDIDATE_SHA" \\
          --arg workflow_sha "$WORKFLOW_SHA" \\
          --arg artifact "$ARTIFACT" \\
          --arg checksum "$CHECKSUM" \\
          --arg sha256 "$SHA256" \\
          --arg binary_sha256 "$BINARY_SHA256" \\
          --arg environment "$(uname -srm)" \\
          --arg rustc "$(rustc +1.96.0 --version)" \\
          --argjson commands '["cargo +1.96.0 test --locked -p lightr-oci --lib","cargo +1.96.0 test --locked -p <witness-package> --lib -- <witness> --exact","bash packaging/release.sh","sha256sum -c <checksum>"]' \\
          --argjson witnesses '["oci-confinement","oci-publication","oci-import","oci-load","oci-pull","oci-no-ref-negative"]' \\
          --arg negative_control "test_path_escape_rejects_import_without_ref: passed; see test log" \\
          '{candidate_sha: $candidate_sha, workflow_sha: $workflow_sha, artifact: $artifact, checksum: $checksum, sha256: $sha256, binary_sha256: $binary_sha256, environment: $environment, rustc: $rustc, commands: $commands, witnesses: $witnesses, negative_control: $negative_control}' \\
          > r1-receipt/R1-linux-x86_64.json
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
    return "\n".join(str(step.get(key, "")) for step in steps(document) for key in ("uses", "run"))


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
        ("Verify artifact and checksum", 'sha256sum -c "$CHECKSUM"'),
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


class R1LinuxRcContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.safe_load(WORKFLOW.read_text())

    def test_clean_workflow_meets_r1_contract(self):
        validate(self.document)
        self.assertIn("cargo build --locked --release -p lightr-cli", RELEASE_SCRIPT.read_text())

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
            ("Verify artifact and checksum", 'sha256sum -c "$CHECKSUM"'),
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


if __name__ == "__main__":
    unittest.main()
