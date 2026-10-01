"""Portable fixtures exercise transport wiring, not GitHub or native qualification."""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import tarfile
import types
import unittest
from unittest.mock import patch
import zipfile
import public_release_install as p
from test_macos_candidate import Fixture as BaseFixture

class Fixture(BaseFixture):
    def __init__(self):
        super().__init__("0.1.1")
    def __enter__(self):
        super().__enter__()
        os.environ.update(PUBLIC_RELEASE_RUN_ID="123", PUBLIC_RELEASE_ID="99", RELEASE_TAG="v0.1.1", PUBLIC_RELEASE_TARGET="darwin-arm64",
                          VERIFIER_SHA="b" * 40, GITHUB_SHA="b" * 40, HEAD_SHA="b" * 40,
                          GITHUB_REPOSITORY=p.REPO, GH_TOKEN="fixture-private-token")
        self.tool(self.root / "tools", "codesign", "print('Signature=adhoc' if '-dv' in sys.argv else '<?xml version=\"1.0\"?><plist><dict><key>com.apple.security.virtualization</key><true/></dict></plist>' if '-d' in sys.argv else '')")
        self.tool(self.root / "tools", "git", "print('" + "b"*40 + "')")
        build = ["Checkout", "Verify owner-selected candidate and tag", "Build release binary", "Package tarball and checksum", "Upload build artifact"]
        job_specs = [("build (darwin-arm64)", build + ["Sign and notarize (macOS)"]), ("build (linux-x86_64)", build),
                     ("assemble draft GitHub Release", ["Download Unix-first artifacts", "Assemble SHA256SUMS", "Create draft release"])]
        self.tarname = self.tar.name; self.linux = "lightr-0.1.1-linux-x86_64.tar.gz"
        self.rows = {
            "actions/runs/123": dict(id=123, run_attempt=1, path=".github/workflows/release.yml", workflow_id=299070533, event="workflow_dispatch", head_sha="a" * 40, status="completed", conclusion="success"),
            "actions/runs/123/jobs?per_page=100": dict(total_count=3, jobs=[dict(id=i+1, name=n, status="completed", conclusion="success", steps=[dict(name=s, status="completed", conclusion="success") for s in steps]) for i, (n, steps) in enumerate(job_specs)]),
            "contents/Cargo.toml?ref=" + "a" * 40: dict(encoding="base64", content=base64.b64encode(b'[workspace.package]\nversion="0.1.1"\n').decode()),
            "git/ref/tags/v0.1.1": dict(object=dict(type="tag", sha="c" * 40)),
            "git/tags/" + "c" * 40: dict(tag="v0.1.1", object=dict(type="commit", sha="a" * 40)),
            "releases/99": dict(id=99, draft=True, tag_name="v0.1.1", assets=[dict(id=i+10, name=n) for i, n in enumerate([self.linux, self.linux+".sha256", self.tarname, self.tarname+".sha256", "SHA256SUMS"])]),
            "actions/runs/123/artifacts?per_page=100": dict(total_count=1, artifacts=[dict(id=77, name="release-darwin-arm64", expired=False, size_in_bytes=100, workflow_run=dict(id=123, head_sha="a" * 40))])}
        self.refresh()
        return self
    def refresh(self, version="lightr 0.1.1 (aaaaaaa, 2026-09-30)", help="Usage: lightr", member="lightr", extra=None, tail=""):
        self.pack(name=member, content=f'#!/bin/sh\ncase "$1" in --version) echo "{version}";; --help) echo "{help}";; esac\n{tail}\n'.encode())
        tar = self.tar.read_bytes(); checksum = Path(str(self.tar)+".sha256").read_bytes()
        self.rows["releases/assets/12"] = tar; self.rows["releases/assets/13"] = checksum
        self.rows["releases/assets/14"] = f'{"0"*64}  {self.linux}\n'.encode() + checksum
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as zipped:
            zipped.writestr(self.tarname, tar); zipped.writestr(self.tarname+".sha256", checksum)
            if extra: zipped.writestr(extra, b"bad")
        self.rows["actions/artifacts/77/zip"] = output.getvalue()
        self.rows["actions/runs/123/artifacts?per_page=100"]["artifacts"][0]["digest"] = "sha256:" + p.sha(output.getvalue())
        for asset in self.rows["releases/99"]["assets"]:
            asset["size"] = len(self.rows.get(f"releases/assets/{asset['id']}", b"x"))
    def get(self, endpoint, binary=False):
        return self.rows[endpoint]
    def verify(self):
        return p.verify(p.PublicEvidence("receipt"), self, os.environ)
    def checksum(self, record):
        self.rows["releases/assets/13"] = record
        blob = io.BytesIO()
        with zipfile.ZipFile(blob, "w") as opened:
            opened.writestr(self.tarname, self.tar.read_bytes()); opened.writestr(self.tarname+".sha256", record)
        self.rows["actions/artifacts/77/zip"] = blob.getvalue()
        self.rows["actions/runs/123/artifacts?per_page=100"]["artifacts"][0]["digest"] = "sha256:"+p.sha(blob.getvalue())
        self.rows["releases/99"]["assets"][3]["size"] = len(record)

class Tests(unittest.TestCase):
    def setUp(self):
        output = contextlib.redirect_stdout(io.StringIO()); output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)
    def test_clean_receipt_and_transport(self):
        with Fixture() as f:
            # Real subprocess gh stub: fixed GET argv, binary stdout, isolated config.
            Path("responses.json").write_text(json.dumps({k: base64.b64encode(v if isinstance(v, bytes) else json.dumps(v).encode()).decode() for k, v in f.rows.items()}))
            f.tool(f.root / "tools", "gh", f"import json, base64\nassert sys.argv[1:6] == ['api', '--hostname', 'github.com', '--method', 'GET']\nassert os.environ['GH_TOKEN'] == 'fixture-private-token'\nassert 'HOME' not in os.environ\nkey = sys.argv[6].removeprefix('repos/{p.REPO}/')\nmedia = 'application/octet-stream' if key.startswith('releases/assets/') else 'application/vnd.github+json'\nassert sys.argv[7:] == ['-H', 'Accept: ' + media]\nsys.stdout.buffer.write(base64.b64decode(json.load(open('responses.json'))[key]))")
            e = p.PublicEvidence("receipt"); api = p.Api(e, os.environ["GH_TOKEN"])
            data = p.verify(e, api, os.environ)
            self.assertEqual(data["compiled_source"], "a"*40); self.assertEqual(data["verification_workflow_sha"], "b"*40); self.assertEqual(data["producer_run"]["run_attempt"], 1)
            self.assertEqual(data["release_id"], 99)
            self.assertEqual(data["vz_boot"], "NOT EXECUTED"); self.assertEqual(len(data["release_assets"]), 5)
            with tarfile.open(f.tar) as opened:
                self.assertEqual(data["binary_sha256"], p.sha(opened.extractfile("lightr").read()))
            smoke = [c for c in data["commands"] if c["argv"][-1] in ("--version", "--help")]
            self.assertEqual(len(smoke), 2); self.assertTrue(all(c["exit_code"] == 0 and c["output"] for c in smoke))
            self.assertTrue(all(set(c["env"]) == {"HOME"} for c in smoke)); self.assertFalse(Path(smoke[0]["env"]["HOME"]).exists())
            self.assertNotIn("fixture-private-token", Path("receipt/commands.json").read_text())
            self.assertEqual(json.loads(Path("receipt/receipt.json").read_text()), data)
            with self.assertRaisesRegex(ValueError, "endpoint forbidden"): api.get("../other")
    def test_rejects_named_defects(self):
        cases = [
            ("run source", "producer run", lambda f: f.rows["actions/runs/123"].update(head_sha="d"*40)),
            ("run workflow", "producer run", lambda f: f.rows["actions/runs/123"].update(workflow_id=1)),
            ("run event", "producer run", lambda f: f.rows["actions/runs/123"].update(event="push")),
            ("run pending", "producer run", lambda f: f.rows["actions/runs/123"].update(status="in_progress")),
            ("run attempt missing", "producer run", lambda f: f.rows["actions/runs/123"].pop("run_attempt")),
            ("step malformed", "malformed producer step rows", lambda f: f.rows["actions/runs/123/jobs?per_page=100"]["jobs"][0].update(steps=[None])),
            ("asset malformed", "malformed release asset rows", lambda f: f.rows["releases/99"].update(assets=[None])),
            ("release ID", "draft release ID/tag", lambda f: f.rows["releases/99"].update(id=100)),
            ("release tag", "draft release ID/tag", lambda f: f.rows["releases/99"].update(tag_name="v0.1.0")),
            ("release public", "draft release ID/tag", lambda f: f.rows["releases/99"].update(draft=False)),
            ("job name malformed", "producer jobs exact/success", lambda f: f.rows["actions/runs/123/jobs?per_page=100"]["jobs"][0].update(name=None)),
            ("tag source", "tag candidate", lambda f: f.rows["git/tags/"+"c"*40]["object"].update(sha="d"*40)),
            ("lightweight", "annotated tag", lambda f: f.rows["git/ref/tags/v0.1.1"]["object"].update(type="commit")),
            ("version", "Cargo/tag version", lambda f: f.rows["contents/Cargo.toml?ref="+"a"*40].update(content=base64.b64encode(b'[workspace.package]\nversion="0.2.0"').decode())),
            ("ZIP hash", "ZIP digest", lambda f: f.rows["actions/runs/123/artifacts?per_page=100"]["artifacts"][0].update(digest="sha256:"+"0"*64)),
            ("artifact source", "artifact identity/expiry", lambda f: f.rows["actions/runs/123/artifacts?per_page=100"]["artifacts"][0]["workflow_run"].update(head_sha="d"*40)),
            ("artifact expired", "artifact identity/expiry", lambda f: f.rows["actions/runs/123/artifacts?per_page=100"]["artifacts"][0].update(expired=True)),
            ("checksum", "checksum record", lambda f: f.checksum(b"bad\n")),
            ("checksum duplicate", "checksum record", lambda f: f.checksum(f.rows["releases/assets/13"]*2)),
            ("ZIP file", "ZIP exact", lambda f: f.refresh(extra="../outside")),
            ("public bytes", "release/producer bytes", lambda f: f.rows.update({"releases/assets/12": b"x"*len(f.rows["releases/assets/12"])})),
            ("asset hash", "asset size/digest", lambda f: f.rows["releases/99"]["assets"][2].update(digest="sha256:"+"0"*64)),
            ("aggregate duplicate", "aggregate exact", lambda f: f.rows.update({"releases/assets/14": f.rows["releases/assets/13"]*2})),
            ("archive member", "only regular", lambda f: f.refresh(member="../lightr")),
            ("CLI source", "metadata mismatch", lambda f: f.refresh(version="lightr 0.1.1 (ddddddd, 2026-09-30)")),
            ("CLI version", "metadata mismatch", lambda f: f.refresh(version="lightr 0.2.0 (aaaaaaa, 2026-09-30)")),
            ("CLI help", "help Usage", lambda f: f.refresh(help="")),
            ("CLI date", "day.*range", lambda f: f.refresh(version="lightr 0.1.1 (aaaaaaa, 2026-02-30)")),
            ("CLI changes binary", "binary hash after", lambda f: f.refresh(tail='printf "\\n#changed\\n" >> "$0"')),
            ("signature", "command failed", lambda f: f.tool(f.root/"tools", "codesign", "sys.exit(1)")),
            ("entitlement", "BOOL true", lambda f: f.tool(f.root/"tools", "codesign", "print('<?xml version=\"1.0\"?><plist><dict><key>com.apple.security.virtualization</key><string>true</string></dict></plist>')")),
            ("cleanup", "HOME cleanup", lambda f: f.tool(f.root/"tools", "rm", "pass")),
            ("verifier", "checkout identity", lambda f: os.environ.update(VERIFIER_SHA="d"*40)),
            ("native", "native target", lambda f: f.tool(f.root/"tools", "uname", "print('Linux' if sys.argv[1]=='-s' else 'x86_64')")),
        ]
        for label, error, mutate in cases:
            if getattr(Tests, "only_defect", label) != label: continue
            with self.subTest(defect=label), Fixture() as f:
                mutate(f)
                if label == "aggregate duplicate": f.rows["releases/99"]["assets"][4]["size"] = len(f.rows["releases/assets/14"])
                with self.assertRaisesRegex(ValueError, error): f.verify()
                self.assertFalse(Path("receipt/receipt.json").exists()); self.assertTrue(Path("receipt/commands.json").is_file())
                if label in ("CLI source", "CLI version", "CLI help"):
                    self.assertEqual(list(Path("receipt").glob("fresh-home-*")), [])
    def test_empty_missing_lists_and_skipped_steps(self):
        for key, field in (("actions/runs/123/jobs?per_page=100", "jobs"), ("actions/runs/123/artifacts?per_page=100", "artifacts"), ("releases/99", "assets")):
            for value in (None, []):
                with self.subTest(field=field, value=value), Fixture() as f:
                    f.rows[key][field] = value
                    with self.assertRaisesRegex(ValueError, "missing/empty"): f.verify()
        for index, count in ((0, 6), (1, 5), (2, 3)):
            for defect in ("missing", "empty", "malformed") + tuple(range(count)):
                with self.subTest(job=index, defect=defect), Fixture() as f:
                    job = f.rows["actions/runs/123/jobs?per_page=100"]["jobs"][index]
                    if defect == "missing": job.pop("steps")
                    elif defect == "empty": job["steps"] = []
                    elif defect == "malformed": job["steps"] = [None]
                    else: job["steps"][defect]["conclusion"] = "skipped"
                    error = "producer step required" if isinstance(defect, int) else "missing/empty producer steps"
                    with self.assertRaisesRegex(ValueError, error): f.verify()
                    self.assertFalse(Path("receipt/receipt.json").exists())
    def test_elf_controls_and_failure_cleanup_postcondition(self):
        header = bytearray(64); header[:7] = b"\x7fELF\x02\x01\x01"; header[16] = 3; header[18] = 62
        p.elf(header)
        for index, value in ((0, 0), (4, 1), (5, 2), (18, 183), (16, 1)):
            bad = header.copy(); bad[index] = value
            with self.assertRaisesRegex(ValueError, "ELF64"): p.elf(bad)
        with Fixture() as f:
            f.refresh(help=""); f.tool(f.root/"tools", "rm", "pass")
            with self.assertRaisesRegex(ValueError, "HOME cleanup"): f.verify()
            self.assertFalse(Path("receipt/receipt.json").exists())
            self.assertTrue(list(Path("receipt").glob("fresh-home-*")))
    def test_input_contract(self):
        for key, value, error in (("PUBLIC_RELEASE_RUN_ID", "0", "positive producer"), ("PUBLIC_RELEASE_ID", "0", "positive release ID"), ("CANDIDATE_SHA", "A"*40, "candidate SHA"), ("RELEASE_TAG", "v0.1.1/other", "release tag"), ("GITHUB_REPOSITORY", "other/repo", "repository/token"), ("PUBLIC_RELEASE_TARGET", "linux-arm64", "public target")):
            with self.subTest(key=key), Fixture() as f:
                os.environ[key] = value
                with self.assertRaisesRegex(ValueError, error): f.verify()
        with Fixture() as f:
            f.rows["actions/runs/123/jobs?per_page=100"]["jobs"][0]["steps"] = []
            with self.assertRaisesRegex(ValueError, "missing/empty producer steps"): f.verify()
    def test_linux_install_wiring(self):
        with Fixture() as f:
            macname = f.tarname; f.tarname = f.linux; f.tar = f.tar.with_name(f.linux); f.refresh()
            for new, old in ((10, 12), (11, 13)): f.rows[f"releases/assets/{new}"] = f.rows[f"releases/assets/{old}"]
            f.rows["releases/assets/14"] = f'{"0"*64}  {macname}\n'.encode() + f.rows["releases/assets/11"]
            for asset in f.rows["releases/99"]["assets"]: asset["size"] = len(f.rows.get(f"releases/assets/{asset['id']}", b"x"))
            f.rows["actions/runs/123/artifacts?per_page=100"]["artifacts"][0]["name"] = "release-linux-x86_64"
            os.environ["PUBLIC_RELEASE_TARGET"] = "linux-x86_64"
            f.tool(f.root/"tools", "uname", "print('Linux' if sys.argv[1]=='-s' else 'x86_64')")
            f.tool(f.root/"tools", "sha256sum", "import subprocess\nsys.exit(subprocess.run(['shasum', '-a', '256']+sys.argv[1:]).returncode)")
            # Portable shell executable; numerical ELF controls execute separately.
            with patch.object(p, "elf") as header: data = f.verify()
            header.assert_called_once(); self.assertEqual(data["target"], "linux-x86_64")
            self.assertTrue(any(c["argv"][0] == "sha256sum" for c in data["commands"]))
            self.assertFalse(any(c["argv"][0] == "codesign" for c in data["commands"]))
    def test_mutation_probes(self):
        source = Path(p.__file__).read_text()
        for before, defect in (('artifact.get("digest") == f"sha256:{sha(packed)}"', "ZIP hash"), ('body == pair[name]', "public bytes")):
            self.assertEqual(source.count(before), 1)
            mutant = types.ModuleType("mutant"); exec(compile(source.replace(before, "True"), "mutant", "exec"), mutant.__dict__)
            with patch(__name__+".p", mutant), patch.object(Tests, "only_defect", defect, create=True):
                result = unittest.TestResult(); Tests("test_rejects_named_defects").run(result)
            self.assertEqual(result.errors, [], "unrelated mutation harness error")
            self.assertEqual(len(result.failures), 1, "critical check mutation must turn rejection test RED")
    def test_all_jobs_mutation_probe(self):
        source = Path(p.__file__).read_text()
        before = "for job in jobs:"
        self.assertEqual(source.count(before), 1)
        mutant = types.ModuleType("mutant")
        old_selection = 'for job in [next(j for j in jobs if j["name"] == f"build ({target})")]: '
        exec(compile(source.replace(before, old_selection), "mutant", "exec"), mutant.__dict__)
        with patch(__name__ + ".p", mutant):
            result = unittest.TestResult(); Tests("test_empty_missing_lists_and_skipped_steps").run(result)
        self.assertEqual(result.errors, [], "unrelated job mutation harness error")
        self.assertEqual(len(result.failures), 14, "other build and assembly controls must turn RED")
    def test_pinned_manifest_base64_controls(self):
        for separator in ("\n", "\r\n"):
            with self.subTest(wrap=separator), Fixture() as f:
                cargo = f.rows["contents/Cargo.toml?ref="+"a"*40]
                cargo["content"] = separator.join(cargo["content"][i:i+16] for i in range(0, len(cargo["content"]), 16)) + separator
                self.assertEqual(f.verify()["version"], "0.1.1")
        for suffix in ("!@#$", " ", "\t", "\r", "é"):
            with self.subTest(suffix=suffix), Fixture() as f:
                f.rows["contents/Cargo.toml?ref="+"a"*40]["content"] += suffix
                with self.assertRaisesRegex(ValueError, "pinned Cargo version malformed"):
                    f.verify()
                self.assertFalse(Path("receipt/receipt.json").exists())
    def test_base64_mutation_probe(self):
        source = Path(p.__file__).read_text()
        before = "base64.b64decode(content, validate=True)"
        self.assertEqual(source.count(before), 1)
        mutant = types.ModuleType("mutant"); exec(compile(source.replace(before, "base64.b64decode(content, validate=False)"), "mutant", "exec"), mutant.__dict__)
        with patch(__name__ + ".p", mutant):
            result = unittest.TestResult(); Tests("test_pinned_manifest_base64_controls").run(result)
        self.assertEqual(result.errors, [], "unrelated base64 mutation harness error")
        self.assertEqual(len(result.failures), 4, "permissive base64 must turn RED")

if __name__ == "__main__":
    unittest.main()
