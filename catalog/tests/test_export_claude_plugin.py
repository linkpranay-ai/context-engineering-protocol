"""Tests for export_claude_plugin.py's tracked_skill_files() and
existing_plugin_files() -- both use `git ls-files` instead of a plain
filesystem walk, so local-only build artifacts under a skill dir or under
claude-plugin/ (__pycache__, .pytest_cache, etc.) never show up as false
"extra"/"stale" files under --check, and so a path tracked in git but
missing on disk never crashes --write's cleanup pass or plan()'s read.
Born from several 2026-09 follow-up reviews. Stdlib unittest only. Run
with:

python -m unittest discover -s catalog/tests -v
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import export_claude_plugin as ecp  # noqa: E402


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


class TestExistingPluginFiles(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _init_git_repo(self.root)
        # Mirrors the real repo's ignore rules for realism, but note this
        # isn't why the pycache test below passes: bare `git ls-files`
        # only lists tracked (index) entries regardless of gitignore
        # status, so an untracked file is excluded either way.
        _write_and_track(self.root, ".gitignore", "__pycache__/\n.pytest_cache/\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_gitignored_pycache_under_the_plugin_tree_is_not_reported_as_extra(self):
        # The exact shape this gate exists to catch: running the mirrored
        # skill's own test suite directly against claude-plugin/ leaves
        # __pycache__ behind under a real skill directory. It's excluded
        # here because it's untracked -- bare `git ls-files` only lists
        # index entries -- and in the real repo it's also gitignored,
        # which is why nobody ever `git add`s it in the first place.
        # Either way, it must not make --check false-fail.
        _write_and_track(
            self.root,
            "claude-plugin/skills/demo/server.py",
            "print('tracked plugin file')\n",
        )
        pycache_file = (
            self.root
            / "claude-plugin"
            / "skills"
            / "demo"
            / "__pycache__"
            / "server.cpython-311.pyc"
        )
        pycache_file.parent.mkdir(parents=True, exist_ok=True)
        pycache_file.write_bytes(b"not a real pyc, just untracked bytes")

        with mock.patch.object(ecp, "LIBRARY_ROOT", self.root), mock.patch.object(
            ecp, "PLUGIN_DIR", self.root / "claude-plugin"
        ):
            result = ecp.existing_plugin_files()

        self.assertIn(self.root / "claude-plugin" / "skills" / "demo" / "server.py", result)
        self.assertNotIn(pycache_file, result)

    def test_tracked_file_under_the_plugin_tree_is_reported(self):
        # Baseline: a git-tracked file under claude-plugin/ (the normal,
        # committed case) must still surface, so --check has a chance to
        # flag it if it's no longer part of the expected export.
        tracked = self.root / "claude-plugin" / "skills" / "demo" / "server.py"
        _write_and_track(self.root, "claude-plugin/skills/demo/server.py", "print('tracked')\n")

        with mock.patch.object(ecp, "LIBRARY_ROOT", self.root), mock.patch.object(
            ecp, "PLUGIN_DIR", self.root / "claude-plugin"
        ):
            result = ecp.existing_plugin_files()

        self.assertEqual(result, {tracked})

    def test_missing_plugin_dir_returns_empty_set(self):
        with mock.patch.object(ecp, "LIBRARY_ROOT", self.root), mock.patch.object(
            ecp, "PLUGIN_DIR", self.root / "claude-plugin"
        ):
            self.assertEqual(ecp.existing_plugin_files(), set())

    def test_file_tracked_in_the_index_but_deleted_from_disk_is_not_reported(self):
        # git ls-files lists index entries regardless of whether the
        # worktree file is actually there -- a file that's tracked, then
        # deleted from disk without `git rm` (e.g. a manual cleanup that
        # forgot to stage the deletion), must not come back from this
        # function, or --write's `path.unlink()` cleanup pass crashes with
        # FileNotFoundError trying to remove a path that doesn't exist.
        tracked = self.root / "claude-plugin" / "skills" / "demo" / "server.py"
        _write_and_track(self.root, "claude-plugin/skills/demo/server.py", "print('tracked')\n")
        tracked.unlink()

        with mock.patch.object(ecp, "LIBRARY_ROOT", self.root), mock.patch.object(
            ecp, "PLUGIN_DIR", self.root / "claude-plugin"
        ):
            result = ecp.existing_plugin_files()

        self.assertEqual(result, set())
        # Mirrors main()'s --write cleanup loop exactly (`for path in
        # extras: path.unlink()`) -- makes the link between "this function
        # excludes the deleted-but-tracked path" and "so --write's cleanup
        # loop can't crash on it" mechanically explicit, not just implied.
        for path in result:
            path.unlink()

    def test_non_ascii_path_is_correctly_reported_not_silently_dropped(self):
        # A plain `git ls-files` quotes and octal-escapes any path
        # containing a non-ASCII byte by default (core.quotePath), so
        # reading its output with plain newline-splitting would either
        # miss the real path entirely or return a garbled quoted string.
        # -z avoids the quoting outright, so the real path comes back
        # untouched.
        tracked = self.root / "claude-plugin" / "skills" / "demo" / "café.md"
        _write_and_track(self.root, "claude-plugin/skills/demo/café.md", "non-ascii filename\n")

        with mock.patch.object(ecp, "LIBRARY_ROOT", self.root), mock.patch.object(
            ecp, "PLUGIN_DIR", self.root / "claude-plugin"
        ):
            result = ecp.existing_plugin_files()

        self.assertEqual(result, {tracked})

    def test_symlink_tracked_in_the_index_with_a_missing_target_is_still_reported(self):
        # is_file() alone follows symlinks -- a tracked symlink whose
        # target no longer exists would look exactly like the tracked-
        # but-deleted-from-disk case to is_file() and get silently
        # dropped, leaving a broken symlink that --write's cleanup pass
        # never gets a chance to remove. is_symlink() catches that case.
        link_path = self.root / "claude-plugin" / "skills" / "demo" / "broken-link.md"
        link_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            link_path.symlink_to(self.root / "does-not-exist.md")
        except OSError as exc:
            self.skipTest(f"symlink creation unsupported/unprivileged here: {exc}")
        subprocess.run(
            ["git", "add", "claude-plugin/skills/demo/broken-link.md"], cwd=self.root, check=True
        )

        with mock.patch.object(ecp, "LIBRARY_ROOT", self.root), mock.patch.object(
            ecp, "PLUGIN_DIR", self.root / "claude-plugin"
        ):
            result = ecp.existing_plugin_files()

        self.assertEqual(result, {link_path})


class TestPlanMissingSourceFile(unittest.TestCase):
    """plan() reads tracked_skill_files() entries via src.read_bytes() --
    a file tracked in git but removed from disk without `git rm` must not
    crash that read with a raw FileNotFoundError traceback.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _init_git_repo(self.root)
        _write_and_track(self.root, "CHANGELOG.md", "# Changelog\n\n## [1.0.0] - 2026-01-01\n\nInitial.\n")
        _write_and_track(
            self.root,
            ".github/skills/demo-skill/SKILL.md",
            '---\ndescription: "Demo skill"\n---\n\nBody.\n',
        )
        self.tracked_script = self.root / ".github" / "skills" / "demo-skill" / "scripts" / "run.py"
        _write_and_track(self.root, ".github/skills/demo-skill/scripts/run.py", "print('hi')\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_source_file_tracked_but_deleted_from_disk_raises_a_clear_error(self):
        self.tracked_script.unlink()

        with mock.patch.object(ecp, "LIBRARY_ROOT", self.root), mock.patch.object(
            ecp, "SKILLS_DIR", self.root / ".github" / "skills"
        ), mock.patch.object(ecp, "CHANGELOG_PATH", self.root / "CHANGELOG.md"), mock.patch.object(
            ecp, "PLUGIN_DIR", self.root / "claude-plugin"
        ), mock.patch.object(
            ecp, "PLUGIN_SKILLS_DIR", self.root / "claude-plugin" / "skills"
        ), mock.patch.object(
            ecp, "PLUGIN_MANIFEST_PATH", self.root / "claude-plugin" / ".claude-plugin" / "plugin.json"
        ), mock.patch.object(
            ecp, "PLUGIN_README_PATH", self.root / "claude-plugin" / "README.md"
        ):
            with self.assertRaises(SystemExit) as ctx:
                ecp.plan()

        self.assertIn("scripts/run.py", str(ctx.exception))
        self.assertIn("tracked by git but missing on disk", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
