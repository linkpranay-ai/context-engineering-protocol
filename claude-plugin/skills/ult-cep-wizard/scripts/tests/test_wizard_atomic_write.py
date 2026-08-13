"""Regression suite for wizard_atomic_write.py (D24 §18.2b, locked). Stdlib
unittest only. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_atomic_write as waw  # noqa: E402


class TestWriteTextAtomic(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_writes_new_file(self):
        target = self.root / "new.md"
        waw.write_text_atomic(target, "hello\n")
        self.assertEqual(target.read_text(encoding="utf-8"), "hello\n")

    def test_overwrites_existing_file_completely(self):
        target = self.root / "existing.md"
        target.write_text("old content that is longer than the new one\n", encoding="utf-8")
        waw.write_text_atomic(target, "new\n")
        self.assertEqual(target.read_text(encoding="utf-8"), "new\n")

    def test_no_leftover_temp_file_after_success(self):
        target = self.root / "clean.md"
        waw.write_text_atomic(target, "content\n")
        leftovers = [p for p in self.root.iterdir() if p != target]
        self.assertEqual(leftovers, [])

    def test_missing_parent_directory_raises_and_writes_nothing(self):
        target = self.root / "does-not-exist" / "file.md"
        with self.assertRaises(waw.AtomicWriteError):
            waw.write_text_atomic(target, "content\n")
        self.assertFalse(target.exists())

    def test_failure_during_replace_leaves_target_untouched_and_cleans_up_temp(self):
        target = self.root / "protected.md"
        target.write_text("original\n", encoding="utf-8")

        with mock.patch("os.replace", side_effect=OSError("simulated failure")):
            with self.assertRaises(waw.AtomicWriteError):
                waw.write_text_atomic(target, "attempted overwrite\n")

        self.assertEqual(target.read_text(encoding="utf-8"), "original\n")
        leftovers = [p for p in self.root.iterdir() if p != target]
        self.assertEqual(leftovers, [])

    def test_unicode_content_round_trips(self):
        target = self.root / "unicode.md"
        content = "café — 日本語\n"
        waw.write_text_atomic(target, content)
        self.assertEqual(target.read_text(encoding="utf-8"), content)


if __name__ == "__main__":
    unittest.main()
