"""Regression suite for validate_approved_by.py (approved_by trust signal).

Stdlib unittest only -- no pytest dependency, so this stays vendorable along
with validate_approved_by.py itself. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import validate_approved_by as vab  # noqa: E402


EMPTY_APPROVED_BY = (
    "context_package:\n"
    "  id: example_user-story_20260613\n"
    "  generated_at: \"2026-06-13T00:00:00Z\"\n"
    "  approved_by: []\n"
    "  content_hash: deadbeef\n"
)

ONE_ENTRY_APPROVED_BY = (
    "context_package:\n"
    "  id: example_user-story_20260613\n"
    "  generated_at: \"2026-06-13T00:00:00Z\"\n"
    "  approved_by:\n"
    "    - actor: human:alice\n"
    "      at: \"2026-06-13T00:05:00Z\"\n"
    "  content_hash: deadbeef\n"
)

TWO_ENTRY_APPROVED_BY = (
    "context_package:\n"
    "  id: example_user-story_20260613\n"
    "  generated_at: \"2026-06-13T00:00:00Z\"\n"
    "  approved_by:\n"
    "    - actor: human:alice\n"
    "      at: \"2026-06-13T00:05:00Z\"\n"
    "    - actor: human:bob\n"
    "      at: \"2026-06-13T00:10:00Z\"\n"
    "  content_hash: deadbeef\n"
)

MISSING_FIELD_ENTIRELY = (
    "context_package:\n"
    "  id: example_user-story_20260613\n"
    "  generated_at: \"2026-06-13T00:00:00Z\"\n"
    "  content_hash: deadbeef\n"
)

MALFORMED_ENTRY = (
    "context_package:\n"
    "  id: example_user-story_20260613\n"
    "  generated_at: \"2026-06-13T00:00:00Z\"\n"
    "  approved_by:\n"
    "    - actor: alice\n"
    "      at: \"2026-06-13T00:05:00Z\"\n"
    "  content_hash: deadbeef\n"
)


class TestParseApprovedBy(unittest.TestCase):
    def test_empty_list_is_valid_zero_entries(self):
        found, entries, problems = vab.parse_approved_by(EMPTY_APPROVED_BY)
        self.assertTrue(found)
        self.assertEqual(entries, [])
        self.assertEqual(problems, [])

    def test_one_entry_parsed(self):
        found, entries, problems = vab.parse_approved_by(ONE_ENTRY_APPROVED_BY)
        self.assertTrue(found)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["actor"], "human:alice")
        self.assertEqual(entries[0]["at"], '"2026-06-13T00:05:00Z"')
        self.assertEqual(problems, [])

    def test_two_entries_parsed_no_shape_problems(self):
        """Parsing itself doesn't reject multiple entries -- the >1 rule is
        enforced by validate_file, not parse_approved_by."""
        found, entries, problems = vab.parse_approved_by(TWO_ENTRY_APPROVED_BY)
        self.assertTrue(found)
        self.assertEqual(len(entries), 2)
        self.assertEqual(problems, [])

    def test_field_missing_entirely(self):
        found, entries, problems = vab.parse_approved_by(MISSING_FIELD_ENTIRELY)
        self.assertFalse(found)
        self.assertEqual(entries, [])

    def test_actor_not_human_prefixed_is_a_problem(self):
        found, entries, problems = vab.parse_approved_by(MALFORMED_ENTRY)
        self.assertTrue(found)
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(problems), 1)
        self.assertIn("does not start with 'human:'", problems[0])


class TestValidateFile(unittest.TestCase):
    def _write(self, content):
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        )
        f.write(content)
        f.close()
        return Path(f.name)

    def test_empty_list_valid(self):
        path = self._write(EMPTY_APPROVED_BY)
        try:
            self.assertEqual(vab.validate_file(path), [])
        finally:
            path.unlink()

    def test_one_entry_valid(self):
        path = self._write(ONE_ENTRY_APPROVED_BY)
        try:
            self.assertEqual(vab.validate_file(path), [])
        finally:
            path.unlink()

    def test_two_entries_invalid_in_v1(self):
        path = self._write(TWO_ENTRY_APPROVED_BY)
        try:
            problems = vab.validate_file(path)
            self.assertEqual(len(problems), 1)
            self.assertIn("2 entries found", problems[0])
        finally:
            path.unlink()

    def test_missing_field_is_invalid(self):
        path = self._write(MISSING_FIELD_ENTIRELY)
        try:
            self.assertEqual(vab.validate_file(path), ["missing approved_by field"])
        finally:
            path.unlink()


class TestGatherPackageFiles(unittest.TestCase):
    def test_addenda_sibling_excluded_from_directory_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "alpha_design_20260701.yaml").write_text(ONE_ENTRY_APPROVED_BY, encoding="utf-8")
            (tmp_path / "alpha_design_20260701_20260701.addenda.yaml").write_text(
                "addenda:\n  - id: add_001\n", encoding="utf-8"
            )
            files = vab.gather_package_files(tmp_path)
            self.assertEqual([p.name for p in files], ["alpha_design_20260701.yaml"])

    def test_single_addenda_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "alpha_design_20260701_20260701.addenda.yaml"
            path.write_text("addenda:\n  - id: add_001\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                vab.gather_package_files(path)

    def test_layout_marker_excluded_from_directory_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "alpha_design_20260701.yaml").write_text(ONE_ENTRY_APPROVED_BY, encoding="utf-8")
            (tmp_path / ".layout-slots.yaml").write_text(
                "slots:\n  - slot: context_packages\n", encoding="utf-8"
            )
            files = vab.gather_package_files(tmp_path)
            self.assertEqual([p.name for p in files], ["alpha_design_20260701.yaml"])

    def test_any_dot_prefixed_yaml_is_excluded_not_just_the_layout_marker(self):
        # Proves the exclusion is a shape rule (any dot-prefixed name), not a
        # denylist entry naming .layout-slots.yaml specifically -- a future
        # marker file with a different dot-prefixed name is excluded too,
        # with no new literal name needed here.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "alpha_design_20260701.yaml").write_text(ONE_ENTRY_APPROVED_BY, encoding="utf-8")
            (tmp_path / ".some-other-tool-marker.yaml").write_text(
                "marker: true\n", encoding="utf-8"
            )
            files = vab.gather_package_files(tmp_path)
            self.assertEqual([p.name for p in files], ["alpha_design_20260701.yaml"])


class TestMain(unittest.TestCase):
    def test_main_reports_all_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "alpha_design_20260701.yaml").write_text(ONE_ENTRY_APPROVED_BY, encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vab.main([tmp])
            self.assertEqual(rc, 0)
            self.assertIn("all valid", buf.getvalue())

    def test_main_reports_failure_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "beta_bugfix_20260702.yaml").write_text(TWO_ENTRY_APPROVED_BY, encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vab.main([tmp])
            self.assertEqual(rc, 1)
            self.assertIn("failed validation", buf.getvalue())
            self.assertIn("beta_bugfix_20260702.yaml", buf.getvalue())

    def test_main_on_empty_dir_reports_zero_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vab.main([tmp])
            self.assertEqual(rc, 0)
            self.assertIn("no package files found", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
