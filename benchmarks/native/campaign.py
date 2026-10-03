"""Serial Linux native campaign; cold CAS/index never means cold OS caches."""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import sys
import tempfile
import time
import traceback
import tomllib
from pathlib import Path

from commands import Commands, TIME, append
from evidence import _unique_object, coverage, memo, require, summarize, tree, verify_memo
from provenance import harness_identity, validate_receipt

SCENARIOS = ("snapshot-cold", "snapshot-warm", "hydrate", "direct", "memo-miss",
             "memo-hit", "input-invalidation", "failed-command")


def scenario_selection(value):
    selected = value.split(",")
    require(selected and all(name in SCENARIOS for name in selected) and
            len(set(selected)) == len(selected), "scenarios must be nonempty, known and unique")
    return tuple(selected)


WORK = """import hashlib, sys
from pathlib import Path
data = Path(sys.argv[1]).read_bytes()
digest = hashlib.sha256()
for _ in range(4096):
    digest.update(data)
with Path(sys.argv[2]).open('ab') as counter:
    counter.write(b'x')
print(digest.hexdigest())
sys.exit(int(sys.argv[3]))
"""


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def fixture(path, size):
    path.mkdir()
    path.chmod(0o755)
    for i in range(size):
        payload = i.to_bytes(8, "little") + hashlib.shake_256(str(i).encode()).digest(4088)
        file = path / f"file-{i:08d}"
        file.write_bytes(payload)
        file.chmod(0o755 if i % 100 == 0 else 0o644)
    (path / "empty").mkdir()
    (path / "empty").chmod(0o755)
    (path / "link").symlink_to("file-00000000")
    return tree(path)


class Campaign(Commands):
    def __init__(self, args, out):
        self.args, self.out = args, out
        self.scenarios = scenario_selection(getattr(args, "scenarios", ",".join(SCENARIOS)))
        self.rows, self.sequence, self.roots = [], 0, {}
        self.context = {"size": None, "scenario": "preflight", "iteration": -1}
        self.meta = {"source_sha": args.source_sha, "options": vars(args), "status": "running",
                     "scenarios": self.scenarios,
                     "started_unix_ns": time.time_ns(),
                     "scope": "Lightr native only; reproducibility, not a sandbox",
                     "cold": "fresh CAS/index/home; OS caches NOT flushed",
                     "sampling_policy": "startup-only load1 gate; serial size/scenario blocks, warmups then samples; not randomized; all samples retained",
                     "wall_scope": "perf_counter_ns including GNU-time wrapper",
                     "usage_scope": "GNU time command/waited descendants; RSS peak, not sum"}
        for directory in ("logs", "work", "fixtures"):
            (out / directory).mkdir()
        self.python = str(Path(sys.executable).resolve(strict=True))
        self.env = self.environment(out / "work")

    def environment(self, home):
        return {"PATH": "/usr/bin:/bin", "HOME": str(home),
                "LIGHTR_HOME": str(home), "LC_ALL": "C"}

    def accept(self, row):
        row["validated"] = True
        append(self.out / "raw.jsonl", row)
        self.rows.append(row)
        return row

    def probe(self, argv):
        return self.accept(self.command(argv))["stdout"].strip()

    def preflight(self):
        a = self.args
        require(platform.system() == "Linux" and platform.machine() == "x86_64",
                "campaign requires Linux x86_64")
        require(re.fullmatch(r"[0-9a-f]{40}", a.source_sha), "source SHA must be 40 lowercase hex")
        require(a.rounds >= 3 and a.warmups >= 0, "rounds >=3 and warmups >=0 required")
        require(re.fullmatch(r"[0-9]+(?:,[0-9]+)*", a.sizes), "sizes require comma-separated integers")
        self.sizes = list(map(int, a.sizes.split(",")))
        require(all(0 < n < 2**64 for n in self.sizes) and len(set(self.sizes)) == len(self.sizes),
                "sizes must be positive and unique")
        self.source, self.binary = Path(a.source_dir).resolve(strict=True), Path(a.binary).resolve(strict=True)
        header = self.binary.read_bytes()[:64]
        require(len(header) == 64 and header[:6] == b"\x7fELF\x02\x01"
                and int.from_bytes(header[18:20], "little") == 62, "binary must be ELF64 x86_64")
        self.meta.update(binary_sha256=hashlib.sha256(self.binary.read_bytes()).hexdigest(),
                         binary=str(self.binary), source_dir=str(self.source), elf_class=64, elf_machine=62)
        tools = {name: shutil.which(name, path=self.env["PATH"]) for name in ("git", "lscpu", "stat")}
        require(all(tools.values()), "missing git/lscpu/stat")
        self.git = tools["git"]
        self.binding()
        self.build_provenance()
        version = self.probe([self.binary, "--version"])
        package_version = tomllib.loads((self.source / "Cargo.toml").read_text())["workspace"]["package"]["version"]
        require(version.startswith(f"lightr {package_version} ({a.source_sha[:7]}"),
                "binary version/source mismatch")
        require("GNU Time" in self.probe([TIME, "--version"]), "real GNU /usr/bin/time required")
        cpuinfo = Path("/proc/cpuinfo").read_text()
        model = next((line.split(":", 1)[1].strip() for line in cpuinfo.splitlines()
                      if line.startswith("model name")), None)
        cpus = os.cpu_count()
        require(model and cpus and cpus > 0, "missing CPU identity/count")
        runner_keys = ("GITHUB_ACTIONS", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB",
                       "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_REF", "GITHUB_WORKFLOW",
                       "RUNNER_NAME", "RUNNER_OS", "RUNNER_ARCH", "RUNNER_ENVIRONMENT",
                       "ImageOS", "ImageVersion")
        self.meta.update(version=version, uname=platform.uname()._asdict(), cpu_model=model,
                         logical_cpus=cpus, cpuinfo=cpuinfo, meminfo=Path("/proc/meminfo").read_text(),
                         os_release=Path("/etc/os-release").read_text(), python=sys.version,
                         lscpu=self.probe([tools["lscpu"]]),
                         filesystem=self.probe([tools["stat"], "-f", str(self.out)]),
                         runner={k: os.environ[k] for k in runner_keys if k in os.environ})

    def build_provenance(self):
        raw = Path(self.args.build_receipt).read_bytes()
        self.meta.update(build_receipt=validate_receipt(raw, self.source, self.args.source_sha,
                         self.binary, self.meta["binary_sha256"]), build_receipt_sha256=hashlib.sha256(raw).hexdigest())
        root = Path(__file__).resolve().parents[2]
        require(root != self.source, "product checkout must be separate from harness")
        self.meta["harness"] = harness_identity(__file__, self.probe([self.git, "-C", root, "rev-parse", "HEAD"]),
            self.probe([self.git, "-C", root, "status", "--porcelain", "--untracked-files=no"]))

    def binding(self):
        require(self.probe([self.git, "-C", self.source, "rev-parse", "HEAD"]) == self.args.source_sha,
                "source HEAD mismatch")
        require(not self.probe([self.git, "-C", self.source, "status", "--porcelain", "--untracked-files=no"]),
                "tracked source worktree is dirty")
        require(hashlib.sha256(self.binary.read_bytes()).hexdigest() == self.meta["binary_sha256"],
                "binary changed during campaign")

    def report(self, row, fields):
        report = json.loads(row["stdout"], object_pairs_hook=_unique_object)
        require(isinstance(report, dict) and set(report) == set(fields), "unexpected report schema")
        require(re.fullmatch(r"[0-9a-f]{64}", report["root"]), "invalid snapshot root")
        require(type(report["files"]) is int and report["files"] == self.context["size"]
                and type(report["bytes_total"]) is int and report["bytes_total"] == self.context["size"] * 4096,
                "snapshot/hydrate file/byte counts mismatch")
        expected = self.roots.setdefault(self.context["size"], report["root"])
        require(report["root"] == expected, "fixture snapshot root changed")
        return report

    def case(self, path, golden, phase):
        scenario = self.context["scenario"]
        first = path / "file-00000000"
        original = first.read_bytes()
        require(tree(path) == golden, "fixture precondition mismatch")
        with tempfile.TemporaryDirectory(prefix="case-", dir=self.out / "work") as temporary:
            home = Path(temporary) / "home"
            home.mkdir()
            env = self.environment(home)
            counter = Path(temporary) / "counter"
            dest = Path(temporary) / "dest"
            snap = [self.binary, "--json", "snapshot", "--dir", path, "--name", "@campaign/data"]

            def snapshot(stage, timed, new):
                row = self.command(snap, stage, timed, env)
                report = self.report(row, ("root", "files", "bytes_total", "objects_new"))
                require(type(report["objects_new"]) is int and report["objects_new"] == new,
                        "snapshot new-object count mismatch")
                return row

            failed = scenario == "failed-command"
            child = [self.python, "-I", "-c", WORK, str(first), str(counter), "7" if failed else "0"]
            native = [self.binary, "--json", "run", "--engine", "native", "--dir", str(path),
                      "--input", str(path), "--", *child]

            def execute(stage, timed, count, hit=False, key=None, different=None):
                data = first.read_bytes()
                row = self.command(child if scenario == "direct" else native, stage, timed, env,
                                   exit_code=7 if failed else 0, cwd=path)
                digest = hashlib.sha256(data * 4096).hexdigest()
                require(row["stdout"] == digest + "\n", "workload stdout digest mismatch")
                require(counter.read_bytes() == b"x" * count, "execution counter mismatch")
                row.update(input_sha256=hashlib.sha256(data).hexdigest(), counter=count)
                if scenario == "direct":
                    require(not row["stderr"], "unexpected direct stderr")
                else:
                    parsed = memo(row["stderr"])
                    verify_memo(parsed, hit, 7 if failed else 0, key, different)
                    lines = row["stderr"].splitlines()
                    marker = f"lightr: memo {'HIT' if hit else 'MISS'} key={parsed['key'][:16]}"
                    require(len(lines) == 2 and lines[0] == marker, "unexpected native stderr")
                    row["memo"] = parsed
                return row

            try:
                if scenario in ("snapshot-warm", "hydrate"):
                    self.accept(snapshot("setup", False, self.context["size"]))
                if scenario.startswith("snapshot"):
                    row = snapshot(phase, True, self.context["size"] if scenario == "snapshot-cold" else 0)
                elif scenario == "hydrate":
                    row = self.command([self.binary, "--json", "hydrate", dest, "--name", "@campaign/data"],
                                       phase, True, env)
                    report = self.report(row, ("root", "files", "bytes_total", "rung"))
                    require(report["rung"] in ("reflink", "copyrange", "copy"), "invalid Linux hydrate rung")
                    require(tree(dest) == golden, "hydrate whole-tree golden mismatch")
                elif scenario in ("memo-hit", "input-invalidation", "failed-command"):
                    seed = self.accept(execute("setup", False, 1))
                    key = seed["memo"]["key"]
                    if scenario == "input-invalidation":
                        first.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                        require(hashlib.sha256(first.read_bytes()).hexdigest() != seed["input_sha256"],
                                "input mutation did not change SHA-256")
                        row = execute(phase, True, 2, different=key)
                    else:
                        row = execute(phase, True, 1 if scenario == "memo-hit" else 2,
                                      hit=scenario == "memo-hit", key=key)
                else:
                    row = execute(phase, True, 1)
            finally:
                if scenario == "input-invalidation":
                    first.write_bytes(original)
            require(tree(path) == golden, "fixture changed after case")
            self.accept(row)

    def run(self):
        self.preflight()
        datasets = {size: fixture(self.out / "fixtures" / str(size), size) for size in self.sizes}
        self.meta["datasets"] = datasets
        write_json(self.out / "metadata.json", self.meta)
        deadline = time.monotonic() + 60
        self.meta["load_wait"] = []
        while True:
            require(time.monotonic() < deadline, "load1 stayed above logical CPUs for 60 seconds")
            load = os.getloadavg()
            self.meta["load_wait"].append(load)
            if load[0] <= self.meta["logical_cpus"]:
                break
            time.sleep(min(1, max(0, deadline - time.monotonic())))
        write_json(self.out / "metadata.json", self.meta)
        control = self.command([self.python, "-c", "print('gnu-time-control')"], timed=True)
        require(control["stdout"] == "gnu-time-control\n", "GNU-time control output mismatch")
        require(control["max_rss_kib"] > 0 and control["wall_ns"] > 0, "GNU-time control saw no usage")
        self.accept(control)
        for size, golden in datasets.items():
            for scenario in self.scenarios:
                for i in range(self.args.warmups + self.args.rounds):
                    phase = "warmup" if i < self.args.warmups else "sample"
                    self.context = {"size": size, "scenario": scenario,
                                    "dataset_sha256": golden["sha256"],
                                    "iteration": i if phase == "warmup" else i - self.args.warmups}
                    self.case(self.out / "fixtures" / str(size), golden, phase)
        self.context = {"size": None, "scenario": "postflight", "iteration": -1}
        self.binding()
        coverage(self.rows, self.sizes, self.args.rounds, self.scenarios)
        summary = {}
        for size in self.sizes:
            for scenario in self.scenarios:
                rows = [r for r in self.rows if r["phase"] == "sample"
                        and r["size"] == size and r["scenario"] == scenario]
                summary[f"{size}/{scenario}"] = {metric: summarize([r[metric] for r in rows])
                    for metric in ("wall_ns", "user_s", "system_s", "max_rss_kib")}
                summary[f"{size}/{scenario}"]["overloaded_sample_count"] = sum(r["overloaded"] for r in rows)
        write_json(self.out / "summary.json", summary)
        (self.out / "summary.md").write_text("# Native campaign\n\nCold CAS/index, not OS-cold. Units: ns, seconds, KiB.\n\n```json\n" +
            (self.out / "summary.json").read_text() + "```\n")
        self.meta.update(status="complete", completed_unix_ns=time.time_ns(), load_after=os.getloadavg())
        write_json(self.out / "metadata.json", self.meta)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for flag in ("binary", "source-dir", "source-sha", "build-receipt", "out"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--rounds", type=int, default=21)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--sizes", default="1000,10000")
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    args = parser.parse_args()
    scenario_selection(args.scenarios)
    out = Path(args.out).absolute()
    require(not out.is_symlink() and (not out.exists() or out.is_dir() and not any(out.iterdir())),
            "output must be a new or empty nonsymlink directory")
    out.mkdir(parents=True, exist_ok=True)
    campaign = None
    try:
        campaign = Campaign(args, out)
        campaign.run()
        return 0
    except (Exception, KeyboardInterrupt) as error:
        for name in ("summary.json", "summary.md"):
            (out / name).unlink(missing_ok=True)
        write_json(out / "failure.json", {"error": str(error), "type": type(error).__name__,
                                          "traceback": traceback.format_exc(), "options": vars(args)})
        if campaign is not None:
            campaign.meta["status"] = "failed"
            write_json(out / "metadata.json", campaign.meta)
        print(f"campaign failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
