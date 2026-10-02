"""Real tagged/detached Git fixtures and executable fake Cargo; HTTPS replaced before any GET."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import ssl
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.response
import crate_publisher as p

NAMES = "lightr-core lightr-init lightr-store lightr-index lightr-oci lightr-views lightr-engine lightr-run hugr-lightr-cri-backend lightr-build hugr-lightr".split()
SECRETS = {key: "synthetic-" + key + "-secret" for key in p.io.TOKEN_KEYS}
FAKE = '''import gzip, io, json, os, pathlib, sys, tarfile
base = pathlib.Path(__file__).parent
mode = json.loads((base / 'mode.json').read_text())
with (base / 'calls.jsonl').open('a') as f:
    f.write(json.dumps([sys.argv[1:], dict(os.environ)]) + '\\n')
name, phase = sys.argv[sys.argv.index('-p') + 1], sys.argv[2]
output = pathlib.Path(os.environ['CARGO_TARGET_DIR']).parent
target = pathlib.Path(os.environ['CARGO_TARGET_DIR']) / 'package'
scratch = pathlib.Path(os.environ['CARGO_BUILD_BUILD_DIR']) / 'package/tmp-crate'
scratch.mkdir(parents=True, exist_ok=True)
if any(not (output / ('indexed-' + n)).exists() for n in mode['order'][:mode['order'].index(name)]):
    sys.exit(88)
settings = dict(mode, **mode.get(phase, {}))
if not settings.get('missing'):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w') as tar:
        files = {'.cargo_vcs_info.json': json.dumps({'git': {'sha1': settings['source'], 'dirty': settings.get('dirty', False)}}), 'Cargo.toml': '[package]\\nname="' + settings.get('name', name) + '"\\nversion="0.1.1"\\nlicense="' + settings.get('license', 'Apache-2.0') + '"\\n'}
        if settings.get('no_vcs'):
            del files['.cargo_vcs_info.json']
        if settings.get('change'):
            files['extra'] = 'repackaged'
        for file, text in files.items():
            body = text.encode()
            info = tarfile.TarInfo(name + '-0.1.1/' + file)
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
    body = gzip.compress(data.getvalue(), mtime=0)
    (scratch / (name + '-0.1.1.crate')).write_bytes(body)
    if phase == 'package':
        target.mkdir(parents=True, exist_ok=True)
        (target / (name + '-0.1.1.crate')).write_bytes(body)
print(' '.join(mode['secrets']))
print(os.environ.get('CARGO_REGISTRY_TOKEN', 'credential-free'), file=sys.stderr)
if phase == 'publish':
    (output / ('uploaded-' + name)).touch()
sys.exit(settings.get('exit', 0))
'''

class Tests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(p.t.SOURCE, "47f02795d0884956c4755254b5f6fc377a5938b5")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(os.chdir, Path.cwd())
        os.chdir(tmp.name)
        self.git("init", "-q")
        paths = ["crates/" + {"hugr-lightr": "lightr-cli", "hugr-lightr-cri-backend": "lightr-cri-backend"}.get(n, n) for n in NAMES + ["lightr-acceptance"]]
        Path("Cargo.toml").write_text('[workspace]\nmembers=' + json.dumps(paths) + '\nexclude=["crates/lightr-cri-serve"]\n[workspace.package]\nversion="0.1.1"\nlicense="Apache-2.0"\npublish=true\n')
        for name, path in zip(NAMES + ["lightr-acceptance"], paths):
            Path(path).mkdir(parents=True)
            Path(path, "Cargo.toml").write_text('[package]\nname="' + name + '"\nversion.workspace=true\nlicense.workspace=true\n' + ('publish=false\n' if name == "lightr-acceptance" else 'publish.workspace=true\n'))
        for path, text in [("crates/lightr-cri/Cargo.toml", '[workspace.package]\npublish=false\n'), ("crates/lightr-cri-serve/Cargo.toml", '[package]\npublish=false\n'), ("docs/RELEASE.md", '## Crates.io Order\n```sh\n' + '\n'.join('cargo publish -p ' + n for n in NAMES) + '\n```\n## Owner Publish Order\n')]:
            Path(path).parent.mkdir(exist_ok=True)
            Path(path).write_text(text)
        Path("Cargo.lock").write_text("# frozen fixture\n")
        self.commit()
        self.source = self.git("rev-parse", "HEAD")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "tag.gpgsign=false", "tag", "-a", "v0.1.1", "-m", "fixture")
        Path("publisher-only").write_text("not product source\n")
        self.commit()
        self.verifier = self.git("rev-parse", "HEAD")
        pin = patch.object(p.t, "SOURCE", self.source)
        pin.start()
        self.addCleanup(pin.stop)
        Path("bin").mkdir()
        Path("bin/cargo").write_text("#!" + sys.executable + "\n" + FAKE)
        Path("bin/cargo").chmod(0o755)
        self.mode = dict(source=self.source)
        self.network = "normal"
        self.env = dict(SECRETS, CANDIDATE_SHA=self.source, RELEASE_TAG="v0.1.1", VERIFIER_SHA=self.verifier, GITHUB_SHA=self.verifier, GITHUB_REPOSITORY=p.t.REPO, GITHUB_EVENT_NAME="workflow_dispatch", UPLOAD_AUTHORIZATION="publish-0.1.1", PATH=str(Path("bin").resolve()) + os.pathsep + os.environ["PATH"], RUSTUP_HOME=str(Path("toolchain").resolve()))
        transport = patch.object(p.io.urllib.request.HTTPSHandler, "https_open", side_effect=self.api)
        self.send = transport.start()
        self.addCleanup(transport.stop)
        tls = patch("http.client._create_https_context", return_value=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
        tls.start()  # Stubbed HTTPS cannot connect; avoid repeatedly loading macOS system certificates.
        self.addCleanup(tls.stop)

    def git(self, *args):
        return p.t.git(*args)

    def commit(self):
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")

    def api(self, request):
        name, *version = request.full_url.removeprefix(p.io.ORIGIN).split("/")
        path = p.io.archive_path(p.OUTPUT, name, publish=True)
        uploaded = (p.OUTPUT / ("uploaded-" + name)).exists()
        exists = (uploaded or self.network == "exists") if version == ["0.1.1"] else name not in p.BOOTSTRAP and self.network != "old-missing"
        if self.network in ("hidden", "transient") and version == ["0.1.1"]:
            exists = False
            self.network = "normal" if self.network == "transient" and uploaded else self.network
        if exists and uploaded and version == ["0.1.1"]:
            (p.OUTPUT / ("indexed-" + name)).touch()
        value = {"version": dict(crate=name, num=version[0], checksum=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "a" * 64, yanked=self.network == "yanked" and uploaded)} if version else {"crate": dict(id=name)}
        if self.network == "checksum" and uploaded:
            value["version"]["checksum"] = "b" * 64
        body, status = json.dumps(value if exists else {"errors": [{"detail": "fixture not found"}]}).encode(), 200 if exists else 404
        if self.network in ("403", "redirect", "malformed", "oversized") or (self.network == "upload403" and uploaded):
            status = {"403": 403, "upload403": 403, "redirect": 302}.get(self.network, 200)
            body = b"invalid" if self.network == "malformed" else b"x" * (p.io.LIMIT + 1) if self.network == "oversized" else body
        response = urllib.response.addinfourl(io.BytesIO(body), {"location": "https://other.invalid/"}, request.full_url, status)
        response.msg = "fixture"
        return response

    def call(self, command, env=None):
        Path("bin/mode.json").write_text(json.dumps(self.mode | dict(order=NAMES, secrets=list(SECRETS.values()))))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            status = p.main([command], self.env if env is None else env)
        for text in [out.getvalue()] + [f.read_text() for f in p.OUTPUT.glob("*") if f.suffix in (".json", ".log")]:
            for token in SECRETS.values():
                self.assertNotIn(token, text)
        return status, out.getvalue()

    def test_serial_auth_environment_and_receipt(self):
        self.assertEqual(self.call("preflight")[0], 0)
        self.network = "transient"
        self.assertEqual(self.call("publish")[0], 0)
        calls = [json.loads(line) for line in Path("bin/calls.jsonl").read_text().splitlines()]
        self.assertEqual([(argv[1], argv[-1]) for argv, env in calls], [(phase, name) for name in NAMES for phase in ("package", "publish")])
        for index, (argv, env) in enumerate(calls):
            phase, slot = argv[1], index // 2
            self.assertEqual(argv, ["+1.96.0", phase, "--locked", "--registry", "crates-io", "--manifest-path", str((p.OUTPUT / "product/Cargo.toml").resolve()), "-p", NAMES[slot]])
            self.assertEqual(env.get("CARGO_REGISTRY_TOKEN"), None if phase == "package" else SECRETS["BOOTSTRAP_TOKEN" if slot in (8, 10) else "TP_TOKEN"])
            self.assertEqual(set(env) - {"__CF_USER_TEXT_ENCODING", "LC_CTYPE", "CARGO_REGISTRY_TOKEN"}, {"PATH", "RUSTUP_HOME", "HOME", "CARGO_HOME", "CARGO_TARGET_DIR", "CARGO_BUILD_BUILD_DIR", "LC_ALL", "CARGO_REGISTRY_GLOBAL_CREDENTIAL_PROVIDERS", "CARGO_REGISTRY_CREDENTIAL_PROVIDER"})
            self.assertEqual(env["CARGO_REGISTRY_CREDENTIAL_PROVIDER"], "cargo:token")
            self.assertTrue(Path(env["HOME"]).is_relative_to(p.OUTPUT.resolve()))
        receipt = json.loads((p.OUTPUT / "receipt.json").read_text())
        self.assertEqual((receipt["identity"]["source"], receipt["identity"]["verifier"], receipt["state"]), (self.source, self.verifier, "COMPLETE"))
        self.assertEqual(len(receipt["crates"]), 11)
        self.assertTrue(all(r["remote"]["checksum"] == r["package_sha256"] == r["prepackage_sha256"] for r in receipt["crates"]))

    def test_identity_order_credentials_and_snapshot_before_upload(self):
        with patch.object(p.t, "SOURCE", self.verifier):
            self.assertIn("frozen candidate mismatch", self.call("preflight")[1])
        for key, value in [("CANDIDATE_SHA", self.verifier), ("VERIFIER_SHA", self.source), ("UPLOAD_AUTHORIZATION", ""), ("GITHUB_REPOSITORY", "other/repo"), ("GITHUB_EVENT_NAME", "push"), ("RELEASE_TAG", "v9.9.9"), ("BOOTSTRAP_TOKEN", " ")]:
            self.assertEqual(self.call("preflight", self.env | {key: value})[0], 1)
        for order in (p.ORDER[:-1], p.ORDER[:-1] + (p.ORDER[0],), p.ORDER[::-1]):
            with patch.object(p, "ORDER", order):
                self.assertIn("order", self.call("preflight")[1])
        self.assertEqual(self.call("publish")[0], 1)
        self.assertEqual(self.call("preflight")[0], 0)
        self.assertEqual(self.call("publish", self.env | {"TP_TOKEN": ""})[0], 1)
        saved = (p.OUTPUT / "preflight.json").read_text()
        (p.OUTPUT / "preflight.json").write_text("{}")
        self.assertIn("snapshot mismatch", self.call("publish")[1])
        (p.OUTPUT / "preflight.json").write_text(saved)
        product = p.OUTPUT / "product"
        self.git("-C", str(product), "checkout", "--detach", self.verifier)
        self.assertIn("HEAD mismatch", self.call("publish")[1])
        self.git("-C", str(product), "checkout", "--detach", self.source)
        (product / "Cargo.lock").write_text("dirty")
        self.assertIn("dirty", self.call("publish")[1])
        self.git("-C", str(product), "restore", "Cargo.lock")
        (p.OUTPUT / "cargo").mkdir()
        self.assertEqual(self.call("publish")[0], 1)
        self.assertFalse(Path("bin/calls.jsonl").exists())

    def test_partial_nonzero_packages_checksums_and_visibility(self):
        cases = [dict(publish=dict(exit=7)), dict(source="f" * 40), dict(dirty=True), dict(name="wrong"),
                 dict(license="MIT"), dict(no_vcs=True), dict(missing=True), dict(package=dict(exit=9)),
                 dict(publish=dict(source="f" * 40)), dict(publish=dict(license="MIT")), dict(publish=dict(no_vcs=True)),
                 dict(publish=dict(change=True)), dict(publish=dict(missing=True)), dict(network="checksum"),
                 dict(network="hidden"), dict(network="upload403"), dict(network="yanked"), dict(spawn=True)]
        for index, mode in enumerate(cases):
            with self.subTest(mode=mode), patch.object(p, "OUTPUT", Path("case-" + str(index))), patch.object(p.io.time, "monotonic", side_effect=range(0, 10000, 121)):
                self.mode = dict(source=self.source)
                self.network = "normal"
                self.assertEqual(self.call("preflight")[0], 0)
                self.mode.update(mode)
                self.network = mode.get("network", "normal")
                uploads_before = sum(json.loads(l)[0][1] == "publish" for l in Path("bin/calls.jsonl").read_text().splitlines()) if Path("bin/calls.jsonl").exists() else 0
                self.assertEqual(self.call("publish", self.env | {"PATH": "missing-cargo"} if mode.get("spawn") else self.env)[0], 1)
                ledger = json.loads((p.OUTPUT / "ledger.json").read_text())
                self.assertEqual((ledger["state"], len(ledger["crates"])), ("PARTIAL_FAILED", 1))
                self.assertFalse((p.OUTPUT / "receipt.json").exists())
                before_write = any(k in mode for k in ("source", "dirty", "name", "license", "no_vcs", "missing", "spawn", "package"))
                uploads = [json.loads(l)[0] for l in Path("bin/calls.jsonl").read_text().splitlines() if json.loads(l)[0][1] == "publish"]
                self.assertEqual(len(uploads), uploads_before + (0 if before_write else 1))
                self.assertEqual((p.OUTPUT / ("uploaded-" + NAMES[0])).exists(), not before_write)
                if mode.get("publish", {}).get("exit") == 7:
                    row = ledger["crates"][0]
                    self.assertEqual((row["exit"], row["remote"]["state"], row["remote"]["checksum"]), (7, "existing", row["package_sha256"]))
                self.assertIn("already started", self.call("publish")[1])
                if mode.get("publish", {}).get("change"):
                    row = ledger["crates"][0]
                    self.assertNotEqual(row["package_sha256"], row["prepackage_sha256"])
                    self.assertEqual(row["remote"]["checksum"], row["package_sha256"])
        self.assertEqual(sum(json.loads(l)[0][1] == "publish" for l in Path("bin/calls.jsonl").read_text().splitlines()), 10)

    def test_registry_fail_closed_and_positive_control(self):
        self.assertEqual(p.io.registry(NAMES[0], "0.1.0")["state"], "existing")
        for mode in ("403", "redirect", "malformed", "oversized", "old-missing", "exists"):
            before = self.send.call_count
            self.network = mode
            self.assertIn("already exists" if mode == "exists" else "registry", self.call("preflight")[1])
            self.assertEqual(self.send.call_count - before, 2 if mode == "exists" else 1)
        self.assertFalse(Path("bin/calls.jsonl").exists())

if __name__ == "__main__":
    unittest.main()
