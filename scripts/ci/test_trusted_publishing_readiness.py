"""Tagged Git fixtures, synthetic DELETE transport, and a closed workflow contract."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request
import yaml
import trusted_publishing_readiness as t
from test_crate_publisher_workflow import CONTRACT, load_workflow, validate_workflow

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "SYNTH-TP-do-not-log"

class Tests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(t.SOURCE, "47f02795d0884956c4755254b5f6fc377a5938b5")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(os.chdir, Path.cwd())
        os.chdir(self.tmp.name)
        self.git("init", "-q")
        Path("Cargo.toml").write_text('[workspace.package]\nversion = "0.1.1"\n')
        self.git("add", "Cargo.toml")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "source")
        self.source = self.git("rev-parse", "HEAD")
        self.tag("v0.1.1", self.source)
        Path("Cargo.toml").write_text('[workspace.package]\nversion = "9.9.9"\n')
        self.git("add", "Cargo.toml")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "verifier")
        self.verifier = self.git("rev-parse", "HEAD")
        self.env = dict(CANDIDATE_SHA=self.source, RELEASE_TAG="v0.1.1", VERIFIER_SHA=self.verifier,
                        GITHUB_SHA=self.verifier, GITHUB_REPOSITORY="gusmhs/hugr-lightr", GITHUB_EVENT_NAME="workflow_dispatch")
        pin = patch.object(t, "SOURCE", self.source)
        pin.start()
        self.addCleanup(pin.stop)

    def git(self, *args):
        return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()

    def tag(self, tag, source):
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "tag.gpgsign=false", "tag", "-a", tag, source, "-m", "fixture")

    def call(self, command, env=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = t.main([command], self.env if env is None else env)
        logs = out.getvalue() + err.getvalue()
        self.assertNotIn(TOKEN, logs)
        for file in t.OUTPUT.glob("*"):
            self.assertNotIn(TOKEN, file.read_text())
        return status, logs

    def transport(self, status=204, error=None):
        opener = MagicMock()
        opener.open.side_effect = error
        opener.open.return_value.__enter__.return_value.status = status
        return patch.object(t.urllib.request, "build_opener", return_value=opener), opener

    def test_source_verifier_and_delete_proof(self):
        self.assertNotEqual(self.source, self.verifier)
        self.assertEqual(self.call("preflight")[0], 0)
        self.assertEqual(json.loads((t.OUTPUT / "preflight.json").read_text())["source"], self.source)
        transport, opener = self.transport()
        with transport, patch.dict(os.environ, TP_TOKEN=TOKEN), patch.object(t.subprocess, "run", wraps=t.subprocess.run) as run:
            self.assertEqual(self.call("revoke", dict(self.env, TP_TOKEN=TOKEN))[0], 0)
            for call in run.call_args_list:
                self.assertEqual(set(call.kwargs["env"]), {"PATH", "LC_ALL", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL"})
        request = opener.open.call_args.args[0]
        self.assertEqual((request.full_url, request.get_method(), request.data), (t.ENDPOINT, "DELETE", None))
        self.assertEqual(request.headers, {"Authorization": "Bearer " + TOKEN})
        receipt = json.loads((t.OUTPUT / "receipt.json").read_text())
        self.assertEqual((receipt["minted"], receipt["revocation_status"], receipt["publication"]), (True, 204, "NOT EXECUTED"))
        self.assertEqual((receipt["source"], receipt["verifier"]), (self.source, self.verifier))
        self.assertEqual(set(receipt["bootstrap_new_crates"]), {"hugr-lightr", "hugr-lightr-cri-backend"})
        self.assertIn("no exact token allowlist introspection", receipt["scope"])
        self.assertEqual(self.call("revoke", dict(self.env, TP_TOKEN=""))[0], 1)
        self.assertFalse((t.OUTPUT / "receipt.json").exists())

    def test_frozen_source_rejects_otherwise_valid_candidate(self):
        self.assertEqual(self.call("preflight")[0], 0)
        with patch.object(t, "SOURCE", self.verifier), patch.object(t.urllib.request, "build_opener") as auth:
            status, logs = self.call("preflight")
        self.assertEqual((status, logs), (1, "FAIL: frozen candidate mismatch\n"))
        self.assertFalse((t.OUTPUT / "preflight.json").exists())
        self.assertFalse((t.OUTPUT / "receipt.json").exists())
        auth.assert_not_called()

    def test_identity_guards(self):
        self.assertEqual(self.call("source")[0], 1)
        cases = {"CANDIDATE_SHA": [self.verifier, "A" * 40, "abc"], "RELEASE_TAG": ["v9.9.9", "--help"],
                 "GITHUB_EVENT_NAME": ["push"], "GITHUB_REPOSITORY": ["other/repo", "gmhelmold/hugr-lightr"],
                 "VERIFIER_SHA": [self.source, "A" * 40], "GITHUB_SHA": [self.source], "TP_TOKEN": [TOKEN]}
        for key, values in cases.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.assertEqual(self.call("preflight", dict(self.env, **{key: value}))[0], 1)
                    self.assertFalse((t.OUTPUT / "preflight.json").exists())
        self.tag("v0.1.2", self.source)
        self.assertIn("version mismatch", self.call("preflight", dict(self.env, RELEASE_TAG="v0.1.2"))[1])
        self.git("tag", "-d", "v0.1.1")
        self.tag("v0.1.1", self.verifier)
        self.assertIn("tag candidate mismatch", self.call("preflight")[1])
        self.git("tag", "-d", "v0.1.1")
        self.git("-c", "tag.gpgsign=false", "tag", "v0.1.1", self.source)
        self.assertIn("annotated tag required", self.call("preflight")[1])

    def test_migrated_repository_authority(self):
        self.assertEqual(t.REPO, "gusmhs/hugr-lightr")
        self.assertEqual(self.call("preflight")[0], 0)
        self.assertEqual(json.loads((t.OUTPUT / "preflight.json").read_text())["repository"], "gusmhs/hugr-lightr")
        with patch.object(t.urllib.request, "build_opener") as auth:
            status, logs = self.call("preflight", dict(self.env, GITHUB_REPOSITORY="gmhelmold/hugr-lightr"))
        self.assertEqual((status, logs), (1, "FAIL: repository mismatch\n"))
        self.assertFalse((t.OUTPUT / "preflight.json").exists())
        self.assertFalse((t.OUTPUT / "receipt.json").exists())
        auth.assert_not_called()

    def test_failed_proofs_never_write_receipt(self):
        minted = dict(self.env, TP_TOKEN=TOKEN)
        transport, opener = self.transport()
        with transport:
            self.assertEqual(self.call("revoke", minted)[0], 1)
            self.assertEqual(self.call("preflight")[0], 0)
            for token in ("", " "):
                self.assertEqual(self.call("revoke", dict(self.env, TP_TOKEN=token))[0], 1)
            (t.OUTPUT / "preflight.json").write_text("{}")
            self.assertEqual(self.call("revoke", minted)[0], 1)
            opener.open.assert_not_called()
        for status, error in [(200, None), (302, None), (500, None), (204, OSError(TOKEN)),
                              (204, urllib.error.HTTPError(t.ENDPOINT, 403, TOKEN, {"Authorization": TOKEN}, io.BytesIO(TOKEN.encode())))]:
            with self.subTest(status=status, error=type(error).__name__):
                self.assertEqual(self.call("preflight")[0], 0)
                transport, _ = self.transport(status, error)
                with transport:
                    self.assertEqual(self.call("revoke", minted)[0], 1)
                self.assertFalse((t.OUTPUT / "receipt.json").exists())
                if isinstance(error, urllib.error.HTTPError):
                    self.assertTrue(error.closed)

    def test_real_redirect_handler_rejects_forwarding(self):
        self.assertEqual(self.call("preflight")[0], 0)
        for status in (301, 302, 303, 307, 308):
            response = urllib.response.addinfourl(io.BytesIO(), {"location": "https://other.invalid/"}, t.ENDPOINT, status)
            response.msg = TOKEN
            with patch.object(urllib.request.HTTPSHandler, "https_open", return_value=response) as send:
                self.assertIn("redirect forbidden", self.call("revoke", dict(self.env, TP_TOKEN=TOKEN))[1])
                self.assertEqual(send.call_count, 1)
                self.assertFalse((t.OUTPUT / "receipt.json").exists())

    def test_workflow_closed_contract_and_all_removals(self):
        document = load_workflow((ROOT / ".github/workflows/publish-crates.yml").read_text())
        validate_workflow(document)
        self.assertEqual(document["on"]["workflow_dispatch"]["inputs"]["mode"]["default"], "auth-only")
        self.assertEqual(set(document["jobs"]), {"readiness", "publish"})
        def mutations(value):
            if isinstance(value, (dict, list)):
                for key in list(value) if isinstance(value, dict) else range(len(value)):
                    removed = copy.deepcopy(value)
                    del removed[key]
                    yield removed
                    for child in mutations(value[key]):
                        changed = copy.deepcopy(value)
                        changed[key] = child
                        yield changed
            yield None
            yield "wrong-value"
        for document in mutations(CONTRACT):
            with self.assertRaises(ValueError):
                validate_workflow(document)
        for key, value in (("on", {"push": {}}), ("env", {"TP_TOKEN": TOKEN}), ("permissions", {"contents": "write"})):
            with self.assertRaises(ValueError):
                validate_workflow(dict(CONTRACT, **{key: value}))
        ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]["required-ci"]
        self.assertIn("python3 -m unittest discover -s scripts/ci -p 'test_*.py' -v", [s.get("run") for s in ci["steps"]])

if __name__ == "__main__":
    unittest.main()
