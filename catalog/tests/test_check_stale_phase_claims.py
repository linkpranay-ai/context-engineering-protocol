"""Tests for check_stale_phase_claims.py (the mechanical gate for the
recurring stale-forward-looking-phase-claim defect class, deferred from the
V3 rerun cycle and implemented in the source-fix session that closed the V4
`/api/stage` concurrency finding). Stdlib unittest only. Run with:

python -m unittest discover -s catalog/tests -v
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_stale_phase_claims as cspc  # noqa: E402


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


class _captured_stdout:
    def __enter__(self):
        import io

        self._old = sys.stdout
        sys.stdout = self._buf = io.StringIO()
        return self._buf

    def __exit__(self, *exc):
        sys.stdout = self._old


class TestCheckStalePhaseClaims(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _init_git_repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_tree_passes(self):
        _write_and_track(
            self.root,
            "notes.md",
            "this file makes no forward-looking staleness claims at all\n",
        )
        with _captured_stdout() as out:
            code = cspc.run_check(self.root)
        self.assertEqual(code, 0)
        self.assertIn(
            "No stale forward-looking-phase-claim violations found", out.getvalue()
        )

    def test_each_calibrated_phrase_is_caught(self):
        # One fixture per pattern, each drawn directly from wording a real
        # historical commit removed (see the module docstring's commit list),
        # so this proves the checker still catches the actual defect shape,
        # not just its own regex in isolation.
        samples = {
            "future Phase": "a future Phase C freshness check can detect this",
            "until Phase": "that endpoint does not exist until Phase 1",
            "disabled by design": "that's disabled by design until Phase C wires it up",
            "not called by anything yet": "**Not called by anything yet.** Phase 0.",
            "registers zero mutating routes": "Phase 0 registers zero mutating routes",
            "will be the first caller": "**Phase 1 will be the first caller**",
            "nothing new to design here": "so Phase 1 has nothing new to design here",
            "this release is read-only": "Phase 0 (this release) is read-only. See S18.",
        }
        for name, line in samples.items():
            with self.subTest(name=name):
                root = Path(tempfile.mkdtemp())
                try:
                    _init_git_repo(root)
                    _write_and_track(root, "module.py", f'"""{line}"""\n')
                    with _captured_stdout() as out:
                        code = cspc.run_check(root)
                    self.assertEqual(code, 1)
                    self.assertIn(f"module.py:1: [{name}]", out.getvalue())
                finally:
                    shutil.rmtree(root, ignore_errors=True)

    def test_ordinary_file_nonexistence_prose_is_not_flagged(self):
        # The false-positive class this checker deliberately does not match:
        # "doesn't exist yet" describing filesystem state, not an unlanded
        # feature. A bare-substring version of this phrase was rejected
        # during design specifically because the live tree has dozens of
        # legitimate hits like these.
        _write_and_track(
            self.root,
            "state.py",
            '"""Load state from `path`, an empty skeleton if it doesn\'t exist yet."""\n'
            "# the file doesn't exist yet or fails to parse\n",
        )
        with _captured_stdout() as out:
            code = cspc.run_check(self.root)
        self.assertEqual(code, 0)

    def test_ordinary_phase_reference_is_not_flagged(self):
        # Plain, current, correct references to a named phase must never
        # trip this - only forward-looking staleness phrasing should.
        _write_and_track(
            self.root,
            "glossary.md",
            "D24 | Browser onboarding wizard, Phase 1 write path. See S18.\n"
            "D22 | Multi-root What-L2, a deferred follow-on, not yet implemented.\n",
        )
        with _captured_stdout() as out:
            code = cspc.run_check(self.root)
        self.assertEqual(code, 0)

    def test_allow_marker_suppresses_the_match(self):
        _write_and_track(
            self.root,
            "notes.md",
            "quoting the old wording for history: 'disabled by design' "
            "<!-- stale-phase-claim-allow: historical quote, not a live claim -->\n",
        )
        with _captured_stdout() as out:
            code = cspc.run_check(self.root)
        self.assertEqual(code, 0)

    def test_untracked_file_is_not_scanned(self):
        (self.root / "scratch.md").write_text(
            "disabled by design, untracked\n", encoding="utf-8"
        )
        _write_and_track(self.root, "notes.md", "nothing stale here\n")
        with _captured_stdout() as out:
            code = cspc.run_check(self.root)
        self.assertEqual(code, 0)

    def test_non_scanned_extension_is_ignored(self):
        _write_and_track(
            self.root, "notes.txt", "disabled by design, but not a scanned type\n"
        )
        with _captured_stdout() as out:
            code = cspc.run_check(self.root)
        self.assertEqual(code, 0)

    def test_html_file_is_scanned(self):
        # static/index.html sits in the same served-UI directory that
        # produced one of the ten historical fix commits (6c61e2c, in its
        # sibling wizard.js) - .html must be in scope, not just .py/.js/.md.
        _write_and_track(
            self.root,
            "static/index.html",
            "<p>this route will be the first caller once wired up</p>\n",
        )
        with _captured_stdout() as out:
            code = cspc.run_check(self.root)
        self.assertEqual(code, 1)
        self.assertIn("static/index.html:1:", out.getvalue())

    def test_a_non_ascii_path_is_scanned_not_silently_dropped(self):
        # A plain `git ls-files` (no -z) quotes and octal-escapes any path
        # containing a non-ASCII byte by default (core.quotePath), which
        # would make _tracked_files() yield a quoted string that doesn't
        # exist on disk -- the path.is_file() filter then drops it, and the
        # file is never scanned for a stale phase claim at all.
        _write_and_track(
            self.root,
            "café-notes.md",
            "that endpoint does not exist until Phase 1\n",
        )
        with _captured_stdout() as out:
            code = cspc.run_check(self.root)
        self.assertEqual(code, 1)
        self.assertIn("café-notes.md:1:", out.getvalue())

    def test_until_phase_catches_the_disabled_until_phase_shape(self):
        # The broader "until Phase" pattern (not just "exist until Phase")
        # exists specifically to catch 6c61e2c's shape: a feature described
        # as disabled/gated "until Phase N", independent of the word
        # "exist". Confirms the widened pattern actually fires on wording
        # the narrower predecessor pattern would have missed.
        _write_and_track(
            self.root,
            "module.py",
            '"""the write endpoint stays disabled until Phase C wires it up."""\n',
        )
        with _captured_stdout() as out:
            code = cspc.run_check(self.root)
        self.assertEqual(code, 1)
        self.assertIn("module.py:1: [until Phase]", out.getvalue())

    def test_a_tracked_path_that_is_not_valid_utf8_fails_with_a_clear_system_exit(self):
        # _tracked_files() decodes git's raw -z stdout manually as UTF-8
        # (see its own docstring) specifically so a tracked path that
        # genuinely isn't valid UTF-8 fails with a clear SystemExit instead
        # of a raw UnicodeDecodeError traceback. Mocking subprocess.run's
        # stdout directly rather than trying to create such a path on disk:
        # this dev machine's filesystem and git tooling can't produce a
        # tracked path with genuinely invalid UTF-8 bytes to begin with
        # (Windows paths are UTF-16 under the hood; Python's own os layer
        # transcodes anything it's given). \xe9 is a lone Latin-1 'e-acute'
        # byte with no valid UTF-8 lead byte before it -- the same shape a
        # legacy Windows-1252-encoded filename would actually produce.
        invalid_stdout = b"module.py\x00caf\xe9-notes.md\x00"
        fake_result = mock.Mock(stdout=invalid_stdout)
        with mock.patch.object(cspc.subprocess, "run", return_value=fake_result):
            with self.assertRaises(SystemExit) as ctx:
                cspc.run_check(self.root)
        self.assertIn("isn't valid UTF-8", str(ctx.exception))

    def test_own_test_file_path_is_exempt_from_the_scan(self):
        _write_and_track(
            self.root,
            "catalog/tests/test_check_stale_phase_claims.py",
            "fixture line saying disabled by design on purpose\n",
        )
        with _captured_stdout() as out:
            code = cspc.run_check(self.root)
        self.assertEqual(code, 0)

        _write_and_track(
            self.root,
            "catalog/tests/test_something_else.py",
            "this sibling file is not exempt: disabled by design\n",
        )
        with _captured_stdout() as out:
            code = cspc.run_check(self.root)
        self.assertEqual(code, 1)
        self.assertIn("test_something_else.py:1:", out.getvalue())


if __name__ == "__main__":
    unittest.main()
