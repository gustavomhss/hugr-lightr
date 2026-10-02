"""Closed YAML wiring contract; no import/execution of the separately landed uploader.

Pins dispatch/auth/CLI/evidence wiring, not helper behavior or live upload outcomes.
"""
import copy
import json
from pathlib import Path
import re
import shlex
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/publish-crates.yml"
EXPR = lambda name: "${{ " + name + " }}"
ENV = {"CANDIDATE_SHA": EXPR("inputs.candidate_sha"), "RELEASE_TAG": EXPR("inputs.release_tag"), "VERIFIER_SHA": EXPR("github.sha")}
PUBLISH_ENV = dict(ENV, UPLOAD_AUTHORIZATION=EXPR("inputs.confirmation"), BOOTSTRAP_TOKEN=EXPR("secrets.CARGO_BOOTSTRAP_TOKEN"))
CHECKOUT = {"uses": "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            "with": {"ref": EXPR("github.sha"), "fetch-depth": 0, "persist-credentials": False}}
AUTH = {"name": "Exchange OIDC for temporary token", "id": "auth", "uses": "rust-lang/crates-io-auth-action@c6f97d42243bad5fab37ca0427f495c86d5b1a18"}
def artifact(name, path):
    return {"uses": "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02", "if": EXPR("always()"),
            "with": {"name": name, "path": path, "if-no-files-found": "error", "retention-days": 30}}

CONTRACT = {
    "name": "Trusted Publishing auth-only readiness",
    "on": {"workflow_dispatch": {"inputs": {
        "mode": {"description": "Auth-only proof or owner-authorized eleven-crate publication", "required": True,
                 "type": "choice", "default": "auth-only", "options": ["auth-only", "publish"]},
        "candidate_sha": {"description": "Frozen lowercase 40-character product SHA", "required": True, "type": "string"},
        "release_tag": {"description": "Existing annotated product tag", "required": True, "type": "string"},
        "confirmation": {"description": "publish-0.1.1 required for publish; validated before token mint", "required": False, "type": "string", "default": ""}}}},
    "permissions": {"contents": "read", "id-token": "write"},
    "jobs": {
        "readiness": {"if": EXPR("inputs.mode == 'auth-only'"), "runs-on": "ubuntu-latest", "environment": "G-PUBLISH", "timeout-minutes": 10, "steps": [
            CHECKOUT,
            {"name": "Verify frozen source and verifier", "env": ENV, "run": "python3 scripts/ci/trusted_publishing_readiness.py preflight"},
            AUTH,
            {"name": "Revoke token and record auth-only proof", "env": dict(ENV, TP_TOKEN=EXPR("steps.auth.outputs.token")),
             "run": "python3 scripts/ci/trusted_publishing_readiness.py revoke"},
            artifact("trusted-publishing-readiness", "trusted-publishing-readiness/")]},
        "publish": {"if": EXPR("inputs.mode == 'publish' && github.run_attempt == 1"), "runs-on": "ubuntu-latest", "environment": "G-PUBLISH", "timeout-minutes": 25,
                    "concurrency": {"group": "publish0.1.1", "cancel-in-progress": False}, "steps": [
            CHECKOUT,
            {"name": "Install pinned Rust before token mint", "uses": "dtolnay/rust-toolchain@ebb3d1676050bfd0971c36c1e215b5751473994d", "with": {"toolchain": "1.96.0"}},
            {"name": "Verify authorized frozen batch before token mint", "env": PUBLISH_ENV, "run": "python3 scripts/ci/crate_publisher.py preflight"},
            AUTH,
            {"name": "Publish frozen batch; halt on first failure", "env": dict(PUBLISH_ENV, TP_TOKEN=EXPR("steps.auth.outputs.token")), "run": "python3 scripts/ci/crate_publisher.py publish"},
            artifact("crate-publication", "crate-publication/*.json\ncrate-publication/*.log\n")]}}}

class UniqueLoader(yaml.SafeLoader):
    """Reject duplicates before YAML overwrites them; keep `on` a string."""
    yaml_implicit_resolvers = {k: [(tag, regex) for tag, regex in values if tag != "tag:yaml.org,2002:bool"]
                               for k, values in yaml.SafeLoader.yaml_implicit_resolvers.items()}
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in result:
                raise ValueError(f"duplicate workflow key: {key}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result
UniqueLoader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$", re.I), list("tTfF"))

def load_workflow(text):
    return yaml.load(text, Loader=UniqueLoader)

def validate_workflow(document):
    def normalized(value):
        if isinstance(value, list):
            return [normalized(v) for v in value]
        if isinstance(value, dict):
            result = {k: normalized(v) for k, v in value.items()}
            if "run" in result:
                command = result["run"]
                if not isinstance(command, str) or "\n" in command.strip() or "\r" in command:
                    raise ValueError("single helper CLI command required")
                result["run"] = shlex.split(command)
            return result
        return value
    try:
        actual = json.dumps(normalized(document), sort_keys=True)
        expected = json.dumps(normalized(CONTRACT), sort_keys=True)
    except (TypeError, AttributeError) as error:
        raise ValueError("malformed workflow contract") from error
    if actual != expected:
        raise ValueError("auth-only/publish closed workflow contract mismatch")

class WorkflowTests(unittest.TestCase):
    def test_real_workflow_and_default_auth_only(self):
        document = load_workflow(WORKFLOW.read_text())
        validate_workflow(document)
        inputs = document["on"]["workflow_dispatch"]["inputs"]
        self.assertEqual(inputs["mode"]["default"], "auth-only")
        self.assertEqual(inputs["confirmation"]["default"], "")
        self.assertEqual(document["jobs"]["readiness"]["if"], EXPR("inputs.mode == 'auth-only'"))
        self.assertEqual(document["jobs"]["publish"]["if"], EXPR("inputs.mode == 'publish' && github.run_attempt == 1"))

    def test_comments_key_order_and_cli_whitespace_tolerated(self):
        document = load_workflow("# harmless YAML comment\n" + WORKFLOW.read_text())
        document = dict(reversed(list(document.items())))
        for job in document["jobs"].values():
            for step in job["steps"]:
                if "run" in step:
                    step["run"] = "  " + step["run"].replace(" ", "\t  ") + "\n"
        validate_workflow(document)

    def test_duplicate_keys_and_empty_yaml_fail(self):
        text = WORKFLOW.read_text()
        for changed in (text + "\njobs: {}\n", text.replace("    timeout-minutes: 25", "    timeout-minutes: 25\n    timeout-minutes: 25"),
                        text.replace("          TP_TOKEN:", "          BOOTSTRAP_TOKEN: counterfeit\n          BOOTSTRAP_TOKEN: counterfeit\n          TP_TOKEN:")):
            with self.subTest(changed=changed[-80:]), self.assertRaisesRegex(ValueError, "duplicate workflow key"):
                load_workflow(changed)
        for text in ("", "# empty", "jobs: {}", "jobs:\n  publish:"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_workflow(load_workflow(text))

    def test_adversarial_wiring_mutations(self):
        # Mutate parsed real YAML: no helper imports, credentials, Cargo, or network.
        original = load_workflow(WORKFLOW.read_text())
        cases = [(("jobs",), {}), (("jobs", "publish"), {}), (("jobs", "publish", "strategy"), {"matrix": {"crate": ["counterfeit"]}}),
                 (("on", "workflow_dispatch", "inputs", "mode", "default"), "publish"),
                 (("on", "workflow_dispatch", "inputs", "confirmation", "default"), "publish-0.1.1"),
                 (("jobs", "publish", "if"), EXPR("inputs.mode == 'publish'")),
                 (("jobs", "readiness", "if"), EXPR("always()")), (("jobs", "publish", "timeout-minutes"), 30),
                 (("jobs", "publish", "concurrency", "cancel-in-progress"), True),
                 (("jobs", "publish", "env"), {"BOOTSTRAP_TOKEN": EXPR("secrets.CARGO_BOOTSTRAP_TOKEN")})]
        for index in (2, 4):
            prefix = ("jobs", "publish", "steps", index)
            cases.extend([(prefix + ("env", "UPLOAD_AUTHORIZATION"), "publish-0.1.1"),
                          (prefix + ("env", "BOOTSTRAP_TOKEN"), EXPR("secrets.OTHER_TOKEN")),
                          (prefix + ("continue-on-error",), True), (prefix + ("if",), EXPR("always()"))])
            for suffix in (" || true", " > crate-publication/token.log", " --dry-run", " --crate counterfeit", "\ntrue", "; true"):
                cases.append((prefix + ("run",), original["jobs"]["publish"]["steps"][index]["run"] + suffix))
        for index in (0, 1, 2, 3, 5):
            cases.append((("jobs", "publish", "steps", index, "env",), {"TP_TOKEN": EXPR("steps.auth.outputs.token")}))
        cases.extend([(("jobs", "publish", "steps", 4, "env", "TP_TOKEN"), EXPR("secrets.CARGO_BOOTSTRAP_TOKEN")),
                      (("jobs", "publish", "steps", 5, "with", "path"), "crate-publication/"),
                      (("jobs", "publish", "steps", 3, "uses"), "rust-lang/crates-io-auth-action@main"),
                      (("jobs", "publish", "steps", 0, "with", "ref"), EXPR("inputs.candidate_sha"))])
        for path, value in cases:
            changed = copy.deepcopy(original)
            target = changed
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                validate_workflow(changed)
        for indexes in ([0, 2, 1, 3, 4, 5], [0, 1, 3, 2, 4, 5], [0, 1, 2, 3, 4, 4, 5]):
            changed = copy.deepcopy(original)
            steps = changed["jobs"]["publish"]["steps"]
            changed["jobs"]["publish"]["steps"] = [steps[i] for i in indexes]
            with self.subTest(order=indexes), self.assertRaises(ValueError):
                validate_workflow(changed)

if __name__ == "__main__":
    unittest.main()
