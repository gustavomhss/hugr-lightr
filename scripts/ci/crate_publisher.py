"""Frozen serial publisher; prepackage before writes, no Cargo retries or promotion.
Official action owns OIDC mint/revoke. Bootstrap presence is not scope proof.
"""
import json
import os
from pathlib import Path
import shlex
import sys
import tomllib
import crate_publish_io as io
import trusted_publishing_readiness as t

OUTPUT = Path("crate-publication")
ORDER = tuple("lightr-core lightr-init lightr-store lightr-index lightr-oci lightr-views lightr-engine lightr-run hugr-lightr-cri-backend lightr-build hugr-lightr".split())
BOOTSTRAP = {"hugr-lightr-cri-backend", "hugr-lightr"}
CONTINUATION = "remaining-after-36951118620"
PREFIX_FILE = Path(__file__).resolve().parents[2] / "packaging/crate-publication-0.1.1-prefix.json"
PREFIX_SHA256 = "6d69cf4ec1cb97180e550ecf01af500730dea11a815e2924d3d043b78ecbe3d6"
require = t.require


def load_prefix():
    try:
        body = PREFIX_FILE.read_bytes()
    except OSError:
        raise t.ReadinessError("prefix evidence missing/unreadable") from None
    require(io.hashlib.sha256(body).hexdigest() == PREFIX_SHA256, "prefix evidence content hash mismatch")
    try:
        data = json.loads(body)
        require(set(data) == {"source", "version", "failed_run", "authority", "crates"}, "prefix evidence fields mismatch")
        require(data["source"] == t.SOURCE, "prefix source mismatch")
        require(data["version"] == "0.1.1" and type(data["failed_run"]) is int and data["failed_run"] == 36951118620,
                "prefix version/run mismatch")
        require(data["authority"] == "https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5944066332", "prefix authority mismatch")
        require(isinstance(data["crates"], list) and len(data["crates"]) == 5, "prefix count mismatch")
        for position, row in enumerate(data["crates"], 1):
            require(set(row) == {"position", "name", "checksum"} and type(row["position"]) is int and
                    row["position"] == position and row["name"] == ORDER[position - 1], "prefix order/name/position mismatch")
            require(isinstance(row["checksum"], str) and io.re.fullmatch(r"[0-9a-f]{64}", row["checksum"]), "prefix checksum malformed")
    except t.ReadinessError:
        raise
    except (ValueError, TypeError, KeyError):
        raise t.ReadinessError("prefix evidence JSON malformed") from None
    return data


def snapshot():
    def read(path):
        return tomllib.loads(t.git("show", t.SOURCE + ":" + path))
    root = read("Cargo.toml")["workspace"]
    require(root["package"]["version"] == "0.1.1" and root["package"]["license"] == "Apache-2.0" and
            root["package"]["publish"] is True, "workspace release policy mismatch")
    members, packages = root["members"], {}
    require(isinstance(members, list) and members and len(members) == len(set(members)), "workspace members missing/duplicate")
    for member in members:
        package = read(member + "/Cargo.toml")["package"]
        fields = {k: root["package"][k] if package[k] == {"workspace": True} else package[k] for k in ("version", "license", "publish")}
        name = package["name"]
        require(name not in packages, "duplicate package name")
        if name == "lightr-acceptance":
            require(fields["publish"] is False, "acceptance must remain unpublished")
        else:
            require(fields == dict(version="0.1.1", license="Apache-2.0", publish=True), "member release policy mismatch")
        packages[name] = dict(path=member, **fields)
    require("lightr-acceptance" in packages and "crates/lightr-cri-serve" in root["exclude"], "excluded package missing")
    require(read("crates/lightr-cri-serve/Cargo.toml")["package"]["publish"] is False and
            read("crates/lightr-cri/Cargo.toml")["workspace"]["package"]["publish"] is False, "CRI exclusion policy mismatch")
    require(len(ORDER) == 11 and len(set(ORDER)) == 11, "publication order duplicate/count mismatch")
    require(set(ORDER) == {n for n, p in packages.items() if p["publish"] is True}, "publication order omission/extra mismatch")
    runbook = t.git("show", t.SOURCE + ":docs/RELEASE.md").split("## Crates.io Order\n")[1].split("## Owner Publish Order\n")[0]
    commands = runbook.split("```sh\n")[1].split("```")[0].splitlines()
    require([shlex.split(line) for line in commands] == [["cargo", "publish", "-p", n] for n in ORDER], "frozen publication order mismatch")
    return packages


def accepted(env):
    data = t.identity(env)
    require(data["source"] != data["verifier"], "publisher must be distinct from product source")
    continuation = env.get("CONTINUATION", "")
    require(continuation in ("", CONTINUATION), "unknown continuation forbidden")
    authorization = "continue-0.1.1-after-36951118620" if continuation else "publish-0.1.1"
    require(env.get("UPLOAD_AUTHORIZATION") == authorization, "explicit upload authorization required")
    require(bool(env.get("BOOTSTRAP_TOKEN", "").strip()), "bootstrap credential required; scope unknown")
    result = {k: data[k] for k in ("source", "verifier", "release_tag", "version", "repository")} | dict(packages=snapshot(), order=list(ORDER))
    if continuation:
        result.update(continuation=continuation, prefix=load_prefix())
    return result


def absent(prefix=None):
    observations = {}
    prior = {row["name"]: row for row in (prefix or {}).get("crates", [])}
    for name in ORDER:
        if name in prior:
            version = io.registry(name, "0.1.1")
            require(version["state"] == "existing" and version["checksum"] == prior[name]["checksum"] and
                    version["yanked"] is False, "prefix registry checksum/yank/state mismatch: " + name)
            observations[name] = dict(version=version)
            continue
        control = io.registry(name, None if name in BOOTSTRAP else "0.1.0")
        require(control["state"] == ("absent" if name in BOOTSTRAP else "existing"), "registry positive/new-name control failed")
        observations[name] = dict(control=control, version=io.registry(name, "0.1.1"))
        require(observations[name]["version"]["state"] == "absent", "0.1.1 already exists; batch forbidden")
    return observations


def clean(product):
    require(t.git("-C", str(product), "rev-parse", "HEAD") == t.SOURCE and
            not t.git("-C", str(product), "status", "--porcelain", "--untracked-files=normal"), "product HEAD mismatch/worktree dirty")


def publish_one(row, ledger, product, env):
    name = row["name"]
    row["package_command"] = io.cargo(OUTPUT, product, name, "package", env)
    io.write(OUTPUT, "ledger.json", ledger, env)
    require(row["package_command"]["exit"] == 0, "Cargo package failed; zero upload for this crate")
    prepared = io.archive_path(OUTPUT, name)
    row["prepackage_sha256"] = io.package_sha(prepared)
    io.verify_archive(prepared, name, t.SOURCE)
    clean(product)
    scratch = io.archive_path(OUTPUT, name, publish=True)
    scratch.unlink(missing_ok=True)  # Prepackage scratch cannot masquerade as publish's bytes.
    io.write(OUTPUT, "ledger.json", ledger, env)
    if row["position"] == 6 and "prefix" in ledger["identity"]:
        absent(ledger["identity"]["prefix"])  # Recheck after potentially slow verification, before first upload.
    row["publish_command"] = io.cargo(OUTPUT, product, name, "publish", env,
                                     "BOOTSTRAP_TOKEN" if row["authpath"] == "REGULAR" else "TP_TOKEN")
    row["exit"] = row["publish_command"]["exit"]
    io.write(OUTPUT, "ledger.json", ledger, env)
    verified = False
    try:
        row["package_sha256"] = io.package_sha(scratch)
        io.verify_archive(scratch, name, t.SOURCE)
        clean(product)
        verified = True
    finally:
        io.observe(row, poll=row["exit"] == 0 and verified)
    require(row["exit"] == 0, "Cargo nonzero/spawn failure; batch halted")
    require(row["package_sha256"] == row["prepackage_sha256"], "publish/prepackage checksum changed; batch halted")
    row["state"] = "PUBLISHED"


def main(argv=None, env=None):
    argv, env = sys.argv[1:] if argv is None else argv, os.environ if env is None else env
    ledger = None
    try:
        require(argv in (["preflight"], ["publish"]), "preflight or publish command required")
        data = accepted(env)
        OUTPUT.mkdir(exist_ok=True)
        output, product = OUTPUT.resolve(), OUTPUT.resolve() / "product"
        require(not (OUTPUT / "ledger.json").exists(), "batch already started; automatic resume/reupload forbidden")
        if argv == ["preflight"]:
            (OUTPUT / "preflight.json").unlink(missing_ok=True)
            observations = absent(data.get("prefix"))
            require(not product.exists(), "preflight product worktree already exists")
            t.git("worktree", "add", "--detach", str(product), t.SOURCE)
            clean(product)
            io.write(OUTPUT, "preflight.json", dict(identity=data, observations=observations, bootstrap_scope="UNKNOWN; presence only"), env)
        else:
            require((OUTPUT / "preflight.json").is_file(), "preflight metadata missing")
            require(json.loads((OUTPUT / "preflight.json").read_text()).get("identity") == data, "preflight snapshot mismatch")
            require(bool(env.get("TP_TOKEN", "").strip()), "OIDC credential required")
            clean(product)
            observations = absent(data.get("prefix"))
            require(json.loads((OUTPUT / "preflight.json").read_text()) == dict(identity=data, observations=observations, bootstrap_scope="UNKNOWN; presence only"), "registry preflight observation mismatch")
            for directory in ("home", "cargo", "target", "build"):
                (output / directory).mkdir()
            ledger = dict(identity=data, state="STARTED", crates=[])
            if "prefix" in data:
                for prior in data["prefix"]["crates"]:
                    ledger["crates"].append(dict(position=prior["position"], name=prior["name"], state="VERIFIED_PRIOR",
                                                 original_run=data["prefix"]["failed_run"], authority=data["prefix"]["authority"],
                                                 package_sha256=prior["checksum"], remote=observations[prior["name"]]["version"]))
            io.write(OUTPUT, "ledger.json", ledger, env)
            start = 6 if "prefix" in data else 1
            for position, name in enumerate(ORDER[start - 1:], start):
                clean(product)
                row = dict(position=position, name=name, authpath="REGULAR" if name in BOOTSTRAP else "OIDC", exit=None, remote=dict(state="unknown"))
                ledger["crates"].append(row)
                io.write(OUTPUT, "ledger.json", ledger, env)
                publish_one(row, ledger, product, env)
                io.write(OUTPUT, "ledger.json", ledger, env)
            for row in ledger["crates"]:
                io.observe(row, poll=True)
            clean(product)
            ledger["state"] = "COMPLETE"
            io.write(OUTPUT, "ledger.json", ledger, env)
            io.write(OUTPUT, "receipt.json", ledger, env)
    except Exception as error:
        message = io.redact(str(error) if isinstance(error, t.ReadinessError) else "publication failed; details suppressed", env)
        print("FAIL: " + message, file=sys.stderr)
        try:
            if ledger is not None:
                ledger.update(state="PARTIAL_FAILED", error=message)
                io.write(OUTPUT, "ledger.json", ledger, env)
            io.write(OUTPUT, "failure.json", dict(state="FAIL", error=message), env)
        except OSError:
            pass
        return 1
    print("preflight READY" if argv == ["preflight"] else "eleven crate checksums verified; batch COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
