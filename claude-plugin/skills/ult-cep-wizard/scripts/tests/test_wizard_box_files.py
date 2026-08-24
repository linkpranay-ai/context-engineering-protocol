"""Regression suite for wizard_box_files.py. Stdlib unittest only. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_box_files as wbf  # noqa: E402


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestListFiles(unittest.TestCase):
    def test_missing_directory_is_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            listing = wbf.list_files(root, "does/not/exist/")
            self.assertEqual(listing.files, [])
            self.assertEqual(listing.total_count, 0)
            self.assertFalse(listing.truncated)

    def test_path_that_is_a_file_not_a_directory_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "not-a-dir.md", "x")
            listing = wbf.list_files(root, "not-a-dir.md")
            self.assertEqual(listing.files, [])
            self.assertEqual(listing.total_count, 0)

    def test_empty_directory_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            listing = wbf.list_files(root, "docs/")
            self.assertEqual(listing.files, [])
            self.assertEqual(listing.total_count, 0)
            self.assertFalse(listing.truncated)

    def test_files_listed_relative_to_queried_directory_sorted_casefold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "docs" / "b.md")
            _write(root / "docs" / "A.md")
            _write(root / "docs" / "nested" / "c.md")
            listing = wbf.list_files(root, "docs/")
            self.assertEqual(listing.files, ["A.md", "b.md", "nested/c.md"])
            self.assertEqual(listing.total_count, 3)
            self.assertFalse(listing.truncated)

    def test_ignored_names_are_pruned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "docs" / "real.md")
            _write(root / "docs" / ".git" / "HEAD")
            _write(root / "docs" / "__pycache__" / "x.pyc")
            _write(root / "docs" / ".gitkeep")
            _write(root / "docs" / "Thumbs.db")
            _write(root / "docs" / ".DS_Store")
            listing = wbf.list_files(root, "docs/")
            self.assertEqual(listing.files, ["real.md"])
            self.assertEqual(listing.total_count, 1)

    def test_truncation_caps_list_but_keeps_real_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(5):
                _write(root / "docs" / f"file-{i}.md")
            listing = wbf.list_files(root, "docs/", limit=3)
            self.assertEqual(len(listing.files), 3)
            self.assertEqual(listing.total_count, 5)
            self.assertTrue(listing.truncated)
            self.assertEqual(listing.files, sorted(listing.files, key=str.casefold))

    def test_exactly_at_limit_is_not_truncated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(3):
                _write(root / "docs" / f"file-{i}.md")
            listing = wbf.list_files(root, "docs/", limit=3)
            self.assertEqual(len(listing.files), 3)
            self.assertEqual(listing.total_count, 3)
            self.assertFalse(listing.truncated)

    def test_trailing_slash_on_rel_dir_is_tolerated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "docs" / "spec.md")
            with_slash = wbf.list_files(root, "docs/")
            without_slash = wbf.list_files(root, "docs")
            self.assertEqual(with_slash.files, without_slash.files)


if __name__ == "__main__":
    unittest.main()
