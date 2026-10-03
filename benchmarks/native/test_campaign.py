"""Small stdlib controls for the campaign's evidence core; no runtime build."""

import hashlib
import io
import json
import math
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from evidence import coverage, memo, require, summarize, tree, verify_memo


class EvidenceTests(unittest.TestCase):
    def test_require(self):
        require(True, "control")
        with self.assertRaisesRegex(ValueError, "control"):
            require(False, "control")

    def test_memo_positive_and_failures(self):
        row = {"key": "a" * 64, "hit": False, "exit_code": 7}
        encode = lambda value: "lightr-json: " + json.dumps(value)
        text = "lightr: memo MISS key=aaaaaaaaaaaaaaaa\n" + encode(row) + "\n"
        self.assertEqual(memo(text), row)
        verify_memo(row, False, 7, expected_key="a" * 64, different_key="b" * 64)
        bad_text = ["", "{}", "lightr-json: {}", "lightr-json: null",
                    "lightr-json: broken", text + encode(row),
                    "lightr-json unknown", " " + encode(row),
                    encode(row).replace('"hit":', '"key": "' + "b" * 64 + '", "hit":')]
        for text in bad_text:
            with self.subTest(stderr=text), self.assertRaises(ValueError):
                memo(text)
        for field, value in [("key", "a" * 63), ("key", "A" * 64), ("key", 1),
                             ("hit", 0), ("hit", "false"), ("exit_code", True),
                             ("exit_code", 7.0), ("extra", 0)]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                memo(encode(dict(row, **{field: value})))
        for args in [(True, 7), (False, 0), (False, 7, "b" * 64),
                     (False, 7, None, "a" * 64), (0, 7), (False, True),
                     (False, 7, "bad")]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                verify_memo(row, *args)
        with self.assertRaises(ValueError):
            verify_memo(dict(row, hit=0), False, 7)
        with self.assertRaises(ValueError):
            verify_memo(dict(row, hit=True), False, 7)
        verify_memo(dict(row, hit=True, exit_code=0), True, 0, "a" * 64)

    def test_exact_coverage(self):
        sizes, scenarios = [1, 2], ["miss", "hit"]
        rows = [{"size": size, "scenario": scenario, "iteration": i,
                 "phase": "sample", "validated": True}
                for size in sizes for scenario in scenarios for i in range(3)]
        expected = {(size, scenario, i) for size in sizes for scenario in scenarios
                    for i in range(3)}
        extras = [{"phase": phase, "validated": True} for phase in ("setup", "warmup")]
        self.assertEqual(coverage(rows + extras, sizes, 3, scenarios), expected)
        defects = [[], extras, rows[:-1], rows + rows[:1],
                   [dict(rows[0], size=99)] + rows[1:],
                   [dict(rows[0], iteration=True)] + rows[1:],
                   [dict(rows[0], scenario="unknown")] + rows[1:],
                   [dict(rows[0], validated=False)] + rows[1:],
                   [dict(rows[0], validated=1)] + rows[1:],
                   rows + [{"phase": "skip", "validated": True}],
                   rows + [{"validated": True}], rows + [None]]
        for defect in defects:
            with self.subTest(rows=defect), self.assertRaises(ValueError):
                coverage(defect, sizes, 3, scenarios)
        for size_list, rounds, names in [([], 3, scenarios), ([1, 1], 3, scenarios),
                                        ([0], 3, scenarios), ([True], 3, scenarios),
                                        (sizes, 2, scenarios), (sizes, True, scenarios),
                                        (sizes, 3, []), (sizes, 3, ["hit", "hit"])]:
            with self.subTest(sizes=size_list, rounds=rounds, names=names):
                with self.assertRaises(ValueError):
                    coverage(rows, size_list, rounds, names)

    def test_tree_golden_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "file"
            data.write_bytes(b"known bytes")
            data.chmod(0o751)
            (root / "empty").mkdir(mode=0o755)
            (root / "empty").chmod(0o755)
            link = root / "link"
            link.symlink_to("file")
            golden = tree(root)
            entries = {"empty": {"kind": "dir", "mode": 0o755},
                       "file": {"kind": "file", "mode": 0o751, "size": 11,
                                "sha256": hashlib.sha256(b"known bytes").hexdigest()},
                       "link": {"kind": "symlink", "mode": link.lstat().st_mode & 0o7777,
                                "target": "file"}}
            encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
            self.assertEqual(golden, {"entries": entries,
                                     "sha256": hashlib.sha256(encoded).hexdigest()})

            def restore_empty():
                (root / "empty").mkdir(mode=0o755)
                (root / "empty").chmod(0o755)

            for change, restore in [
                (lambda: data.write_bytes(b"wrong bytes"), lambda: data.write_bytes(b"known bytes")),
                (lambda: data.chmod(0o644), lambda: data.chmod(0o751)),
                (lambda: (root / "empty").rmdir(), restore_empty),
            ]:
                change()
                self.assertNotEqual(tree(root), golden)
                restore()
                self.assertEqual(tree(root), golden)
            (root / "extra").write_bytes(b"unexpected")
            self.assertNotEqual(tree(root), golden)
            (root / "extra").unlink()
            data.unlink()
            self.assertNotEqual(tree(root), golden)
            os.mkfifo(root / "fifo")
            with self.assertRaisesRegex(ValueError, "unsupported fixture entry"):
                tree(root)
            for invalid_root in (link, str(link) + "/"):
                with self.assertRaisesRegex(ValueError, "not a directory"):
                    tree(invalid_root)

    def test_statistics_known_vectors(self):
        self.assertEqual(summarize([3, 1, 2]),
                         {"n": 3, "min": 1, "p50": 2, "p95": 3, "max": 3, "sample_stddev": 1})
        even = summarize([40, 10, 30, 20])
        self.assertEqual({k: v for k, v in even.items() if k != "sample_stddev"},
                         {"n": 4, "min": 10, "p50": 25, "p95": 40, "max": 40})
        self.assertAlmostEqual(even["sample_stddev"], math.sqrt(500 / 3))
        ranked = summarize(range(1, 22))
        self.assertEqual(ranked["p95"], 20)
        self.assertAlmostEqual(ranked["sample_stddev"], math.sqrt(38.5))
        large = summarize([1e308] * 4)
        self.assertEqual(large["p50"], 1e308)
        self.assertTrue(all(math.isfinite(value) for value in large.values()))
        for values in [[], [1], [1, 2], [1, 2, float("nan")], [1, 2, float("inf")],
                       [1, 2, -float("inf")], [1, 2, True], [1, 2, "3"], [1.79e308, -1.79e308] * 2]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                summarize(values)

    def test_raw_symlink_spelling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests = []
            for target in ("file", "./file", "file/"):
                os.symlink(target, root / "link")
                manifest = tree(root)
                self.assertEqual(manifest["entries"]["link"]["target"], target)
                manifests.append(manifest["sha256"])
                (root / "link").unlink()
            self.assertEqual(len(set(manifests)), 3)

    def test_replacements_after_stat(self):
        real_open, real_scan, real_io, real_read = os.open, os.scandir, io.open, os.read
        for kind in ("file", "directory"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                root, outside = base / "root", base / "outside"
                root.mkdir()
                outside.mkdir()
                (outside / "data").write_bytes(b"outside")
                victim = root / "entry"
                victim.mkdir() if kind == "directory" else victim.write_bytes(b"inside")
                before = victim.lstat()
                self.assertIn("entry", tree(root)["entries"])
                replaced = False
                opened = []

                def replace():
                    nonlocal replaced
                    replaced = True
                    victim.rename(root / "parked")
                    victim.symlink_to(outside if kind == "directory" else outside / "data")

                def opening(name, flags, *args, **kwargs):
                    if kind == "file" and not replaced and str(name) in ("entry", str(victim)):
                        replace()
                    descriptor = real_open(name, flags, *args, **kwargs)
                    opened.append(descriptor)
                    return descriptor

                def scanning(name):
                    matches = os.fstat(name).st_ino == before.st_ino if isinstance(name, int) else Path(name) == victim
                    if kind == "directory" and matches and not replaced:
                        replace()
                        self.assertIsInstance(name, int)
                    return real_scan(name)

                def reading(descriptor, count):
                    self.assertNotEqual(os.fstat(descriptor).st_ino, (outside / "data").stat().st_ino)
                    return real_read(descriptor, count)

                def legacy_io(name, *args, **kwargs):
                    if name == victim:
                        kwargs["opener"] = os.open
                    return real_io(name, *args, **kwargs)

                with patch("os.open", side_effect=opening), patch("os.scandir", side_effect=scanning), \
                        patch("io.open", side_effect=legacy_io), patch("os.read", side_effect=reading), \
                        self.assertRaises((OSError, ValueError)):
                    tree(root)
                self.assertTrue(replaced)
                for descriptor in opened:
                    with self.assertRaises(OSError):
                        os.fstat(descriptor)


if __name__ == "__main__":
    unittest.main()
