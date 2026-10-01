"""Closed YAML wiring contract; helper existence/runtime and owner settings are integration checks."""
import copy
from pathlib import Path
import unittest

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/public-release-install.yml"
EXPECTED = {
    "name": "Public release fresh-install proof",
    "on": {"workflow_dispatch": {"inputs": {
        name: {"description": description, "required": "true", "type": "string"}
        for name, description in (
            ("producer_run_id", "Immutable public release producer run ID"),
            ("release_id", "Immutable draft release ID"),
            ("candidate_sha", "Immutable lowercase 40-character product commit"),
            ("release_tag", "Existing release tag bound to the product commit"))}}},
    "permissions": {"contents": "read", "actions": "read"},
    "jobs": {"clean-install": {
        "environment": "G-PUBLISH", "runs-on": "${{ matrix.runner }}", "timeout-minutes": "15",
        "strategy": {"fail-fast": "false", "matrix": {"include": [
            {"target": "linux-x86_64", "runner": "ubuntu-latest"},
            {"target": "darwin-arm64", "runner": "macos-14"}]}},
        "steps": [
            {"uses": "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
             "with": {"ref": "${{ github.sha }}", "persist-credentials": "false"}},
            {"name": "Verify read-only transport and fresh native install", "shell": "bash",
             "env": {"GH_TOKEN": "${{ github.token }}",
                     "PUBLIC_RELEASE_RUN_ID": "${{ inputs.producer_run_id }}",
                     "PUBLIC_RELEASE_ID": "${{ inputs.release_id }}",
                     "CANDIDATE_SHA": "${{ inputs.candidate_sha }}",
                     "RELEASE_TAG": "${{ inputs.release_tag }}",
                     "PUBLIC_RELEASE_TARGET": "${{ matrix.target }}",
                     "VERIFIER_SHA": "${{ github.sha }}"},
             "run": "python3 scripts/ci/public_release_install.py"},
            {"uses": "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
             "if": "${{ always() }}",
             "with": {"name": "public-release-install-${{ matrix.target }}-${{ inputs.producer_run_id }}",
                      "path": "public-release-install/", "if-no-files-found": "error",
                      "retention-days": "30"}}]}}
}


class ClosedLoader(yaml.BaseLoader):
    # BaseLoader keeps `on` a string, avoiding SafeLoader's YAML 1.1 boolean key.
    def construct_mapping(self, node, deep=False):
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in mapping:
                raise ValueError(f"duplicate/non-string YAML key: {key!r}")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def contract(actual, expected=EXPECTED, path="workflow"):
    if type(actual) is not type(expected):
        raise ValueError(f"{path}: wrong type")
    if isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise ValueError(f"{path}: closed keys mismatch")
        for key in expected:
            contract(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError(f"{path}: missing/extra entries")
        for index, value in enumerate(expected):
            contract(actual[index], value, f"{path}[{index}]")
    elif actual != expected:
        raise ValueError(f"{path}: exact value mismatch")


def paths(value, path=()):
    yield path, value
    if isinstance(value, (dict, list)):
        for key in value if isinstance(value, dict) else range(len(value)):
            yield from paths(value[key], path + (key,))


class Tests(unittest.TestCase):
    def test_actual_workflow_and_every_field_mutation(self):
        text = WORKFLOW.read_text()
        doc = yaml.load(text, Loader=ClosedLoader)
        contract(doc)
        contract(yaml.load("# harmless formatting control\n" + text, Loader=ClosedLoader))
        for path, value in paths(doc):
            replacements = [None, {}, [], ""]
            replacements += [{**value, "unexpected": "true"}] if isinstance(value, dict) else (
                [value + [{}]] if isinstance(value, list) else [value + "-changed"])
            for replacement in replacements:
                with self.subTest(path=path, replacement=replacement):
                    changed = copy.deepcopy(doc)
                    parent = changed
                    for key in path[:-1]:
                        parent = parent[key]
                    if path:
                        parent[path[-1]] = replacement
                    else:
                        changed = replacement
                    with self.assertRaises(ValueError):
                        contract(yaml.load(yaml.safe_dump(changed), Loader=ClosedLoader))
            if path:
                with self.subTest(path=path, mutation="removed"):
                    changed = copy.deepcopy(doc)
                    parent = changed
                    for key in path[:-1]:
                        parent = parent[key]
                    del parent[path[-1]]
                    with self.assertRaises(ValueError):
                        contract(changed)

    def test_policy_bypass_mutations(self):
        doc = yaml.load(WORKFLOW.read_text(), Loader=ClosedLoader)
        for path, value in paths(doc):
            if isinstance(value, dict):
                for key, replacement in (("if", "false"), ("continue-on-error", "true"),
                                         ("permissions", {"contents": "write"}),
                                         ("repository", "evil/repo"), ("env", {"GH_TOKEN": "${{ secrets.PAT }}"})):
                    with self.subTest(path=path, bypass=key):
                        changed = copy.deepcopy(doc)
                        parent = changed
                        for part in path:
                            parent = parent[part]
                        parent[key] = replacement
                        with self.assertRaises(ValueError):
                            contract(changed)

    def test_duplicate_keys_rejected(self):
        with self.assertRaises(ValueError):
            yaml.load(WORKFLOW.read_text() + "\npermissions: {}\n", Loader=ClosedLoader)

    def test_fail_fast_removal_and_value_flip_rejected(self):
        doc = yaml.load(WORKFLOW.read_text(), Loader=ClosedLoader)
        contract(doc)
        for mutation in ("removed", "true"):
            with self.subTest(fail_fast=mutation):
                changed = copy.deepcopy(doc)
                strategy = changed["jobs"]["clean-install"]["strategy"]
                if mutation == "removed":
                    del strategy["fail-fast"]
                else:
                    strategy["fail-fast"] = mutation
                with self.assertRaises(ValueError):
                    contract(changed)


if __name__ == "__main__":
    unittest.main()
