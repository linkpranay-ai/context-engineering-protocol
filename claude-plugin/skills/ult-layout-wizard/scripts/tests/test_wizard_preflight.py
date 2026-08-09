"""Regression suite for wizard_preflight.py (D24 §18.10 exit criterion 6; narrowed in
Phase 2, §18.14). Stdlib unittest only, same posture as ult-repo-layout's own test
suite. Run with:

    python -m unittest discover -s scripts/tests -v

Each fixture repo is built fresh in a tempdir per test, rather than checked in under
fixtures/ - the interesting thing about each case is precisely *which* file is
missing/present, which a freshly-assembled tree makes explicit at the point of each
test instead of requiring a reader to go inspect a separate on-disk fixture directory.

Phase 2 retired this module's old checks 2 (`_check_initialized`, D20 axis) and 3
(`_check_validates`) - their tests moved to test_wizard_onboarding_state.py, which
exercises the real state machine (`layout_broken`/`needs_discover`/
`decisions_pending`/`steady_state`) that replaced them. This file now only covers the
one remaining check: is `ult-repo-layout` installed at all.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_preflight as wp  # noqa: E402


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestCheckPresent(unittest.TestCase):
    """Check 1 (the sole remaining check): is ult-repo-layout installed at all?"""

    def test_missing_skill_md_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(wp.PreflightError) as ctx:
                wp.run_preflight(root)
            msg = str(ctx.exception)
            self.assertIn("ult-repo-layout", msg)
            self.assertIn("-Only", msg)

    def test_skill_md_present_but_scripts_missing_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / ".github" / "skills" / "ult-repo-layout" / "SKILL.md",
                "---\nname: repo-layout\n---\n",
            )
            with self.assertRaises(wp.PreflightError) as ctx:
                wp.run_preflight(root)
            msg = str(ctx.exception)
            self.assertIn("partial or corrupted", msg)

    def test_skill_md_and_validate_layout_present_passes(self):
        """Check 1 no longer cares about anything content-wise (no markers, no
        context-config.yaml, no discovery artifact) - only that ult-repo-layout is
        installed. A totally fresh/unconfigured repo must pass."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / ".github" / "skills" / "ult-repo-layout" / "SKILL.md",
                "---\nname: repo-layout\n---\n",
            )
            _write(
                root / ".github" / "skills" / "ult-repo-layout" / "scripts" / "validate_layout.py",
                "# stub\n",
            )
            wp.run_preflight(root)  # must not raise

    def test_run_preflight_prints_nothing_and_opens_no_socket(self):
        """Success is silent: run_preflight itself must not print or touch the
        network - only main()/the CLI wrapper does I/O, and only on failure."""
        import io
        import contextlib

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / ".github" / "skills" / "ult-repo-layout" / "SKILL.md",
                "---\nname: repo-layout\n---\n",
            )
            _write(
                root / ".github" / "skills" / "ult-repo-layout" / "scripts" / "validate_layout.py",
                "# stub\n",
            )
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                wp.run_preflight(root)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(stderr.getvalue(), "")


class TestMainCLI(unittest.TestCase):
    """main() wraps run_preflight with the actual CLI contract: exit code + stderr
    message, nothing printed on success."""

    def test_main_returns_nonzero_and_prints_stderr_on_failure(self):
        import io
        import contextlib

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = wp.main([str(root)])
            self.assertNotEqual(rc, 0)
            self.assertIn("ult-repo-layout", stderr.getvalue())

    def test_main_returns_zero_on_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / ".github" / "skills" / "ult-repo-layout" / "SKILL.md",
                "---\nname: repo-layout\n---\n",
            )
            _write(
                root / ".github" / "skills" / "ult-repo-layout" / "scripts" / "validate_layout.py",
                "# stub\n",
            )
            rc = wp.main([str(root)])
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
