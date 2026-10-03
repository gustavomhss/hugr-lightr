import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path

from provenance import harness_identity, validate_receipt


class ProvenanceTests(unittest.TestCase):
    def test_receipt_identities_profile_cleanliness_and_types(self):
        source, binary, sha, digest = Path('/source'), Path('/source/target/release/lightr'), 'a' * 40, 'b' * 64
        receipt = {"schema": 1, "status": "complete", "source_sha": sha,
                   "tracked_clean_before": True, "tracked_clean_after": True, "profile": "release",
                   "argv": ["cargo", "+1.96.0", "build", "--locked", "--release", "--bin", "lightr"],
                   "cwd": str(source), "exit": 0, "binary": str(binary), "binary_sha256": digest,
                   "cargo_version": "cargo 1.96.0 (control)", "rustc_version": "rustc 1.96.0 (control)",
                   "started_unix_ns": 1, "completed_unix_ns": 2}
        def validate(value):
            return validate_receipt(json.dumps(value).encode(), source, sha, binary, digest)
        self.assertEqual(validate(receipt), receipt)
        defects = {"schema": True, "status": "started", "source_sha": 'c' * 40,
                   "tracked_clean_before": False, "tracked_clean_after": 1, "profile": "debug",
                   "argv": ['cargo', 'build', '--release'], "cwd": '/elsewhere', "exit": False,
                   "binary": '/source/target/debug/lightr', "binary_sha256": 'c' * 64,
                   "cargo_version": 'cargo 1.95.0 (old)', "rustc_version": 'rustc 1.95.0 (old)',
                   "started_unix_ns": True, "completed_unix_ns": time.time_ns() + 10**12}
        for field, value in defects.items():
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(dict(receipt, **{field: value}))
        for field in receipt:
            incomplete = dict(receipt)
            del incomplete[field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                validate(incomplete)
        with self.assertRaises(ValueError):
            validate(dict(receipt, extra='unknown'))
        duplicate = json.dumps(receipt).replace('"profile": "release"', '"profile": "debug", "profile": "release"')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON field'):
            validate_receipt(duplicate.encode(), source, sha, binary, digest)

    def test_harness_hashes_distinct_from_product_and_untracked_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            directory = root / 'benchmarks/native'
            directory.mkdir(parents=True)
            for name in ('campaign.py', 'evidence.py', 'deadline.py', 'commands.py'):
                (directory / name).write_bytes(name.encode())
            (root / 'product').mkdir()
            (root / 'output.json').write_text('untracked output')
            result = harness_identity(directory / 'campaign.py', 'a' * 40, '')
            self.assertEqual(result['repo_root'], str(root))
            self.assertEqual(result['git_sha'], 'a' * 40)
            self.assertEqual(result['file_sha256'], {name: hashlib.sha256(name.encode()).hexdigest()
                             for name in ('campaign.py', 'evidence.py', 'deadline.py', 'commands.py')})
            with self.assertRaisesRegex(ValueError, 'harness worktree is dirty'):
                harness_identity(directory / 'campaign.py', 'a' * 40, ' M campaign.py')
