"""Standalone IO guards plus mandatory credential-free real Cargo 1.96 dry-run conformance."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.response
import crate_publish_io as c

TOKENS = ("TP_TOKEN", "BOOTSTRAP_TOKEN", "GH_TOKEN", "GITHUB_TOKEN",
          "GH_RUNTIME_TOKEN", "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN")
CHILD_KEYS = {"PATH", "RUSTUP_HOME", "HOME", "CARGO_HOME", "CARGO_TARGET_DIR", "CARGO_BUILD_BUILD_DIR",
              "LC_ALL", "CARGO_REGISTRY_GLOBAL_CREDENTIAL_PROVIDERS", "CARGO_REGISTRY_CREDENTIAL_PROVIDER", "CARGO_HTTP_MULTIPLEXING"}


class Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="crate-io-")
        self.addCleanup(tmp.cleanup)
        self.output = Path(tmp.name)
        for directory in ("home", "cargo", "target", "build", "product/src"):
            (self.output / directory).mkdir(parents=True)
        self.product = self.output / "product"
        self.env = dict(PATH=os.environ["PATH"], RUSTUP_HOME="parent-toolchain",
                        **{k: "synthetic-" + k + "-secret" for k in TOKENS})

    def test_capture_all_credentials_json_and_spawn_errors(self):
        values = " ".join(self.env[k] for k in TOKENS)
        result = Mock(returncode=7, stdout=values.encode(), stderr=values.encode())
        with patch.object(c.subprocess, "run", return_value=result) as run, contextlib.redirect_stdout(io.StringIO()) as out:
            row = c.cargo(self.output, self.product, "probe", "publish", self.env, "BOOTSTRAP_TOKEN")
        self.assertEqual(row["exit"], 7)
        child = run.call_args.kwargs["env"]
        self.assertEqual(set(child), CHILD_KEYS | {"CARGO_REGISTRY_TOKEN"})
        self.assertEqual(child["CARGO_HTTP_MULTIPLEXING"], "false")
        self.assertTrue(set(child).isdisjoint(TOKENS))
        self.assertEqual(child["CARGO_REGISTRY_TOKEN"], self.env["BOOTSTRAP_TOKEN"])
        self.assertNotIn("CARGO_REGISTRY_TOKEN", c.child_env(self.output, self.env))
        self.assertIsInstance(c.safe((values,), self.env), list)
        c.write(self.output, "safe.json", {values: [(values, {"nested": (values, (values,))}), row]}, self.env)
        with patch.object(c.subprocess, "run", side_effect=OSError(values)), contextlib.redirect_stdout(out):
            self.assertIsNone(c.cargo(self.output, self.product, "probe", "package", self.env)["exit"])
        for text in [out.getvalue()] + [f.read_text() for f in self.output.glob("*") if f.suffix in (".json", ".log")]:
            for key in TOKENS:
                self.assertNotIn(self.env[key], text)

    def test_package_credentials_rejected_before_spawn(self):
        with patch.object(c.subprocess, "run", return_value=Mock(returncode=0, stdout=b"", stderr=b"")) as spawn:
            for phase, dry_run in (("package", False), ("publish", True)):
                for token in ("TP_TOKEN", "BOOTSTRAP_TOKEN"):
                    with self.assertRaises(c.ReadinessError):
                        c.cargo(self.output, self.product, "probe", phase, self.env, token, dry_run=dry_run)
            spawn.assert_not_called()

    def test_archive_source_license_and_notary_marker(self):
        path = c.archive_path(self.output, "probe", publish=True)
        path.parent.mkdir(parents=True)
        bad_entries = [("/outside", tarfile.REGTYPE), ("probe-0.1.1/../outside", tarfile.REGTYPE),
                       ("other-root/file", tarfile.REGTYPE), ("probe-0.1.1//file", tarfile.REGTYPE),
                       ("probe-0.1.1/./file", tarfile.REGTYPE), ("probe-0.1.1/duplicate", tarfile.REGTYPE),
                       ("probe-0.1.1/link", tarfile.SYMTYPE), ("probe-0.1.1/link", tarfile.LNKTYPE),
                       ("probe-0.1.1/device", tarfile.CHRTYPE), ("probe-0.1.1/fifo", tarfile.FIFOTYPE),
                       ("probe-0.1.1/..\\outside", tarfile.REGTYPE), ("probe-0.1.1/block", tarfile.BLKTYPE)]
        for defect in [None, "source", "license", "notary", "dirty", "name", "version", "rootfile"] + bad_entries:
            vcs = json.dumps(dict(git=dict(sha1="b" * 40 if defect == "source" else "a" * 40, dirty=defect == "dirty")))
            manifest = '[package]\nname="' + ("wrong" if defect == "name" else "probe") + '"\nversion="' + ("9.9.9" if defect == "version" else "0.1.1") + '"\nlicense="' + ("MIT" if defect == "license" else "Apache-2.0") + '"\n'
            with tarfile.open(path, "w:gz") as archive:
                directory = tarfile.TarInfo("probe-0.1.1")
                directory.type = tarfile.REGTYPE if defect == "rootfile" else tarfile.DIRTYPE
                archive.addfile(directory)
                for name, text in {"Cargo.toml": manifest, ".cargo_vcs_info.json": vcs}.items():
                    if defect == "notary" and name == ".cargo_vcs_info.json":
                        continue
                    body = text.encode()
                    member = tarfile.TarInfo("probe-0.1.1/" + name)
                    member.size = len(body)
                    archive.addfile(member, io.BytesIO(body))
                if isinstance(defect, tuple):
                    extra = tarfile.TarInfo(defect[0])
                    extra.type, extra.linkname = defect[1], "../../outside"
                    archive.addfile(extra, io.BytesIO())
                    if defect[0] == "probe-0.1.1/duplicate":
                        archive.addfile(extra, io.BytesIO())
            if defect is None:
                c.verify_archive(path, "probe", "a" * 40)
                self.assertEqual(c.package_sha(path), c.hashlib.sha256(path.read_bytes()).hexdigest())
            else:
                if defect == "rootfile":
                    with tarfile.open(path, "r:gz") as archive:
                        self.assertEqual([m.name for m in archive.getmembers()].count("probe-0.1.1"), 1)
                        self.assertTrue(archive.getmember("probe-0.1.1").isfile())
                expected = "package member type/link forbidden" if defect == "rootfile" else ""
                with self.subTest(defect=defect), self.assertRaisesRegex(c.ReadinessError, expected):
                    c.verify_archive(path, "probe", "a" * 40)

    def test_public_get_boundaries_and_checksum_polling(self):
        url = c.ORIGIN + "probe/0.1.1"
        good = {"version": dict(crate="probe", num="0.1.1", checksum="a" * 64, yanked=False)}
        def response(status, body):
            value = urllib.response.addinfourl(io.BytesIO(body), {"location": "https://other.invalid/"}, url, status)
            value.msg = "fixture"
            return value
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        valid = json.dumps(good).encode()
        cases = [(200, json.dumps(good).encode(), True), (404, b'{"errors":[{"detail":"absent"}]}', True),
                 (400, valid, False), (200, valid + b" " * (c.LIMIT + 1 - len(valid)), False),
                 (403, b"forbidden", False), (302, b"redirect", False), (200, b"bad JSON", False),
                 (404, b"bad JSON", False), (200, b"x" * (c.LIMIT + 1), False)]
        for change in (dict(checksum="a" * 63), dict(checksum="A" * 64), dict(checksum="g" * 64),
                       dict(checksum=123), dict(yanked="false"), dict(yanked=0), dict(crate="wrong"), dict(num="9.9.9")):
            cases.append((200, json.dumps({"version": good["version"] | change}).encode(), False))
        for status, body, accepted in cases:
            with (
                patch("http.client._create_https_context", return_value=tls),
                patch.object(c.urllib.request.HTTPSHandler, "https_open", return_value=response(status, body)) as send,
                patch.object(c.urllib.request, "build_opener", wraps=c.urllib.request.build_opener) as opener,
                patch.object(c.urllib.request, "getproxies", return_value={"https": "http://proxy.invalid"}),
            ):
                if accepted:
                    self.assertEqual(c.registry("probe", "0.1.1")["state"], "existing" if status == 200 else "absent")
                else:
                    expected = "registry"
                    if status == 400:
                        expected = "registry HTTP failure"
                    elif len(body) > c.LIMIT:
                        expected = "registry response size invalid"
                    elif status == 200 and body.startswith(b'{"version"'):
                        expected = "registry version/checksum malformed"
                    with self.assertRaisesRegex(c.ReadinessError, expected):
                        c.registry("probe", "0.1.1")
                self.assertEqual(send.call_count, 1)
                self.assertIsInstance(opener.call_args.args[0], c.urllib.request.ProxyHandler)
                self.assertEqual(opener.call_args.args[0].proxies, {})
                self.assertEqual((send.call_args.args[0].full_url, send.call_args.args[0].get_method()), (url, "GET"))
                self.assertNotIn("Authorization", send.call_args.args[0].headers)
        for change in ({}, dict(checksum="b" * 64), dict(yanked=True)):
            row = dict(name="probe", package_sha256="a" * 64, remote=dict(state="unknown"))
            remote = dict(state="existing", checksum="a" * 64, yanked=False) | change
            with patch.object(c, "registry", side_effect=[dict(state="absent"), remote]), patch.object(c.time, "sleep") as sleep:
                if change:
                    with self.assertRaises(c.ReadinessError):
                        c.observe(row, poll=True)
                else:
                    c.observe(row, poll=True)
                sleep.assert_called_once_with(5)

    def test_real_cargo196_publish_scratch_and_verification(self):
        parent = {k: os.environ[k] for k in ("PATH", "HOME", "RUSTUP_HOME") if k in os.environ}
        rustup = shutil.which("rustup", path=parent["PATH"])
        self.assertIsNotNone(rustup, "real Rustup/Cargo 1.96 is required, never skipped")
        binary = self.output / "bin"
        binary.mkdir()
        (binary / "cargo").symlink_to(Path(rustup).resolve())
        parent["PATH"] = str(binary) + os.pathsep + parent["PATH"]
        child = c.child_env(self.output, parent)
        self.assertNotIn("CARGO_REGISTRY_TOKEN", child)
        self.assertEqual(set(child), CHILD_KEYS)
        self.assertTrue(set(child).isdisjoint(TOKENS))
        def run(*args):
            return subprocess.run(args, cwd=self.product, env=child, capture_output=True, text=True, timeout=90)
        version = run("cargo", "+1.96.0", "--version")
        self.assertEqual(version.returncode, 0)
        self.assertTrue(version.stdout.startswith("cargo 1.96.0 "))
        (self.product / "Cargo.toml").write_text('[package]\nname="publisher-layout-probe"\nversion="0.1.1"\nedition="2021"\nlicense="Apache-2.0"\ndescription="Cargo archive conformance fixture"\n')
        (self.product / "src/lib.rs").write_text("pub fn answer() -> u8 { 42 }\n")
        self.assertEqual(run("cargo", "+1.96.0", "generate-lockfile", "--offline").returncode, 0)
        git_env = child | dict(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        def git(*args):
            return subprocess.run(["git", *args], cwd=self.product, env=git_env, capture_output=True, text=True, check=True).stdout.strip()
        git("init", "-q")
        git("add", ".")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
        source = git("rev-parse", "HEAD")
        with contextlib.redirect_stdout(io.StringIO()):
            packaged = c.cargo(self.output, self.product, "publisher-layout-probe", "package", parent, offline=True)
        self.assertEqual(packaged["exit"], 0, (self.output / packaged["log"]).read_text())
        prepared = c.archive_path(self.output, "publisher-layout-probe")
        scratch = c.archive_path(self.output, "publisher-layout-probe", publish=True)
        self.assertEqual(scratch.relative_to(self.output).as_posix(), "build/package/tmp-crate/publisher-layout-probe-0.1.1.crate")
        self.assertTrue(prepared.is_file() and scratch.is_file(), "real Cargo must honor distinct target/build directories")
        c.verify_archive(prepared, "publisher-layout-probe", source)
        expected = c.package_sha(prepared)
        prepared.unlink()
        scratch.unlink()
        with contextlib.redirect_stdout(io.StringIO()):
            published = c.cargo(self.output, self.product, "publisher-layout-probe", "publish", parent, dry_run=True)
        log = (self.output / published["log"]).read_text()
        self.assertEqual(published["exit"], 0, log)
        self.assertIn("aborting upload due to dry run", log)
        self.assertFalse(prepared.exists(), "publish must not uplift package into TARGET")
        c.verify_archive(scratch, "publisher-layout-probe", source)
        self.assertEqual(c.package_sha(scratch), expected)
        (self.product / "src/lib.rs").write_text("pub fn broken( {\n")
        git("add", ".")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "broken control")
        with contextlib.redirect_stdout(io.StringIO()):
            broken = c.cargo(self.output, self.product, "publisher-layout-probe", "package", parent, offline=True)
        self.assertNotEqual(broken["exit"], 0, "verification cannot be skipped or stubbed")
        self.assertIn("failed to verify package tarball", (self.output / broken["log"]).read_text())
        print("REAL " + version.stdout.strip() + " dry-run: build/package/tmp-crate/publisher-layout-probe-0.1.1.crate sha256=" + expected)


if __name__ == "__main__":
    unittest.main()
