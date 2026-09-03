"""Tests for check_private_refs.py (Round 2 remediation, C-1: the repo-wide
private-document-reference scrub gate). Stdlib unittest only. Run with:

python -m unittest discover -s catalog/tests -v
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_private_refs as cpr  # noqa: E402


def _init_git_repo(root: Path):
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=root, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)


def _write_and_track(root: Path, rel_path: str, content: str):
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", rel_path], cwd=root, check=True)


class TestCheckPrivateRefs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _init_git_repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_tracked_file_naming_denylisted_doc_fails_with_file_and_line(self):
        # The exact shape C-1 found and this gate exists to catch: a tracked file
        # citing the private evaluation doc by filename.
        _write_and_track(
            self.root,
            "notes.md",
            "line one is fine\nsee ISSUES.md Round 2 finding 9 for details\n",
        )
        with self._captured_stdout() as out:
            code = cpr.run_check(self.root)
        self.assertEqual(code, 1)
        self.assertIn("notes.md:2:", out.getvalue())
        self.assertIn("ISSUES.md", out.getvalue())

    def test_clean_tree_passes(self):
        _write_and_track(
            self.root,
            "notes.md",
            "this file names no private documents at all\n",
        )
        with self._captured_stdout() as out:
            code = cpr.run_check(self.root)
        self.assertEqual(code, 0)
        self.assertIn("No private-document reference violations found", out.getvalue())

    def test_allow_marker_suppresses_the_match(self):
        _write_and_track(
            self.root,
            "notes.md",
            "explaining the past cleanup that removed ISSUES.md citations "
            "<!-- private-ref-allow: historical note, not a live citation -->\n",
        )
        with self._captured_stdout() as out:
            code = cpr.run_check(self.root)
        self.assertEqual(code, 0)

    def test_untracked_file_is_not_scanned(self):
        # Per the standing rule: a real ISSUES.md sitting untracked in a
        # contributor's working copy must never trip this gate - only what git
        # actually tracks is in scope.
        (self.root / "ISSUES.md").write_text("private notes\n", encoding="utf-8")
        _write_and_track(self.root, "notes.md", "nothing private here\n")
        with self._captured_stdout() as out:
            code = cpr.run_check(self.root)
        self.assertEqual(code, 0)

    def test_own_test_file_path_is_exempt_from_the_scan(self):
        # The 2026-09-01 evaluation's follow-up on this gate: this checker's own
        # test fixtures necessarily write denylisted filenames verbatim to prove
        # detection works, so `catalog/tests/test_check_private_refs.py` is
        # exempted by relative path - not a marker, since a marker on every
        # fixture line would defeat the point of testing raw detection. This
        # asserts the exemption is scoped to exactly that one path, not to
        # "anything under catalog/tests/": a sibling file at the same depth is
        # not exempt and still trips the scan.
        _write_and_track(
            self.root,
            "catalog/tests/test_check_private_refs.py",
            "fixture line naming ISSUES.md on purpose\n",
        )
        with self._captured_stdout() as out:
            code = cpr.run_check(self.root)
        self.assertEqual(code, 0)
        self.assertIn("No private-document reference violations found", out.getvalue())

        _write_and_track(
            self.root,
            "catalog/tests/test_something_else.py",
            "this sibling file is not exempt: ISSUES.md\n",
        )
        with self._captured_stdout() as out:
            code = cpr.run_check(self.root)
        self.assertEqual(code, 1)
        self.assertIn("test_something_else.py:1:", out.getvalue())

    def test_other_denylisted_filenames_are_each_caught(self):
        for name in (
            "CEP_INSTALLATION_REPORT.md",
            "CEP-HANDOFF.md",
            "CONTEXT-ENGINEERING-DESIGN.md",
        ):
            with self.subTest(name=name):
                root = Path(tempfile.mkdtemp())
                try:
                    _init_git_repo(root)
                    _write_and_track(root, "notes.md", f"see {name} for context\n")
                    with self._captured_stdout() as out:
                        code = cpr.run_check(root)
                    self.assertEqual(code, 1)
                    self.assertIn(name, out.getvalue())
                finally:
                    import shutil

                    shutil.rmtree(root, ignore_errors=True)

    class _captured_stdout:
        def __enter__(self):
            import io

            self._old = sys.stdout
            sys.stdout = self._buf = io.StringIO()
            return self._buf

        def __exit__(self, *exc):
            sys.stdout = self._old


if __name__ == "__main__":
    unittest.main()
