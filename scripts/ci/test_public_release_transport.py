"""Standalone transport controls: real subprocesses, synthetic credentials, no network."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback
import types
import unittest
from unittest.mock import patch
import public_release_transport as t

class Fixture:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="public transport ")
        self.root = Path(self.tmp.name)
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.env = patch.dict(os.environ, PATH=f"{self.tools}:{os.environ['PATH']}",
                              GH_TOKEN="SYNTH-gh-token", GITHUB_TOKEN="SYNTH-github-token", PRIVATE_SECRET="SYNTH-private-secret")
        self.env.start()
        self.e = t.PublicEvidence(self.root / "evidence")
        return self

    def tool(self, name, body):
        path = self.tools / name
        path.write_text(f"#!{sys.executable} -S\nimport os, sys\n{body}\n")
        path.chmod(0o755)

    def __exit__(self, *args):
        self.env.stop()
        self.tmp.cleanup()

class Tests(unittest.TestCase):
    def test_endpoint_media_and_binary_stdout(self):
        for endpoint, binary, media, body in (
            ("actions/artifacts/77/zip", True, "application/vnd.github+json", b"PK\x00\xff"),
            ("releases/assets/12", True, "application/octet-stream", b"\x1f\x8b\xff"),
            ("releases/99", False, "application/vnd.github+json", b'{"id":99,"draft":true}')):
            with self.subTest(endpoint=endpoint), Fixture() as f:
                f.tool("gh", f"assert sys.argv[1:] == ['api', '--hostname', 'github.com', '--method', 'GET', 'repos/gmhelmold/hugr-lightr/{endpoint}', '-H', 'Accept: {media}']\nassert os.environ['GH_TOKEN'] == 'SYNTH-gh-token'\nassert set(os.environ) <= {{'PATH', 'GH_TOKEN', 'GH_HOST', 'GH_CONFIG_DIR', 'LC_CTYPE', '__CF_USER_TEXT_ENCODING'}}\nassert os.listdir(os.environ['GH_CONFIG_DIR']) == []\nsys.stdout.buffer.write({body!r})")
                api = t.Api(f.e, os.environ["GH_TOKEN"])
                try:
                    actual = api.get(endpoint, binary)
                except ValueError as error:
                    self.fail(str(error))
                self.assertEqual(actual, body if binary else json.loads(body))
                self.assertEqual(f.e.commands[0]["exit_code"], 0)
                self.assertNotIn("SYNTH-gh-token", (f.e.path / "commands.json").read_text())

    def test_get_restriction_before_subprocess(self):
        with Fixture() as f:
            api = t.Api(f.e, os.environ["GH_TOKEN"])
            for endpoint in ("../other", "releases/tags/v0.1.1", "releases/0", "https://other/repo", "actions/runs/1?method=POST"):
                with self.subTest(endpoint=endpoint), patch.object(t.subprocess, "run", return_value=types.SimpleNamespace(returncode=0, stdout=b"{}")) as run:
                    with self.assertRaisesRegex(ValueError, "API endpoint forbidden"):
                        api.get(endpoint)
                    run.assert_not_called()

    def test_child_env_whitelist_and_token_absence(self):
        with Fixture() as f:
            code = "import os, json; print(json.dumps(dict(os.environ)))"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                text = f.e.run(sys.executable, "-S", "-c", code, env=dict(os.environ, HOME=str(f.e.home)))
            env = json.loads(text)
            self.assertLessEqual(set(env), {"PATH", "HOME", "LC_ALL", "TMPDIR", "__CF_USER_TEXT_ENCODING"})
            self.assertEqual(env["LC_ALL"], "C")
            for key in ("HOME", "TMPDIR"):
                self.assertTrue(Path(env[key]).is_relative_to(f.e.path))
            for secret in ("SYNTH-gh-token", "SYNTH-github-token", "SYNTH-private-secret"):
                self.assertNotIn(secret, stdout.getvalue())
            self.assertNotIn("PRIVATE_SECRET", text)

    def test_failure_redaction_before_all_output_writes(self):
        with Fixture() as f:
            code = "import sys; print('legit error SYNTH-gh-token SYNTH-github-token'); sys.stderr.write('SYNTH-gh-token\\n'); sys.exit(1)"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout), self.assertRaisesRegex(ValueError, "command failed") as error:
                f.e.run(sys.executable, "-S", "-c", code)
            captured = stdout.getvalue().encode() + str(error.exception).encode()
            captured += (f.e.path / "00.log").read_bytes() + (f.e.path / "commands.json").read_bytes()
            for secret in (b"SYNTH-gh-token", b"SYNTH-github-token"):
                self.assertNotIn(secret, captured)
            self.assertIn(b"legit error [REDACTED] [REDACTED]", captured)
            self.assertEqual(f.e.commands[0]["exit_code"], 1)
            self.assertIn("[REDACTED]", f.e.commands[0]["argv"][-1])

    def test_api_failures_preserve_only_response_hash(self):
        for code, body, error in ((1, b"private body", "GET failed"), (0, b"", "GET failed"), (0, b"private body", "JSON malformed")):
            with self.subTest(code=code, body=body), Fixture() as f:
                f.tool("gh", f"sys.stdout.buffer.write({body!r}); sys.stderr.write('SYNTH-gh-token'); sys.exit({code})")
                with self.assertRaisesRegex(ValueError, error):
                    t.Api(f.e, os.environ["GH_TOKEN"]).get("actions/runs/123")
                log = (f.e.path / "commands.json").read_text()
                self.assertNotIn("private body", log)
                self.assertNotIn("SYNTH-gh-token", log)
                self.assertIn(t.sha(body), log)
    def test_spawn_errors_are_redacted_without_chain(self):
        for missing_cwd in (False, True):
            with self.subTest(cwd=missing_cwd), Fixture() as f:
                path = "/nonexistent/SYNTH-gh-token"
                argv, cwd = ((sys.executable, "-S", "-c", "pass"), path) if missing_cwd else ((path,), None)
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout), self.assertRaisesRegex(ValueError, "command spawn failed") as error:
                    f.e.run(*argv, cwd=cwd)
                captured = stdout.getvalue() + "".join(traceback.format_exception(error.exception))
                captured += (f.e.path / "00.log").read_text() + (f.e.path / "commands.json").read_text()
                self.assertNotIn("SYNTH-gh-token", captured)
                self.assertIn("[REDACTED]", captured)
                self.assertIsNone(error.exception.__cause__)
                self.assertTrue(error.exception.__suppress_context__)
                self.assertIsNone(f.e.commands[0]["exit_code"])
    def test_endpoint_size_and_component_bounds(self):
        with Fixture() as f:
            f.tool("gh", "sys.stdout.write('{}')")
            api = t.Api(f.e, os.environ["GH_TOKEN"])
            for endpoint in ("releases/" + "9"*20, "git/ref/tags/v" + ".".join(["9"*10]*3)):
                self.assertEqual(api.get(endpoint), {})
            for endpoint in ("releases/"+"9"*21, "git/ref/tags/v"+"9"*11+".0.1", "releases/"+"9"*10000):
                with self.subTest(endpoint=endpoint[:40]), patch.object(t.subprocess, "run") as run:
                    with self.assertRaisesRegex(ValueError, "API endpoint forbidden"):
                        api.get(endpoint)
                    run.assert_not_called()

    def test_root_mutation_probes(self):
        source = Path(t.__file__).read_text()
        mutations = [
            ('body = body.replace(token.encode(), b"[REDACTED]")', 'body = body', "test_failure_redaction_before_all_output_writes", 1),
            ('endpoint.startswith("releases/assets/")', 'binary', "test_endpoint_media_and_binary_stdout", 1),
            ('require(re.fullmatch(allowed, endpoint), "API endpoint forbidden")', 'require(True, "mutant")', "test_get_restriction_before_subprocess", 5),
            ('child_env = dict(PATH=os.environ["PATH"], HOME=str(home), LC_ALL="C", TMPDIR=str(self.tmp))', 'child_env = dict(os.environ, HOME=str(home), LC_ALL="C", TMPDIR=str(self.tmp))', "test_child_env_whitelist_and_token_absence", 1),
            ('diagnostic = self.safe(f"command spawn failed: {list(argv)}: {error}")', 'diagnostic = f"command spawn failed: {list(argv)}: {error}"', "test_spawn_errors_are_redacted_without_chain", 2)]
        for before, after, test, failures in mutations:
            with self.subTest(check=test):
                self.assertEqual(source.count(before), 1)
                mutant = types.ModuleType("mutant")
                exec(compile(source.replace(before, after), "mutant", "exec"), mutant.__dict__)
                with patch(__name__ + ".t", mutant):
                    result = unittest.TestResult()
                    Tests(test).run(result)
                self.assertEqual(result.errors, [], "unrelated mutation harness error")
                self.assertEqual(len(result.failures), failures, "root control must turn RED")

if __name__ == "__main__":
    unittest.main()
