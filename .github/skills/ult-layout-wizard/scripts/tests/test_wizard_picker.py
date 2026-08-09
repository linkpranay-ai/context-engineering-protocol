"""Regression suite for wizard_picker.py (D24 §18.7/S1, locked). Stdlib unittest
only. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_picker as wp  # noqa: E402


def _try_make_symlink(link_path: Path, target: Path) -> bool:
    try:
        link_path.symlink_to(target, target_is_directory=True)
        return True
    except OSError:
        return False


class TestListDirectoryBasics(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "contexts").mkdir()
        (self.root / "org").mkdir()
        (self.root / "README.md").write_text("x", encoding="utf-8")  # a file, not a dir

    def tearDown(self):
        self._tmp.cleanup()

    def test_root_listing_returns_only_directories(self):
        result = wp.list_directory(self.root, ".")
        names = {e.name for e in result.entries}
        self.assertEqual(names, {"contexts", "org"})  # README.md excluded, not a dir

    def test_root_listing_rel_path_and_no_parent(self):
        result = wp.list_directory(self.root, ".")
        self.assertEqual(result.rel_path, ".")
        self.assertIsNone(result.parent_rel_path)

    def test_entries_are_sorted_case_insensitively(self):
        (self.root / "Zebra").mkdir()
        (self.root / "apple").mkdir()
        result = wp.list_directory(self.root, ".")
        names = [e.name for e in result.entries]
        self.assertEqual(names, sorted(names, key=str.casefold))

    def test_entry_rel_paths_are_posix_style_relative_to_root(self):
        result = wp.list_directory(self.root, ".")
        rel_paths = {e.rel_path for e in result.entries}
        self.assertEqual(rel_paths, {"contexts", "org"})

    def test_nested_listing_has_correct_parent(self):
        (self.root / "contexts" / "sub").mkdir()
        result = wp.list_directory(self.root, "contexts")
        self.assertEqual(result.rel_path, "contexts")
        self.assertEqual(result.parent_rel_path, ".")
        self.assertEqual([e.name for e in result.entries], ["sub"])
        self.assertEqual(result.entries[0].rel_path, "contexts/sub")

    def test_grandchild_listing_parent_is_the_intermediate_dir(self):
        (self.root / "contexts" / "sub").mkdir()
        (self.root / "contexts" / "sub" / "leaf").mkdir()
        result = wp.list_directory(self.root, "contexts/sub")
        self.assertEqual(result.parent_rel_path, "contexts")

    def test_target_that_is_a_file_raises(self):
        with self.assertRaises(wp.PickerError):
            wp.list_directory(self.root, "README.md")

    def test_target_that_does_not_exist_raises_via_containment(self):
        with self.assertRaises(wp.PickerError):
            wp.list_directory(self.root, "does-not-exist")

    def test_escape_attempt_raises(self):
        with self.assertRaises(wp.PickerError):
            wp.list_directory(self.root, "../escaped")


class TestListDirectoryFiltering(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_hidden_directories_are_excluded(self):
        (self.root / ".git").mkdir()
        (self.root / ".hidden").mkdir()
        (self.root / "visible").mkdir()
        result = wp.list_directory(self.root, ".")
        self.assertEqual({e.name for e in result.entries}, {"visible"})

    def test_known_build_output_names_are_excluded(self):
        for name in ("node_modules", "dist", "build", "__pycache__", ".venv"):
            (self.root / name).mkdir()
        (self.root / "src").mkdir()
        result = wp.list_directory(self.root, ".")
        self.assertEqual({e.name for e in result.entries}, {"src"})

    def test_symlinked_subdirectory_is_invisible_to_the_picker(self):
        real = Path(tempfile.mkdtemp())
        try:
            link = self.root / "link_to_real"
            if not _try_make_symlink(link, real):
                self.skipTest("process cannot create symlinks (no Developer Mode/admin)")
            (self.root / "ordinary").mkdir()
            result = wp.list_directory(self.root, ".")
            self.assertEqual({e.name for e in result.entries}, {"ordinary"})
        finally:
            import shutil

            shutil.rmtree(real, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
