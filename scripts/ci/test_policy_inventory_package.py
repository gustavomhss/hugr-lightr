"""Guard source-workspace inventory byte sync/schema and Cargo-listed CLI fixture.

Uses real metadata/package --list, not an archive build or runtime witness.
Discovered by the existing Required CI test_*.py runner.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CANONICAL = Path("benchmarks/s3/security/inventory.json")
RESOURCE = Path("src/handlers/run/policy_security_inventory.json")
DERIVED = Path("crates/lightr-cli") / RESOURCE


def validate(root):
    payloads = []
    for label, path in (("canonical", CANONICAL), ("derived", DERIVED)):
        try:
            payloads.append((root / path).read_bytes())
        except OSError as error:
            raise AssertionError(f"{label} inventory missing/unreadable: {path}: {error}") from error
    if payloads[0] != payloads[1]:
        raise AssertionError(f"derived inventory byte mismatch: {DERIVED} != {CANONICAL}")
    try:
        data = json.loads(payloads[0])
    except (ValueError, UnicodeError) as error:
        raise AssertionError(f"inventory JSON invalid: {CANONICAL}: {error}") from error
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
        raise AssertionError("inventory schema: expected object with version 1")
    rows = data.get("controls")
    if not isinstance(rows, list) or not rows:
        raise AssertionError("inventory schema: controls missing/non-array/empty")
    names = set()
    for row in rows:
        if not isinstance(row, dict):
            raise AssertionError("inventory schema: control row is not an object")
        for field in ("control", "cli", "parser", "run_config", "witness", "enforcement",
                      "platform", "oracle", "fixture", "mutation"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise AssertionError(f"inventory schema: {row.get('control')} missing/invalid {field}")
        if row["control"] in names:
            raise AssertionError(f"inventory schema: duplicate control {row['control']}")
        names.add(row["control"])
        if "exec_spec" not in row or (row["exec_spec"] is not None and
                                      (not isinstance(row["exec_spec"], str) or not row["exec_spec"])):
            raise AssertionError(f"inventory schema: {row['control']} invalid exec_spec")
        for engine in ("native", "ns", "vz"):
            if row.get(engine) not in ("enforced", "refused", "unsupported"):
                raise AssertionError(f"inventory schema: {row['control']}/{engine} invalid outcome")


def cargo(*args):
    result = subprocess.run(["cargo", *args], cwd=ROOT, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise AssertionError(f"cargo {' '.join(args)} failed: {result.stdout}{result.stderr}")
    return result.stdout


class PolicyInventoryPackageTests(unittest.TestCase):
    def test_workspace_sync_and_real_cargo_package_list(self):
        validate(ROOT)
        metadata = json.loads(cargo("metadata", "--no-deps", "--format-version", "1", "--offline", "--locked"))
        packages = [p for p in metadata["packages"] if any(
            t["name"] == "lightr" and "bin" in t["kind"] for t in p["targets"])]
        self.assertEqual(len(packages), 1, "CLI binary package missing/ambiguous")
        # Listing resolves registry metadata on a cold CI runner; it never uploads.
        listing = cargo("package", "--list", "--allow-dirty", "--locked",
                        "--manifest-path", packages[0]["manifest_path"]).splitlines()
        self.assertTrue(listing, "cargo package --list returned empty")
        self.assertIn(RESOURCE.as_posix(), listing, "derived inventory missing from CLI package list")

    def test_guard_rejects_byte_control_missing_and_schema_mutations(self):
        with tempfile.TemporaryDirectory(prefix="policy-inventory-") as tmp:
            root = Path(tmp)
            original = (ROOT / CANONICAL).read_bytes()
            for path in (CANONICAL, DERIVED):
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_bytes(original)
            validate(root)
            for mutated in (original + b"\n", original.replace(b'"--user"', b'"--mutated"', 1)):
                (root / DERIVED).write_bytes(mutated)
                with self.assertRaisesRegex(AssertionError, "derived inventory byte mismatch"):
                    validate(root)
            (root / DERIVED).write_bytes(original)
            for label, path in (("canonical", CANONICAL), ("derived", DERIVED)):
                (root / path).unlink()
                with self.assertRaisesRegex(AssertionError, f"{label} inventory missing/unreadable"):
                    validate(root)
                (root / path).write_bytes(original)
            bad_row = json.loads(original)["controls"][0]
            bad_row["native"] = "unknown"
            for payload, reason in ((b"", "JSON invalid"), (b"{}", "schema"),
                                    (b'{"version":true,"controls":[{}]}', "schema"),
                                    (b'{"version":1,"controls":{}}', "controls missing/non-array/empty"),
                                    (b'{"version":1,"controls":[]}', "controls missing/non-array/empty"),
                                    (b'{"version":1,"controls":[null]}', "not an object"),
                                    (b'{"version":1,"controls":[{}]}', "missing/invalid control"),
                                    (json.dumps({"version": 1, "controls": [dict(bad_row, exec_spec=1)]}).encode(), "invalid exec_spec"),
                                    (json.dumps({"version": 1, "controls": [json.loads(original)["controls"][0]] * 2}).encode(), "duplicate control"),
                                    (json.dumps({"version": 1, "controls": [bad_row]}).encode(), "invalid outcome")):
                for path in (CANONICAL, DERIVED):
                    (root / path).write_bytes(payload)
                with self.assertRaisesRegex(AssertionError, reason):
                    validate(root)


if __name__ == "__main__":
    unittest.main()
