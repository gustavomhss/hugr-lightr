"""Hosted OCI/artifact/install evidence only; never executes or qualifies VZ boot."""
import hashlib
from datetime import date
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import tarfile
import tempfile
from xml.parsers.expat import ExpatError

if sys.version_info < (3, 11):
    raise RuntimeError("Python >=3.11 required")
import tomllib

CARGO = ["cargo", "+1.96.0", "test", "--locked", "-p", "lightr-oci", "--lib"]
WITNESSES = [
    "oci::tests::integrity_tests::test_write_through_symlink_component_rejects_import_without_ref",
    "store::image_ref::tests::concurrent_tuple_reads_never_observe_mixed_publication",
    "oci::tests::import_tests::test_import_layout_two_layers_whiteout_and_hydrate",
    "oci::load::load_tests::save_load_roundtrip_lossless",
    "oci::tests::pull_tests::test_pull_alpine_network_gated",
    "oci::tests::import_tests::test_path_escape_rejects_import_without_ref",
    "oci::layer::unix::tests::cleanup_removes_owned_stage_before_drop",
    "oci::layer::unix::tests::cleanup_rejects_replaced_stage_and_preserves_both_trees",
]
QUALIFICATION = dict(vz_boot="NOT EXECUTED", blocked="Hosted macos-14 VM has no nested Virtualization.framework support",
                     reference="https://docs.github.com/en/actions/reference/runners/github-hosted-runners#limitations-for-arm64-macos-runners",
                     R2="incomplete", R3="incomplete", signing="ad-hoc; unsigned; no Developer ID; not notarized")

def require(condition, message):
    if not condition:
        raise ValueError(message)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def declared_version():
    try:
        with Path("Cargo.toml").open("rb") as manifest:
            version = tomllib.load(manifest)["workspace"]["package"]["version"]
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError) as error:
        raise ValueError("missing/malformed Cargo.toml workspace.package.version") from error
    require(isinstance(version, str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version), "invalid declared version")
    return version

def artifact_name(version):
    return f"lightr-{version}-darwin-arm64-unsigned.tar.gz"

class Evidence:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.mkdir()
        self.commands = []
        (self.path / "commands.json").write_text("[]\n")
    def run(self, *argv, cwd=None, env=None):
        log = self.path / f"{len(self.commands):02d}.log"
        with log.open("wb") as output:
            result = subprocess.run(argv, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
        text = log.read_bytes().decode("utf-8", errors="replace")
        print(text, end="", flush=True)
        self.commands.append(dict(argv=list(argv), cwd=str(Path(cwd or os.getcwd()).resolve()),
                                  exit_code=result.returncode, output=text, log=log.name,
                                  env={k: env.get(k) for k in ("HOME", "LIGHTR_HOME", "LIGHTR_STORE_DIR", "LIGHTR_LINUX_PACK")} if env else {}))
        (self.path / "commands.json").write_text(json.dumps(self.commands, indent=2))
        require(result.returncode == 0, f"command failed: {argv}")
        return text.strip()
    def host(self):
        sha = os.environ["CANDIDATE_SHA"]
        require(re.fullmatch("[0-9a-f]{40}", sha) and sha == os.environ["WORKFLOW_SHA"], "candidate identity")
        require(self.run("git", "rev-parse", "HEAD") == sha, "checkout identity")
        require(self.run("uname", "-s") == "Darwin" and self.run("uname", "-m") == "arm64", "native Darwin arm64 required")
        require(self.run("sysctl", "-n", "hw.optional.arm64") == "1", "arm64 capability")
        return dict(candidate_sha=sha, workflow_sha=sha, target="aarch64-apple-darwin", version=declared_version(),
                    model=self.run("sysctl", "-n", "hw.model"), os=self.run("sw_vers"),
                    runner={k: os.environ.get(k) for k in ("RUNNER_OS", "RUNNER_ARCH", "ImageOS", "ImageVersion", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")})
    def save(self, data):
        data.update(commands=self.commands, qualification=QUALIFICATION)
        receipt = self.path / "receipt.json"
        receipt.write_text(json.dumps(data, indent=2) + "\n")
        return digest(receipt)

def witness(text, name=None):
    summaries = re.findall(r"^test result: (.+)$", text, re.M)
    require(len(summaries) == 1, "missing/duplicate test summary")
    require(re.fullmatch(r"ok\. ([1-9][0-9]*) passed; 0 failed; 0 ignored; 0 measured; [0-9]+ filtered out; finished in .+", summaries[0]), "failed/ignored/empty witness")
    if name:
        require(summaries[0].startswith("ok. 1 passed;") and text.splitlines().count(f"test {name} ... ok") == 1, "exact witness not executed")
    require("SKIPPED" not in text, "network witness skipped")

def archive(e, directory, version, expected=None):
    artifact = artifact_name(version)
    if expected:
        require(expected["version"] == version and expected["artifact"] == artifact, "original receipt version/filename")
    tar = Path(directory).resolve() / artifact
    sha = digest(tar)
    checksum = Path(str(tar) + ".sha256")
    require(checksum.read_text() == f"{sha}  {artifact}\n", "checksum record/filename")
    if expected:
        require(expected["sha256"] == sha, "original receipt archive hash")
    e.run("shasum", "-a", "256", "-c", checksum.name, cwd=tar.parent)
    with tarfile.open(tar) as opened:
        members = opened.getmembers()
        require(len(members) == 1 and members[0].name == "lightr" and members[0].isfile() and members[0].mode == 0o755, "tar must contain only regular executable lightr")
        binary_sha = hashlib.sha256(opened.extractfile(members[0]).read()).hexdigest()
    if expected:
        require(expected["binary_sha256"] == binary_sha, "original receipt binary hash")
    return tar, dict(artifact=artifact, sha256=sha, binary_sha256=binary_sha)

def cli_version(e, binary, data, env=None):
    version = e.run(str(binary), "--version", env=env)
    metadata = re.fullmatch(r"lightr ([0-9]+\.[0-9]+\.[0-9]+) \(([0-9a-f]{7,40}), ([0-9]{4}-[0-9]{2}-[0-9]{2})\)", version)
    require(metadata and metadata[1] == data["version"] and data["candidate_sha"].startswith(metadata[2]), "version/candidate metadata mismatch")
    date.fromisoformat(metadata[3])
    data.update(binary_version=version, build_date_utc=metadata[3])

def inspect(e, binary):
    require("Mach-O 64-bit executable arm64" in e.run("file", str(binary)), "Mach-O arm64 required")
    require(e.run("lipo", "-archs", str(binary)) == "arm64", "arm64-only binary required")
    e.run("codesign", "--verify", "--strict", str(binary))
    output = e.run("codesign", "-d", "--entitlements", ":-", str(binary))
    start = output.find("<?xml")
    require(start >= 0, "missing entitlement plist")
    try:
        entitlement = plistlib.loads(output[start:].encode())
    except (plistlib.InvalidFileException, ExpatError) as error:
        raise ValueError("malformed entitlement plist") from error
    require(isinstance(entitlement, dict), "entitlement plist must be dictionary")
    require(entitlement.get("com.apple.security.virtualization") is True, "virtualization entitlement must be BOOL true")

def build():
    e = Evidence("macos-build")
    data = e.host()
    data["toolchain"] = e.run("rustc", "+1.96.0", "-vV")
    require("host: aarch64-apple-darwin" in data["toolchain"], "native toolchain required")
    data["env"] = {key: os.environ[key] for key in ("LIGHTR_NET_TESTS", "RUSTFLAGS")}
    require(data["env"]["LIGHTR_NET_TESTS"] == "1", "selected network witness requires LIGHTR_NET_TESTS=1")
    witness(e.run(*CARGO))
    data["witnesses"] = []
    for name in WITNESSES:
        argv = ["lightr-store" if arg == "lightr-oci" and name.startswith("store::") else arg for arg in CARGO]
        witness(e.run(*argv, "--", name, "--exact", "--nocapture"), name)
        data["witnesses"].append(dict(name=name, outcome="passed"))
    e.run("bash", "packaging/release.sh")
    tar, hashes = archive(e, "packaging/dist", data["version"])
    data.update(hashes, build="lightr --locked --release --features vz")
    with tempfile.TemporaryDirectory() as extracted:
        e.run("tar", "-xzf", str(tar), "-C", extracted)
        inspect(e, Path(extracted) / "lightr")
        cli_version(e, Path(extracted) / "lightr", data)
        require(digest(Path(extracted) / "lightr") == hashes["binary_sha256"], "inspection changed binary")
    sha = e.save(data)
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"receipt-sha256={sha}\nartifact-path=packaging/dist/{hashes['artifact']}\nchecksum-path=packaging/dist/{hashes['artifact']}.sha256\n")

def install():
    e = Evidence("macos-install")
    data = e.host()
    require(re.fullmatch("[1-9][0-9]*", os.environ["ARTIFACT_ID"]), "missing immutable artifact ID")
    receipt = Path("candidate/macos-build/receipt.json")
    require(digest(receipt) == os.environ["RECEIPT_SHA256"], "original receipt hash")
    original = json.loads(receipt.read_text())
    require(original["candidate_sha"] == original["workflow_sha"] == data["candidate_sha"], "receipt candidate identity")
    tar, hashes = archive(e, "candidate/packaging/dist", data["version"], original)
    home = Path(tempfile.mkdtemp(dir=e.path)).resolve()
    try:
        env = dict(os.environ, HOME=str(home), LIGHTR_HOME=str(home / ".lightr"))
        for key in ("LIGHTR_STORE_DIR", "LIGHTR_LINUX_PACK"):
            env.pop(key, None)
        e.run("tar", "-xzf", str(tar), "-C", str(home))
        inspect(e, home / "lightr")
        destination = home / ".local/bin/lightr"
        destination.parent.mkdir(parents=True)
        e.run("install", "-m", "755", str(home / "lightr"), str(destination))
        require(digest(destination) == hashes["binary_sha256"], "installed binary hash")
        cli_version(e, destination, data, env=env)
        require(all(data[key] == original[key] for key in ("binary_version", "build_date_utc")), "original receipt CLI metadata")
        require(e.run(str(destination), "--help", env=env), "empty help smoke output")
    finally:
        e.run("rm", "-rf", str(home))
    require(not home.exists(), "fresh HOME cleanup failed")
    data.update(hashes, source=os.environ["ARTIFACT_SOURCE"], artifact_id=os.environ["ARTIFACT_ID"],
                build_receipt_sha256=digest(receipt), cleanup="fresh HOME removed")
    e.save(data)

if __name__ == "__main__":
    {"build": build, "install": install}[sys.argv[1]]()
