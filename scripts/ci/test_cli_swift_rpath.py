"""Standalone build.rs directives and Darwin Mach-O rpaths; no live VZ qualification."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "crates/lightr-cli/build.rs"
FLAG = "-Wl,-rpath,/usr/lib/swift"
DIRECTIVE = "cargo:rustc-link-arg=" + FLAG
ENCODED = "-C\x1flink-arg=" + FLAG

def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=30, **kwargs).stdout


def directives(binary, cwd, target="macos", vz=True, flags=None, **extra):
    env = dict(PATH=os.environ["PATH"], SOURCE_DATE_EPOCH="0", CARGO_CFG_TARGET_OS=target)
    if vz:
        env["CARGO_FEATURE_VZ"] = ""  # Cargo feature presence, not truthiness.
    if flags is not None:
        env["CARGO_ENCODED_RUSTFLAGS"] = flags
    return run([str(binary)], cwd=cwd, env=dict(env, **extra)).splitlines()


class CliSwiftRpathTests(unittest.TestCase):
    def test_directives_and_missing_rpath_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp, binary = Path(directory), Path(directory) / "build-script"
            run(["rustc", "--edition=2021", str(SOURCE), "-o", str(binary)])
            for target, vz in (("macos", True), ("macos", False), ("linux", True), ("linux", False)):
                for flags in (None, "", "-C\x1fopt-level=2", ENCODED, "--cfg\x1fprobe\x1f" + ENCODED,
                              "link-arg=" + FLAG, "-Clink-arg=" + FLAG, ENCODED + "/other"):
                    with self.subTest(target=target, vz=vz, flags=flags):
                        lines = directives(binary, tmp, target, vz, flags)
                        provided = flags in (ENCODED, "--cfg\x1fprobe\x1f" + ENCODED)
                        expected = [DIRECTIVE] if target == "macos" and vz and not provided else []
                        self.assertEqual([s for s in lines if s.startswith("cargo:rustc-link-arg=")], expected)
                        self.assertIn("cargo:rustc-env=LIGHTR_GIT_SHA=unknown", lines)
                        self.assertIn("cargo:rustc-env=LIGHTR_BUILD_DATE=1970-01-01", lines)
            sha = run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT).strip()
            self.assertIn("cargo:rustc-env=LIGHTR_GIT_SHA=" + sha, directives(binary, ROOT))
            self.assertIn("cargo:rustc-env=LIGHTR_BUILD_DATE=unknown", directives(binary, tmp, SOURCE_DATE_EPOCH="bad"))
            needle, mutant = f'println!("{DIRECTIVE}");', tmp / "missing.rs"
            self.assertEqual(SOURCE.read_text().count(needle), 1, "mutation anchor missing")
            mutant.write_text(SOURCE.read_text().replace(needle, ""))
            run(["rustc", "--edition=2021", str(mutant), "-o", str(binary)])
            with self.assertRaises(AssertionError):
                self.assertIn(DIRECTIVE, directives(binary, tmp))

    @unittest.skipUnless(sys.platform == "darwin", "Darwin Mach-O linker control requires macOS")
    def test_actual_linker_rpath_control_and_config_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            source, binary, executable = tmp / "main.c", tmp / "build-script", tmp / "fixture"
            source.write_text("int main(void) { return 0; }\n")
            run(["rustc", "--edition=2021", str(SOURCE), "-o", str(binary)])
            for flags, configured, count in ((None, [], 1), (ENCODED, [FLAG], 1), (None, [], 0)):
                emitted = [s.removeprefix("cargo:rustc-link-arg=") for s in directives(binary, tmp, vz=bool(count), flags=flags) if s.startswith("cargo:rustc-link-arg=")]
                run(["clang", str(source), "-o", str(executable), *configured, *emitted])
                loads = run(["otool", "-l", str(executable)]).split("cmd LC_RPATH")[1:]
                self.assertEqual([load.split("path ", 1)[1].split(" (offset", 1)[0] for load in loads], ["/usr/lib/swift"] * count)
                run([str(executable)])

if __name__ == "__main__":
    unittest.main()
