"""Auth-only evidence. Token scope requires external readback, not opaque-token introspection."""
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request

SOURCE = "47f02795d0884956c4755254b5f6fc377a5938b5"
REPO = "gmhelmold/hugr-lightr"
ENDPOINT = "https://crates.io/api/v1/trusted_publishing/tokens"
OUTPUT = Path("trusted-publishing-readiness")

class ReadinessError(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise ReadinessError(message)

def git(*args):
    # No token inherited by subprocesses; Git diagnostics never enter evidence.
    env = dict(PATH=os.environ["PATH"], LC_ALL="C", GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL=os.devnull)
    return subprocess.run(["git", *args], env=env, check=True, timeout=15,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout.strip()

def identity(env):
    candidate, tag, verifier = [env.get(k, "") for k in ("CANDIDATE_SHA", "RELEASE_TAG", "VERIFIER_SHA")]
    require(re.fullmatch(r"[0-9a-f]{40}", candidate), "lowercase candidate SHA required")
    require(candidate == SOURCE, "frozen candidate mismatch")
    require(re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag), "release tag required")
    require(env.get("GITHUB_REPOSITORY") == REPO, "repository mismatch")
    require(env.get("GITHUB_EVENT_NAME") == "workflow_dispatch", "manual event required")
    require(re.fullmatch(r"[0-9a-f]{40}", verifier) and verifier == env.get("GITHUB_SHA") and
            git("rev-parse", "HEAD") == verifier, "verifier checkout identity mismatch")
    ref = "refs/tags/" + tag
    require(git("cat-file", "-t", ref) == "tag", "annotated tag required")
    require(git("rev-parse", ref + "^{commit}") == candidate, "tag candidate mismatch")
    version = tomllib.loads(git("show", candidate + ":Cargo.toml"))["workspace"]["package"]["version"]
    require(version == "0.1.1" and tag == "v" + version, "pinned Cargo/tag version mismatch")
    return dict(state="READY", source=candidate, verifier=verifier, release_tag=tag,
                version=version, repository=REPO, python=platform.python_version(), git=git("--version"),
                runner={k: env.get(k, "") for k in ("RUNNER_OS", "RUNNER_ARCH", "ImageOS", "ImageVersion",
                                                  "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")})

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        fp.close()
        raise ReadinessError("revocation redirect forbidden")

def revoke(token):
    request = urllib.request.Request(ENDPOINT, method="DELETE", headers={"Authorization": "Bearer " + token})
    try:
        # Disable ambient proxies and redirects; never read/log response bodies or headers.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=30) as response:
            status = response.status
    except ReadinessError:
        raise
    except urllib.error.HTTPError as error:
        error.close()
        raise ReadinessError("token revocation request failed") from None
    except Exception:
        raise ReadinessError("token revocation request failed") from None
    require(status == 204, "revocation status must be 204")
    return status

def write(name, data):
    temporary = OUTPUT / (name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(OUTPUT / name)

def main(argv=None, env=None):
    argv, env = sys.argv[1:] if argv is None else argv, os.environ if env is None else env
    try:
        OUTPUT.mkdir(exist_ok=True)
        (OUTPUT / "receipt.json").unlink(missing_ok=True)
        (OUTPUT / "failure.json").unlink(missing_ok=True)
        require(argv in (["preflight"], ["revoke"]), "preflight or revoke command required")
        if argv == ["preflight"]:
            (OUTPUT / "preflight.json").unlink(missing_ok=True)
        data = identity(env)
        if argv == ["preflight"]:
            require(not env.get("TP_TOKEN"), "preflight must be credential-free")
            write("preflight.json", data)
        else:
            require((OUTPUT / "preflight.json").is_file(), "preflight metadata missing")
            require(json.loads((OUTPUT / "preflight.json").read_text()) == data, "preflight metadata mismatch")
            token = env.get("TP_TOKEN", "")
            require(isinstance(token, str) and bool(token.strip()), "minted token required")
            status = revoke(token)
            data.update(minted=True, revocation_status=status, publication="NOT EXECUTED",
                        bootstrap_new_crates={n: "pending: manual first publication required" for n in
                                              ("hugr-lightr", "hugr-lightr-cri-backend")},
                         configuration_readback="LEAD offline before/after; not checked here",
                        scope="at least 1 match: action exchange succeeds; scope based on external config readback; no exact token allowlist introspection")
            write("receipt.json", data)
    except Exception as error:
        message = str(error) if isinstance(error, ReadinessError) else "readiness failed; details suppressed"
        print("FAIL: " + message, file=sys.stderr)
        try:
            write("failure.json", dict(state="FAIL", error=message))
        except OSError:
            pass
        return 1
    print("preflight READY" if argv == ["preflight"] else "auth-only proof recorded; publication NOT EXECUTED")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
