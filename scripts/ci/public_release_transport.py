"""Fixed-repository GET transport and credential-isolated, redacted command evidence."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from macos_candidate import require

REPO = "gusmhs/hugr-lightr"
LIMIT = 128 * 1024 * 1024  # Post-capture size check, not a streaming memory bound.

def sha(body):
    return hashlib.sha256(body).hexdigest()

class PublicEvidence:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.mkdir()
        self.commands, self.tokens = [], set()
        self.home, self.tmp = self.path / "command-home", self.path / "tmp"
        self.home.mkdir()
        self.tmp.mkdir()
        (self.path / "commands.json").write_text("[]\n")

    def redact(self, body):
        tokens = self.tokens | {os.environ.get(k, "") for k in ("GH_TOKEN", "GITHUB_TOKEN")}
        for token in sorted(tokens - {""}, key=len, reverse=True):
            body = body.replace(token.encode(), b"[REDACTED]")
        return body

    def safe(self, value):
        if isinstance(value, str):
            return self.redact(value.encode()).decode()
        if isinstance(value, list):
            return [self.safe(v) for v in value]
        if isinstance(value, dict):
            return {k: self.safe(v) for k, v in value.items()}
        return value

    def record(self, row):
        self.commands.append(self.safe(row))
        (self.path / "commands.json").write_text(json.dumps(self.commands, indent=2))

    def run(self, *argv, cwd=None, env=None):
        home = Path((env or {}).get("HOME", self.home)).resolve()
        require(home.is_relative_to(self.path), "child HOME must be inside evidence directory")
        child_env = dict(PATH=os.environ["PATH"], HOME=str(home), LC_ALL="C", TMPDIR=str(self.tmp))
        try:
            result = subprocess.run(argv, cwd=cwd, env=child_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except OSError as error:
            diagnostic = self.safe(f"command spawn failed: {list(argv)}: {error}")
            log = self.path / f"{len(self.commands):02d}.log"
            try:
                log.write_text(diagnostic + "\n")
                self.record(dict(argv=list(argv), cwd=str(cwd or os.getcwd()), exit_code=None,
                                 output=diagnostic, log=log.name, env={"HOME": str(home)}))
            except OSError:
                pass
            raise ValueError(diagnostic) from None
        body = self.redact(result.stdout)
        log = self.path / f"{len(self.commands):02d}.log"
        log.write_bytes(body)
        text = body.decode("utf-8", errors="replace")
        self.record(dict(argv=list(argv), cwd=str(Path(cwd or os.getcwd()).resolve()), exit_code=result.returncode,
                         output=text, log=log.name, env={"HOME": str(home)}))
        print(text, end="", flush=True)
        require(result.returncode == 0, f"command failed: {self.safe(list(argv))}")
        return text.strip()

class Api:
    def __init__(self, evidence, token):
        self.e, self.token = evidence, token
        self.e.tokens.add(token)
        self.config = evidence.path / "gh-config"
        self.config.mkdir()

    def get(self, endpoint, binary=False):
        # Endpoint <=256 characters; positive IDs 1..20 digits; tag components 1..10 digits.
        require(isinstance(endpoint, str) and len(endpoint) <= 256, "API endpoint forbidden: size/type")
        allowed = r"actions/workflows/release\.yml|actions/runs/[1-9][0-9]{0,19}(?:/(?:jobs|artifacts)\?per_page=100)?|actions/artifacts/[1-9][0-9]{0,19}/zip|contents/Cargo.toml\?ref=[0-9a-f]{40}|git/(?:ref/tags/v[0-9]{1,10}\.[0-9]{1,10}\.[0-9]{1,10}|tags/[0-9a-f]{40})|releases/(?:[1-9][0-9]{0,19}|assets/[1-9][0-9]{0,19})"
        require(re.fullmatch(allowed, endpoint), "API endpoint forbidden")
        accept = "application/octet-stream" if endpoint.startswith("releases/assets/") else "application/vnd.github+json"
        argv = ["gh", "api", "--hostname", "github.com", "--method", "GET", f"repos/{REPO}/{endpoint}", "-H", f"Accept: {accept}"]
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=120,
                                env=dict(PATH=os.environ["PATH"], GH_TOKEN=self.token, GH_HOST="github.com", GH_CONFIG_DIR=str(self.config)))
        self.e.record(dict(argv=argv, env={}, exit_code=result.returncode,
                           output=f"response bytes={len(result.stdout)} sha256={sha(result.stdout)}"))
        require(result.returncode == 0 and 0 < len(result.stdout) <= LIMIT, f"API GET failed/oversized: {endpoint}")
        if binary:
            return result.stdout
        try:
            value = json.loads(result.stdout)
        except (ValueError, UnicodeError) as error:
            raise ValueError(f"API JSON malformed: {endpoint}") from error
        require(isinstance(value, dict), f"API JSON object required: {endpoint}")
        return value
