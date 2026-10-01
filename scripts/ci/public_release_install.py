"""Read-only public-output verification; verifier revision is not product source."""
import base64
import io
import json
import os
from pathlib import Path
import re
import tarfile
import tempfile
import tomllib
import zipfile
from macos_candidate import require, digest, inspect, cli_version
from public_release_transport import Api, PublicEvidence, REPO, LIMIT, sha

STEPS = ["Checkout", "Verify owner-selected candidate and tag", "Build release binary",
         "Package tarball and checksum", "Upload build artifact"]
ASSEMBLY_STEPS = ["Download Unix-first artifacts", "Assemble SHA256SUMS", "Create draft release"]

def elf(header):
    require(len(header) == 64 and header[:7] == b"\x7fELF\x02\x01\x01" and
            int.from_bytes(header[18:20], "little") == 62 and int.from_bytes(header[16:18], "little") in (2, 3),
            "ELF64 little-endian x86_64 required")

def listing(api, endpoint, key):
    data = api.get(endpoint)
    rows = data.get(key)
    require(isinstance(rows, list) and rows and len(rows) == data.get("total_count"), f"missing/empty/truncated {key}")
    require(all(isinstance(row, dict) for row in rows), f"malformed {key}")
    return rows

def identity(row, label):
    value = row.get("id")
    require(type(value) is int and value > 0, f"immutable {label} ID required")
    return value

def verify(e, api, env):
    run, release_id, candidate, tag, target, verifier = [env.get(k, "") for k in
        ("PUBLIC_RELEASE_RUN_ID", "PUBLIC_RELEASE_ID", "CANDIDATE_SHA", "RELEASE_TAG", "PUBLIC_RELEASE_TARGET", "VERIFIER_SHA")]
    require(re.fullmatch(r"[1-9][0-9]*", run), "positive producer run ID required")
    require(re.fullmatch(r"[1-9][0-9]*", release_id), "positive release ID required")
    require(re.fullmatch(r"[0-9a-f]{40}", candidate), "candidate SHA required")
    require(re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag), "release tag required")
    require(target in ("linux-x86_64", "darwin-arm64"), "public target required")
    require(env.get("GITHUB_REPOSITORY") == REPO and env.get("GH_TOKEN"), "repository/token required")
    require(re.fullmatch(r"[0-9a-f]{40}", verifier) and verifier == env.get("GITHUB_SHA") and
            e.run("git", "rev-parse", "HEAD") == verifier, "verification checkout identity")
    mac = target == "darwin-arm64"
    host = dict(os=e.run("uname", "-s"), arch=e.run("uname", "-m"), platform=e.run("uname", "-a"))
    require((host["os"], host["arch"]) == (("Darwin", "arm64") if mac else ("Linux", "x86_64")), "native target required")
    if mac:
        require(e.run("sysctl", "-n", "hw.optional.arm64") == "1", "arm64 capability required")
        host.update(model=e.run("sysctl", "-n", "hw.model"), version=e.run("sw_vers"))
    producer = api.get(f"actions/runs/{run}")
    require(producer.get("id") == int(run) and producer.get("path") == ".github/workflows/release.yml" and
            producer.get("workflow_id") == 299070533 and producer.get("event") == "workflow_dispatch" and
            producer.get("head_sha") == candidate and producer.get("status") == "completed" and
            producer.get("conclusion") == "success" and type(producer.get("run_attempt")) is int and producer["run_attempt"] > 0, "producer run identity/success")
    jobs = listing(api, f"actions/runs/{run}/jobs?per_page=100", "jobs")
    names = ["build (darwin-arm64)", "build (linux-x86_64)", "assemble draft GitHub Release"]
    require(all(isinstance(j.get("name"), str) for j in jobs) and sorted(j["name"] for j in jobs) == sorted(names) and
            all(j.get("status") == "completed" and j.get("conclusion") == "success" for j in jobs), "producer jobs exact/success")
    for job in jobs:
        steps = job.get("steps")
        require(isinstance(steps, list) and steps and all(isinstance(s, dict) for s in steps), f"missing/empty producer steps or malformed producer step rows: {job['name']}")
        required = ASSEMBLY_STEPS if job["name"] == names[2] else STEPS + (["Sign and notarize (macOS)"] if job["name"] == names[0] else [])
        for name in required:
            matches = [s for s in steps if s.get("name") == name]
            require(len(matches) == 1 and matches[0].get("status") == "completed" and matches[0].get("conclusion") == "success", f"producer step required: {job['name']}: {name}")
    cargo = api.get(f"contents/Cargo.toml?ref={candidate}")
    try:
        require(cargo.get("encoding") == "base64", "pinned Cargo encoding")
        require(isinstance(cargo["content"], str), "pinned Cargo version malformed")
        content = cargo["content"].replace("\r\n", "\n").replace("\n", "")  # GitHub base64 LF/CRLF wrapping only.
        version = tomllib.loads(base64.b64decode(content, validate=True).decode())["workspace"]["package"]["version"]
    except (KeyError, ValueError, UnicodeError, TypeError) as error:
        raise ValueError("pinned Cargo version malformed") from error
    require(tag == f"v{version}", "pinned Cargo/tag version mismatch")
    ref = api.get(f"git/ref/tags/{tag}").get("object", {})
    require(ref.get("type") == "tag" and re.fullmatch(r"[0-9a-f]{40}", ref.get("sha", "")), "annotated tag required")
    annotated = api.get(f"git/tags/{ref['sha']}")
    require(annotated.get("tag") == tag and annotated.get("object", {}).get("type") == "commit" and annotated.get("object", {}).get("sha") == candidate, "annotated tag candidate mismatch")
    release = api.get(f"releases/{release_id}")
    require(identity(release, "release") == int(release_id) and release.get("draft") is True and release.get("tag_name") == tag, "draft release ID/tag required")
    assets = release.get("assets")
    require(isinstance(assets, list) and assets and all(isinstance(a, dict) and isinstance(a.get("name"), str) for a in assets), "missing/empty release assets or malformed release asset rows")
    linux = f"lightr-{version}-linux-x86_64.tar.gz"
    macnames = [f"lightr-{version}-darwin-arm64{suffix}.tar.gz" for suffix in ("", "-unsigned")]
    macfiles = [a.get("name") for a in assets if a.get("name") in macnames]
    require(len(macfiles) == 1, "exact macOS asset required")
    filenames = [linux, macfiles[0]]
    require(sorted(a.get("name", "") for a in assets) == sorted(filenames + [n + ".sha256" for n in filenames] + ["SHA256SUMS"]), "exact five release assets required")
    ids = [identity(a, "asset") for a in assets]
    require(len(set(ids)) == 5, "duplicate asset IDs")
    artifact_rows = listing(api, f"actions/runs/{run}/artifacts?per_page=100", "artifacts")
    matches = [a for a in artifact_rows if a.get("name") == f"release-{target}"]
    require(len(matches) == 1, "exact producer artifact required")
    artifact = matches[0]; aid = identity(artifact, "artifact")
    require(artifact.get("expired") is False and artifact.get("workflow_run", {}).get("id") == int(run) and
            artifact.get("workflow_run", {}).get("head_sha") == candidate, "producer artifact identity/expiry")
    require(type(artifact.get("size_in_bytes")) is int and 0 < artifact["size_in_bytes"] <= LIMIT, "artifact size bounded")
    packed = api.get(f"actions/artifacts/{aid}/zip", True)
    require(artifact.get("digest") == f"sha256:{sha(packed)}", "producer ZIP digest mismatch")
    filename = filenames[1 if mac else 0]
    with zipfile.ZipFile(io.BytesIO(packed)) as opened:
        entries = opened.infolist()
        require(sorted(z.filename for z in entries) == sorted([filename, filename + ".sha256"]) and
                all(not z.is_dir() and z.file_size <= LIMIT for z in entries), "producer ZIP exact files/bounds")
        pair = {z.filename: opened.read(z) for z in entries}
    downloaded, evidence = {}, []
    for name in (filename, filename + ".sha256", "SHA256SUMS"):
        asset = next(a for a in assets if a["name"] == name); asset_id = identity(asset, "asset")
        require(type(asset.get("size")) is int and 0 < asset["size"] <= LIMIT, "asset size bounded")
        body = api.get(f"releases/assets/{asset_id}", True)
        require(len(body) == asset["size"] and (asset.get("digest") is None or asset["digest"] == f"sha256:{sha(body)}"), "release asset size/digest mismatch")
        if name != "SHA256SUMS":
            require(body == pair[name], "release/producer bytes mismatch")
        downloaded[name] = body
        evidence.append(dict(id=asset_id, name=name, url=f"https://api.github.com/repos/{REPO}/releases/assets/{asset_id}", sha256=sha(body)))
    sums = downloaded["SHA256SUMS"].decode("ascii").splitlines(keepends=True)
    records = [re.fullmatch(r"([0-9a-f]{64})  (lightr-[^\n]+\.tar\.gz)\n", line) for line in sums]
    require(len(records) == 2 and all(records) and sorted(r[2] for r in records) == sorted(filenames), "aggregate exact canonical records")
    archive_sha = sha(downloaded[filename])
    require(next(r[1] for r in records if r[2] == filename) == archive_sha, "aggregate target hash mismatch")
    require(downloaded[filename + ".sha256"] == f"{archive_sha}  {filename}\n".encode(), "checksum record/filename")
    tar = e.path / filename; tar.write_bytes(downloaded[filename])
    Path(str(tar) + ".sha256").write_bytes(downloaded[filename + ".sha256"])
    e.run(*(["shasum", "-a", "256"] if mac else ["sha256sum"]), "-c", filename + ".sha256", cwd=e.path)
    with tarfile.open(tar) as opened:
        members = opened.getmembers()
        require(len(members) == 1 and members[0].name == "lightr" and members[0].isfile() and members[0].mode == 0o755 and members[0].size <= LIMIT, "tar must contain only regular executable lightr")
        binary_sha = sha(opened.extractfile(members[0]).read())
    data = dict(version=version, candidate_sha=candidate, compiled_source=candidate, producer_workflow_sha=candidate,
                verification_workflow_sha=verifier, target=target, native_host=host,
                runner={k: env.get(k) for k in ("RUNNER_OS", "RUNNER_ARCH", "ImageOS", "ImageVersion", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")},
                producer_run=dict(id=int(run), run_attempt=producer["run_attempt"], url=f"https://github.com/{REPO}/actions/runs/{run}"),
                jobs=[dict(id=identity(j, "job"), name=j["name"], url=f"https://github.com/{REPO}/actions/runs/{run}/job/{j['id']}") for j in jobs],
                artifact=dict(id=aid, url=f"https://api.github.com/repos/{REPO}/actions/artifacts/{aid}/zip", zip_sha256=sha(packed), api_digest=artifact["digest"]),
                release_id=identity(release, "release"), release_assets=[dict(id=a["id"], name=a["name"], url=f"https://api.github.com/repos/{REPO}/releases/assets/{a['id']}") for a in assets], assets=evidence, archive_sha256=archive_sha, binary_sha256=binary_sha,
                checksum_sha256=sha(downloaded[filename + ".sha256"]), aggregate_sha256=sha(downloaded["SHA256SUMS"]), vz_boot="NOT EXECUTED")
    home = Path(tempfile.mkdtemp(prefix="fresh-home-", dir=e.path))
    try:
        clean_env = dict(PATH=os.environ["PATH"], HOME=str(home), LC_ALL="C")
        e.run("tar", "-xzf", str(tar), "-C", str(home))
        binary = home / "lightr"
        if mac:
            inspect(e, binary)
            signing = e.run("codesign", "-dv", "--verbose=4", str(binary))
            require(("Signature=adhoc" in signing) == filename.endswith("-unsigned.tar.gz"), "signing filename mismatch")
            require("Signature=adhoc" in signing or "Authority=Developer ID Application" in signing, "Developer ID signing required")
            data["signing"] = "unsigned (ad-hoc; no Developer ID; not notarized)" if "Signature=adhoc" in signing else "Developer ID; notarization acceptance not independently verified"
        else:
            with binary.open("rb") as opened:
                elf(opened.read(64))
            data["signing"] = "unsigned"
        destination = home / ".local/bin/lightr"; destination.parent.mkdir(parents=True)
        e.run("install", "-m", "755", str(binary), str(destination))
        require(digest(destination) == binary_sha, "installed binary hash before smoke")
        cli_version(e, destination, data, env=clean_env)
        require("Usage:" in e.run(str(destination), "--help", env=clean_env), "help Usage required")
        require(digest(destination) == binary_sha, "installed binary hash after smoke")
    finally:
        e.run("rm", "-rf", str(home))
        require(not os.path.lexists(home), "fresh HOME cleanup failed")
    data.update(cleanup="fresh HOME removed", commands=e.commands)
    (e.path / "receipt.json").write_text(json.dumps(data, indent=2) + "\n")
    return data

if __name__ == "__main__":
    evidence = PublicEvidence("public-release-install")
    verify(evidence, Api(evidence, os.environ.get("GH_TOKEN", "")), os.environ)
