"""Credential-isolated Cargo 1.96 IO and public crates.io checksum observations.
Archive layout: rust-lang/cargo@30a34c682 src/cargo/ops/cargo_package/mod.rs
and src/cargo/ops/registry/publish.rs; exercised by real-Cargo conformance test.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import time
import tomllib
import urllib.error
import urllib.request
from trusted_publishing_readiness import ReadinessError, require

ORIGIN = "https://crates.io/api/v1/crates/"
LIMIT = 1024 * 1024
TOKEN_KEYS = ("TP_TOKEN", "BOOTSTRAP_TOKEN", "GH_TOKEN", "GITHUB_TOKEN",
              "GH_RUNTIME_TOKEN", "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN")


def redact(text, env):
    for token in sorted({env.get(k, "") for k in TOKEN_KEYS} - {""}, key=len, reverse=True):
        text = text.replace(token, "[REDACTED]")
    return text


def safe(value, env):
    if isinstance(value, str):
        return redact(value, env)
    if isinstance(value, (list, tuple)):
        return [safe(v, env) for v in value]
    if isinstance(value, dict):
        return {redact(k, env): safe(v, env) for k, v in value.items()}
    return value


def write(output, name, value, env):
    temporary = output / (name + ".tmp")
    temporary.write_text(json.dumps(safe(value, env), indent=2) + "\n")
    temporary.replace(output / name)


def child_env(output, env, token_key=None):
    output = output.resolve()
    child = dict(PATH=env["PATH"], RUSTUP_HOME=env.get("RUSTUP_HOME") or str(Path(env["HOME"]) / ".rustup"),
                 HOME=str(output / "home"), CARGO_HOME=str(output / "cargo"),
                 CARGO_TARGET_DIR=str(output / "target"), CARGO_BUILD_BUILD_DIR=str(output / "build"), LC_ALL="C",
                 CARGO_HTTP_MULTIPLEXING="false",
                 CARGO_REGISTRY_GLOBAL_CREDENTIAL_PROVIDERS="cargo:token", CARGO_REGISTRY_CREDENTIAL_PROVIDER="cargo:token")
    if token_key is not None:
        require(token_key in ("TP_TOKEN", "BOOTSTRAP_TOKEN"), "Cargo credential selector forbidden")
        require(bool(env.get(token_key, "").strip()), "selected Cargo credential missing")
        child["CARGO_REGISTRY_TOKEN"] = env[token_key]
    return child


def archive_path(output, name, publish=False):
    require(re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name), "crate archive name forbidden")
    directory = "build/package/tmp-crate" if publish else "target/package"
    return output / directory / (name + "-0.1.1.crate")


def package_sha(path):
    require(path.is_file() and not path.is_symlink(), "local crate package missing")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_archive(path, name, source):
    with tarfile.open(path, "r:gz") as archive:
        members, seen = archive.getmembers(), set()
        root = name + "-0.1.1"
        for member in members:
            parts = member.name.split("/")
            require(parts[0] == root and all(p and p not in (".", "..") for p in parts) and
                    "\\" not in member.name, "package member path forbidden")
            require(member.name not in seen, "duplicate package member")
            require(member.type in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE) and
                    (member.name != root or member.isdir()), "package member type/link forbidden")
            seen.add(member.name)
        def read(file):
            matches = [m for m in members if m.name == root + "/" + file]
            require(len(matches) == 1 and matches[0].isfile() and matches[0].size <= LIMIT,
                    "package metadata missing/invalid: " + file)
            return archive.extractfile(matches[0]).read().decode()
        vcs = json.loads(read(".cargo_vcs_info.json"))["git"]
        require(vcs.get("sha1") == source and vcs.get("dirty", False) is False, "package git source/dirty mismatch")
        manifest = tomllib.loads(read("Cargo.toml"))["package"]
        require([manifest.get(k) for k in ("name", "version")] == [name, "0.1.1"], "normalized package name/version mismatch")
        require(manifest.get("license") == "Apache-2.0", "package license mismatch")


def cargo(output, product, name, phase, env, token_key=None, dry_run=False, offline=False):
    require(phase in ("package", "publish"), "Cargo phase forbidden")
    require(token_key is None or (phase == "publish" and not dry_run), "package/dry-run must be credential-free")
    archive_path(output, name)
    argv = ["cargo", "+1.96.0", phase, "--locked", "--registry", "crates-io", "--manifest-path", str(product / "Cargo.toml"), "-p", name]
    if dry_run:
        require(phase == "publish" and token_key is None, "credential-free publish dry-run required")
        argv.append("--dry-run")
    if offline:
        argv.append("--offline")
    row = dict(argv=argv, exit=None, log=f"{name}-{phase}.log")
    try:
        result = subprocess.run(argv, cwd=product, env=child_env(output, env, token_key), capture_output=True)
        row["exit"] = result.returncode
        text = redact((result.stdout + result.stderr).decode(errors="replace"), env)
    except OSError:
        text = "Cargo spawn failed; details suppressed"
    (output / row["log"]).write_text(text)
    print(text, end="", flush=True)
    return row


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        fp.close()
        raise ReadinessError("registry redirect forbidden")


def registry(name, version=None):
    require(re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name) and version in (None, "0.1.0", "0.1.1"), "registry query forbidden")
    url = ORIGIN + name + ("/" + version if version else "")
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "lightr-crate-publisher/0.1.1"})
        try:
            with opener.open(request, timeout=10) as response:
                require(response.geturl() == url, "registry response identity mismatch")
                status, body = response.status, response.read(LIMIT + 1)
        except urllib.error.HTTPError as error:
            with error:
                status, body = error.code, error.read(LIMIT + 1)
        require(status in (200, 404), "registry HTTP failure")
        require(0 < len(body) <= LIMIT, "registry response size invalid")
        payload = json.loads(body)
        if status == 404:
            require(isinstance(payload.get("errors"), list) and payload["errors"] and all(isinstance(e, dict) and isinstance(e.get("detail"), str) and e["detail"] for e in payload["errors"]), "registry absence JSON malformed")
            return dict(state="absent", url=url)
        value = payload["version" if version else "crate"]
        require(isinstance(value, dict), "registry JSON object required")
        if version:
            require(value.get("crate") == name and value.get("num") == version and
                    isinstance(value.get("checksum"), str) and
                    re.fullmatch(r"[0-9a-f]{64}", value.get("checksum", "")) and
                    type(value.get("yanked")) is bool, "registry version/checksum malformed")
            return dict(state="existing", url=url, checksum=value["checksum"], yanked=value["yanked"])
        require(value.get("id") == name, "registry crate identity mismatch")
        return dict(state="existing", url=url)
    except ReadinessError:
        raise
    except Exception:
        raise ReadinessError("registry network/JSON failure") from None


def observe(row, poll=False):
    deadline = time.monotonic() + (120 if poll else 0)
    while True:
        row["remote"] = registry(row["name"], "0.1.1")
        if row["remote"]["state"] == "existing" or not poll or time.monotonic() >= deadline:
            break
        time.sleep(min(5, max(0, deadline - time.monotonic())))
    if poll:
        require(row["remote"]["state"] == "existing", "index visibility unavailable after bounded wait")
        require(row["remote"]["checksum"] == row["package_sha256"] and not row["remote"]["yanked"], "registry package checksum/yank mismatch")
