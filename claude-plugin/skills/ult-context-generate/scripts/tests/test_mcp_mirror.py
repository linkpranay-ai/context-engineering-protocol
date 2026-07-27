"""Regression suite for mcp_mirror.py (ROADMAP items 9/11: MCP-backed
What-L1/How-L1 sourcing).

Stdlib unittest only -- no pytest dependency, matching test_content_hash.py's
convention. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mcp_mirror as mm  # noqa: E402


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh)


class TestMirrorOne(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.content_dir = self.tmp / "mock-source"
        self.mirror_dir = self.tmp / "mirror"
        self.manifest = {}
        self.spec = {
            "id": "page-1",
            "source": {
                "server": "mock-wiki",
                "tool": "get_page",
                "identifier": "mock:page-1",
            },
            "mirror_filename": "page-1.md",
            "content_file": "page-1.json",
        }

    def _write_content_file(self, name, body):
        write_json(self.content_dir / name, {"body": body})

    def test_first_run_writes_file_and_manifest_entry(self):
        self._write_content_file("page-1.json", "# Page 1\n\nBody text.\n")
        status = mm.mirror_one(
            self.spec, self.mirror_dir, self.manifest,
            content_dir=str(self.content_dir), spec_file_dir=self.tmp,
        )
        self.assertEqual(status, "written (new)")
        mirror_path = self.mirror_dir / "page-1.md"
        self.assertTrue(mirror_path.exists())
        self.assertIn("Body text.", mirror_path.read_text(encoding="utf-8"))
        self.assertIn("page-1", self.manifest)
        self.assertEqual(len(self.manifest["page-1"]["content_hash8"]), 8)

    def test_second_run_identical_content_is_unchanged_and_mtime_preserved(self):
        self._write_content_file("page-1.json", "# Page 1\n\nBody text.\n")
        mm.mirror_one(
            self.spec, self.mirror_dir, self.manifest,
            content_dir=str(self.content_dir), spec_file_dir=self.tmp,
        )
        mirror_path = self.mirror_dir / "page-1.md"
        mtime_after_first = mirror_path.stat().st_mtime

        time.sleep(0.05)  # ensure a rewrite (if it happened) would be detectable
        status = mm.mirror_one(
            self.spec, self.mirror_dir, self.manifest,
            content_dir=str(self.content_dir), spec_file_dir=self.tmp,
        )
        self.assertEqual(status, "unchanged")
        self.assertEqual(mirror_path.stat().st_mtime, mtime_after_first)

    def test_third_run_changed_content_rewrites_and_bumps_mtime(self):
        self._write_content_file("page-1.json", "# Page 1\n\nBody text.\n")
        mm.mirror_one(
            self.spec, self.mirror_dir, self.manifest,
            content_dir=str(self.content_dir), spec_file_dir=self.tmp,
        )
        mirror_path = self.mirror_dir / "page-1.md"
        mtime_before = mirror_path.stat().st_mtime
        hash_before = self.manifest["page-1"]["content_hash8"]

        time.sleep(0.05)
        self._write_content_file("page-1.json", "# Page 1\n\nBody text CHANGED.\n")
        status = mm.mirror_one(
            self.spec, self.mirror_dir, self.manifest,
            content_dir=str(self.content_dir), spec_file_dir=self.tmp,
        )
        self.assertEqual(status, "written (changed)")
        self.assertGreater(mirror_path.stat().st_mtime, mtime_before)
        self.assertNotEqual(self.manifest["page-1"]["content_hash8"], hash_before)
        self.assertIn("CHANGED", mirror_path.read_text(encoding="utf-8"))

    def test_missing_content_file_fails_loudly(self):
        with self.assertRaises(FileNotFoundError):
            mm.mirror_one(
                self.spec, self.mirror_dir, self.manifest,
                content_dir=str(self.content_dir), spec_file_dir=self.tmp,
            )


class TestCmdMirror(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        write_json(self.tmp / "mock-source" / "page-1.json",
                   {"body": "# Page 1\n\nHello.\n"})
        write_json(self.tmp / "fetch-specs.json", [{
            "id": "page-1",
            "source": {"server": "mock-wiki", "tool": "get_page",
                       "identifier": "mock:page-1"},
            "mirror_filename": "page-1.md",
            "content_file": "mock-source/page-1.json",
        }])

    def test_manifest_round_trips_as_json(self):
        rc = mm.main([
            "mirror",
            "--spec-file", str(self.tmp / "fetch-specs.json"),
            "--mirror-dir", str(self.tmp / "mirror"),
            "--manifest", str(self.tmp / "manifest.json"),
        ])
        self.assertEqual(rc, 0)

        with (self.tmp / "manifest.json").open(encoding="utf-8") as fh:
            manifest = json.load(fh)
        self.assertIn("page-1", manifest)
        self.assertTrue((self.tmp / "mirror" / "page-1.md").exists())

        # Re-run against the unchanged spec file: manifest content is stable.
        rc2 = mm.main([
            "mirror",
            "--spec-file", str(self.tmp / "fetch-specs.json"),
            "--mirror-dir", str(self.tmp / "mirror"),
            "--manifest", str(self.tmp / "manifest.json"),
        ])
        self.assertEqual(rc2, 0)
        with (self.tmp / "manifest.json").open(encoding="utf-8") as fh:
            manifest2 = json.load(fh)
        self.assertEqual(manifest, manifest2)


if __name__ == "__main__":
    unittest.main()
