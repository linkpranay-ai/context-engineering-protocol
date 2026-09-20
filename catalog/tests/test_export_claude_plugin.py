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

import locale
import os
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

    def _patched(self):
        return (
            mock.patch.object(ecp, "LIBRARY_ROOT", self.root),
            mock.patch.object(ecp, "SKILLS_DIR", self.root / ".github" / "skills"),
            mock.patch.object(ecp, "CHANGELOG_PATH", self.root / "CHANGELOG.md"),
            mock.patch.object(ecp, "PLUGIN_DIR", self.root / "claude-plugin"),
            mock.patch.object(ecp, "PLUGIN_SKILLS_DIR", self.root / "claude-plugin" / "skills"),
            mock.patch.object(
                ecp, "PLUGIN_MANIFEST_PATH", self.root / "claude-plugin" / ".claude-plugin" / "plugin.json"
            ),
            mock.patch.object(ecp, "PLUGIN_README_PATH", self.root / "claude-plugin" / "README.md"),
        )

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

    def test_source_file_is_a_tracked_symlink_with_a_missing_target_raises_a_specific_error(self):
        # is_file() alone would call a broken symlink "missing on disk"
        # and tell the operator to run `git status` -- which shows
        # nothing wrong, since the symlink itself IS tracked and present.
        # This must get its own message naming the real problem (a
        # missing symlink target), not the generic missing-file one.
        self.tracked_script.unlink()
        try:
            self.tracked_script.symlink_to(self.root / "does-not-exist.py")
        except OSError as exc:
            self.skipTest(f"symlink creation unsupported/unprivileged here: {exc}")
        subprocess.run(
            ["git", "add", ".github/skills/demo-skill/scripts/run.py"], cwd=self.root, check=True
        )

        patches = self._patched()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with self.assertRaises(SystemExit) as ctx:
                ecp.plan()

        self.assertIn("scripts/run.py", str(ctx.exception))
        self.assertIn("tracked symlink", str(ctx.exception))
        self.assertIn("target is missing", str(ctx.exception))
        self.assertNotIn("git status", str(ctx.exception))


class TestTrackedSkillFiles(unittest.TestCase):
    """tracked_skill_files() decodes git's raw -z output as UTF-8 bytes
    directly, rather than via subprocess.run(text=True), specifically so
    that a \\r byte inside a path is preserved rather than translated to
    \\n by universal-newline handling.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_literal_cr_byte_in_a_tracked_path_is_not_translated_to_a_newline(self):
        # A real file with \r in its name can't be created on this
        # Windows test environment (illegal on NTFS), even though it's a
        # legal POSIX filename -- so git's raw -z output is faked here to
        # exercise the decode path directly, independent of what this
        # filesystem can hold.
        skill_dir = self.root / ".github" / "skills"
        raw_entry = ".github/skills/demo-skill/odd\rname.md".encode("utf-8")
        raw_stdout = raw_entry + b"\x00"

        def fake_run(*args, **kwargs):
            # Mirrors real subprocess.run behavior closely enough to prove
            # this test actually depends on the fix, not just on which
            # kwargs get passed: text=True decodes AND applies
            # universal-newline translation (\r -> \n), same as the real
            # implementation this replaces -- capture_output-only returns
            # raw, untranslated bytes. When encoding isn't given explicitly,
            # real subprocess.run(text=True) falls back to
            # locale.getpreferredencoding(False), not a hardcoded "utf-8" --
            # matched here rather than assumed, so this fake can't silently
            # hide the locale-decoding hazard on a box whose preferred
            # encoding isn't UTF-8.
            if kwargs.get("text"):
                encoding = kwargs.get("encoding") or locale.getpreferredencoding(False)
                decoded = raw_stdout.decode(encoding)
                return mock.Mock(stdout=decoded.replace("\r\n", "\n").replace("\r", "\n"))
            return mock.Mock(stdout=raw_stdout)

        with mock.patch.object(ecp, "LIBRARY_ROOT", self.root), mock.patch.object(
            ecp, "SKILLS_DIR", skill_dir
        ), mock.patch.object(ecp.subprocess, "run", side_effect=fake_run):
            result = ecp.tracked_skill_files("demo-skill")

        self.assertEqual(result, [Path("odd\rname.md")])

    def test_a_real_non_ascii_path_is_correctly_reported_not_silently_dropped(self):
        # Exercises the actual `git ls-files -z --` call end to end, no
        # subprocess mock -- mirrors TestExistingPluginFiles's equivalent
        # test. The \r test above mocks subprocess.run and only varies the
        # `text` kwarg, so it can't detect a regression that dropped the -z
        # flag itself (plain `git ls-files` quotes/octal-escapes non-ASCII
        # paths by default, which would make this file come back under a
        # quoted name and fail the exact-match assert below).
        _init_git_repo(self.root)
        _write_and_track(
            self.root, ".github/skills/demo-skill/café.md", "non-ascii filename\n"
        )

        with mock.patch.object(ecp, "LIBRARY_ROOT", self.root), mock.patch.object(
            ecp, "SKILLS_DIR", self.root / ".github" / "skills"
        ):
            result = ecp.tracked_skill_files("demo-skill")

        self.assertEqual(result, [Path("café.md")])


class TestIncludedSkillDirs(unittest.TestCase):
    """included_skill_dirs() must agree with tracked_skill_files() about
    which skills actually have exportable content -- both are supposed to
    be git-driven, per this module's own docstring.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _init_git_repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_skill_dir_with_an_untracked_skill_md_is_excluded(self):
        # A SKILL.md present on disk but never `git add`ed (e.g. a skill
        # still being drafted) must not be advertised in the generated
        # README/manifest -- tracked_skill_files() would export zero
        # files for it, so a README entry for it would document a
        # command that ships nothing.
        tracked_dir = self.root / ".github" / "skills" / "tracked-skill"
        _write_and_track(
            self.root, ".github/skills/tracked-skill/SKILL.md", '---\ndescription: "Tracked"\n---\n\nBody.\n'
        )
        untracked_dir = self.root / ".github" / "skills" / "draft-skill"
        untracked_dir.mkdir(parents=True)
        (untracked_dir / "SKILL.md").write_text('---\ndescription: "Draft"\n---\n\nBody.\n', encoding="utf-8")

        with mock.patch.object(ecp, "LIBRARY_ROOT", self.root), mock.patch.object(
            ecp, "SKILLS_DIR", self.root / ".github" / "skills"
        ):
            result = ecp.included_skill_dirs()

        self.assertEqual(result, ["tracked-skill"])
        self.assertNotIn("draft-skill", result)

    def test_result_is_sorted_by_name_regardless_of_iterdir_order(self):
        # iterdir() order is filesystem-dependent, not alphabetical -- the
        # function's own docstring says the explicit sort-by-name exists so
        # plugin.json/README.md output is identical across the platforms
        # this repo's CI runs on. Fakes iterdir() to hand back entries in
        # reverse-alphabetical order, deliberately fighting whatever order
        # this filesystem would naturally give, so the assertion below can
        # only pass if the sort is doing real work -- not incidentally
        # matching already-sorted disk order.
        names = ["zeta-skill", "alpha-skill", "mid-skill"]
        for name in names:
            _write_and_track(
                self.root, f".github/skills/{name}/SKILL.md",
                f'---\ndescription: "{name}"\n---\n\nBody.\n',
            )

        skills_dir = self.root / ".github" / "skills"
        real_iterdir = Path.iterdir

        def reversed_iterdir(path_self):
            entries = list(real_iterdir(path_self))
            if path_self == skills_dir:
                return iter(sorted(entries, key=lambda p: p.name, reverse=True))
            return iter(entries)

        with mock.patch.object(ecp, "LIBRARY_ROOT", self.root), mock.patch.object(
            ecp, "SKILLS_DIR", skills_dir
        ), mock.patch.object(Path, "iterdir", reversed_iterdir):
            result = ecp.included_skill_dirs()

        self.assertEqual(result, ["alpha-skill", "mid-skill", "zeta-skill"])


class TestDecodeGitLsFilesZ(unittest.TestCase):
    """_decode_git_ls_files_z() decodes git's raw -z stdout as UTF-8
    directly -- a tracked path that genuinely isn't valid UTF-8 must raise a
    clear SystemExit naming the problem, not a raw UnicodeDecodeError
    traceback.
    """

    def test_non_utf8_bytes_raise_a_clear_system_exit_not_a_raw_traceback(self):
        invalid = b"\xff\xfe not valid utf-8\x00"

        with self.assertRaises(SystemExit) as ctx:
            ecp._decode_git_ls_files_z(invalid)

        self.assertIn("isn't valid UTF-8", str(ctx.exception))


class TestPlanSymlinkToNonFile(unittest.TestCase):
    """plan()'s third symlink branch: a tracked symlink whose target exists
    but isn't a regular file (here, a directory) must raise its own specific
    error, not fall through to the generic tracked-but-missing message that
    is_file() alone would produce.
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

    def _patched(self):
        return (
            mock.patch.object(ecp, "LIBRARY_ROOT", self.root),
            mock.patch.object(ecp, "SKILLS_DIR", self.root / ".github" / "skills"),
            mock.patch.object(ecp, "CHANGELOG_PATH", self.root / "CHANGELOG.md"),
            mock.patch.object(ecp, "PLUGIN_DIR", self.root / "claude-plugin"),
            mock.patch.object(ecp, "PLUGIN_SKILLS_DIR", self.root / "claude-plugin" / "skills"),
            mock.patch.object(
                ecp, "PLUGIN_MANIFEST_PATH", self.root / "claude-plugin" / ".claude-plugin" / "plugin.json"
            ),
            mock.patch.object(ecp, "PLUGIN_README_PATH", self.root / "claude-plugin" / "README.md"),
        )

    def test_source_file_is_a_tracked_symlink_to_a_directory_raises_a_specific_error(self):
        self.tracked_script.unlink()
        target_dir = self.root / "some-directory"
        target_dir.mkdir()
        try:
            self.tracked_script.symlink_to(target_dir)
        except OSError as exc:
            self.skipTest(f"symlink creation unsupported/unprivileged here: {exc}")
        subprocess.run(
            ["git", "add", ".github/skills/demo-skill/scripts/run.py"], cwd=self.root, check=True
        )

        patches = self._patched()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with self.assertRaises(SystemExit) as ctx:
                ecp.plan()

        self.assertIn("scripts/run.py", str(ctx.exception))
        self.assertIn("tracked symlink", str(ctx.exception))
        self.assertIn("other than", str(ctx.exception))
        self.assertNotIn("missing on disk", str(ctx.exception))


class TestWriteRemovesStraySymlinks(unittest.TestCase):
    """--write's symlink-ancestor-removal branch: every path under
    claude-plugin/ is generator-owned, so a symlink anywhere in a generated
    path's ancestry -- not just at the leaf -- must be removed before
    mkdir(parents=True)/write_bytes() run there. Windows additionally
    requires rmdir() rather than unlink() for a *directory* symlink/
    junction (unlink() raises PermissionError there), so both the leaf-file
    and ancestor-directory shapes get their own test.
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
        _write_and_track(self.root, ".github/skills/demo-skill/scripts/run.py", "print('hi')\n")

    def tearDown(self):
        self._tmp.cleanup()

    def _patched(self):
        return (
            mock.patch.object(ecp, "LIBRARY_ROOT", self.root),
            mock.patch.object(ecp, "SKILLS_DIR", self.root / ".github" / "skills"),
            mock.patch.object(ecp, "CHANGELOG_PATH", self.root / "CHANGELOG.md"),
            mock.patch.object(ecp, "PLUGIN_DIR", self.root / "claude-plugin"),
            mock.patch.object(ecp, "PLUGIN_SKILLS_DIR", self.root / "claude-plugin" / "skills"),
            mock.patch.object(
                ecp, "PLUGIN_MANIFEST_PATH", self.root / "claude-plugin" / ".claude-plugin" / "plugin.json"
            ),
            mock.patch.object(ecp, "PLUGIN_README_PATH", self.root / "claude-plugin" / "README.md"),
        )

    def test_write_removes_a_stray_file_symlink_at_a_generated_leaf_path(self):
        leaf = self.root / "claude-plugin" / "skills" / "demo-skill" / "scripts" / "run.py"
        leaf.parent.mkdir(parents=True)
        real_file = self.root / "elsewhere.py"
        real_file.write_text("not the generated content\n", encoding="utf-8")
        try:
            leaf.symlink_to(real_file)
        except OSError as exc:
            self.skipTest(f"symlink creation unsupported/unprivileged here: {exc}")

        patches = self._patched()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with mock.patch.object(sys, "argv", ["export_claude_plugin.py", "--write"]):
                ecp.main()

        self.assertFalse(leaf.is_symlink())
        self.assertEqual(leaf.read_text(encoding="utf-8"), "print('hi')\n")

    def test_write_removes_a_stray_directory_symlink_at_a_generated_ancestor(self):
        # A symlinked *ancestor directory* -- not just the leaf file -- must
        # also be removed before mkdir(parents=True) walks through it.
        ancestor = self.root / "claude-plugin" / "skills" / "demo-skill"
        ancestor.parent.mkdir(parents=True)
        real_dir = self.root / "elsewhere-dir"
        real_dir.mkdir()
        (real_dir / "decoy.txt").write_text("should not survive\n", encoding="utf-8")
        try:
            ancestor.symlink_to(real_dir, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink creation unsupported/unprivileged here: {exc}")

        patches = self._patched()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with mock.patch.object(sys, "argv", ["export_claude_plugin.py", "--write"]):
                ecp.main()

        leaf = ancestor / "scripts" / "run.py"
        self.assertFalse(ancestor.is_symlink())
        self.assertEqual(leaf.read_text(encoding="utf-8"), "print('hi')\n")


class TestWriteSymlinkRemovalChoosesRmdirOrUnlink(unittest.TestCase):
    """Same removal branch as TestWriteRemovesStraySymlinks, exercised
    without creating a real OS symlink: this dev machine has no privilege
    to create one at all (confirmed directly -- plain os.symlink() here
    raises WinError 1314, "A required privilege is not held by the
    client"), which is also why every symlink-dependent test above skips
    here rather than passing. _first_symlink_under_plugin_dir() is mocked
    to hand back a fake stray-symlink object, and
    _is_windows_directory_symlink() itself is mocked directly (it calls
    os.lstat() on its argument, which a mock object can't stand in for --
    that function's own real-filesystem behavior is exercised separately
    by TestIsWindowsDirectorySymlink below), so the
    _is_windows_directory_symlink()-selects-rmdir()-vs-unlink() decision
    inside --write's removal branch itself is exercised and provably
    non-vacuous on this machine, not only on a platform where symlink
    creation happens to be unprivileged.
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
        _write_and_track(self.root, ".github/skills/demo-skill/scripts/run.py", "print('hi')\n")

    def tearDown(self):
        self._tmp.cleanup()

    def _patched(self):
        return (
            mock.patch.object(ecp, "LIBRARY_ROOT", self.root),
            mock.patch.object(ecp, "SKILLS_DIR", self.root / ".github" / "skills"),
            mock.patch.object(ecp, "CHANGELOG_PATH", self.root / "CHANGELOG.md"),
            mock.patch.object(ecp, "PLUGIN_DIR", self.root / "claude-plugin"),
            mock.patch.object(ecp, "PLUGIN_SKILLS_DIR", self.root / "claude-plugin" / "skills"),
            mock.patch.object(
                ecp, "PLUGIN_MANIFEST_PATH", self.root / "claude-plugin" / ".claude-plugin" / "plugin.json"
            ),
            mock.patch.object(ecp, "PLUGIN_README_PATH", self.root / "claude-plugin" / "README.md"),
        )

    def _run_write_with_fake_stray_symlink(self, is_windows_directory_symlink_value):
        fake_symlink = mock.NonCallableMock(spec=Path)
        patches = self._patched()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with mock.patch.object(
                ecp, "_first_symlink_under_plugin_dir", return_value=fake_symlink
            ):
                with mock.patch.object(
                    ecp,
                    "_is_windows_directory_symlink",
                    return_value=is_windows_directory_symlink_value,
                ):
                    with mock.patch.object(sys, "argv", ["export_claude_plugin.py", "--write"]):
                        ecp.main()
        return fake_symlink

    def test_directory_symlink_is_removed_with_rmdir_not_unlink(self):
        fake_symlink = self._run_write_with_fake_stray_symlink(is_windows_directory_symlink_value=True)
        fake_symlink.rmdir.assert_called()
        fake_symlink.unlink.assert_not_called()

    def test_file_symlink_is_removed_with_unlink_not_rmdir(self):
        fake_symlink = self._run_write_with_fake_stray_symlink(is_windows_directory_symlink_value=False)
        fake_symlink.unlink.assert_called()


class TestIsWindowsDirectorySymlink(unittest.TestCase):
    """_is_windows_directory_symlink() itself, against real filesystem
    entries rather than a mock -- the test above patches this function out
    entirely, so its own os.lstat()-based bit check needs separate,
    non-mocked coverage. Symlink creation is unprivileged on this dev
    machine (see TestWriteSymlinkRemovalChoosesRmdirOrUnlink), so this
    exercises the same FILE_ATTRIBUTE_DIRECTORY check the function applies
    to a stray symlink against a real directory and a real file instead --
    lstat() reports the same attribute bit for either, since a symlink and
    the directory/file it targets are just two different entries lstat()
    can be pointed at.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_posix_is_always_false_without_touching_the_filesystem(self):
        with mock.patch.object(os, "name", "posix"):
            self.assertFalse(ecp._is_windows_directory_symlink(self.root / "does-not-exist"))

    @unittest.skipUnless(os.name == "nt", "st_file_attributes is a Windows-only os.stat_result field")
    def test_windows_directory_entry_is_true(self):
        directory = self.root / "a-directory"
        directory.mkdir()
        self.assertTrue(ecp._is_windows_directory_symlink(directory))

    @unittest.skipUnless(os.name == "nt", "st_file_attributes is a Windows-only os.stat_result field")
    def test_windows_file_entry_is_false(self):
        file_path = self.root / "a-file.txt"
        file_path.write_text("hi\n", encoding="utf-8")
        self.assertFalse(ecp._is_windows_directory_symlink(file_path))


class TestPlanSymlinkToNonFileMocked(unittest.TestCase):
    """Same branch as TestPlanSymlinkToNonFile, exercised without a real OS
    symlink (unprivileged on this machine -- see
    TestWriteSymlinkRemovalChoosesRmdirOrUnlink) by faking is_symlink()/
    exists()/is_file() for just the one path under test, so this branch's
    non-vacuity is provable here too.
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

    def _patched(self):
        return (
            mock.patch.object(ecp, "LIBRARY_ROOT", self.root),
            mock.patch.object(ecp, "SKILLS_DIR", self.root / ".github" / "skills"),
            mock.patch.object(ecp, "CHANGELOG_PATH", self.root / "CHANGELOG.md"),
            mock.patch.object(ecp, "PLUGIN_DIR", self.root / "claude-plugin"),
            mock.patch.object(ecp, "PLUGIN_SKILLS_DIR", self.root / "claude-plugin" / "skills"),
            mock.patch.object(
                ecp, "PLUGIN_MANIFEST_PATH", self.root / "claude-plugin" / ".claude-plugin" / "plugin.json"
            ),
            mock.patch.object(ecp, "PLUGIN_README_PATH", self.root / "claude-plugin" / "README.md"),
        )

    def test_source_file_is_a_tracked_symlink_to_a_directory_raises_a_specific_error(self):
        real_is_symlink = Path.is_symlink
        real_exists = Path.exists
        real_is_file = Path.is_file
        tracked_script = self.tracked_script

        def fake_is_symlink(path_self):
            if path_self == tracked_script:
                return True
            return real_is_symlink(path_self)

        def fake_exists(path_self):
            if path_self == tracked_script:
                return True
            return real_exists(path_self)

        def fake_is_file(path_self):
            if path_self == tracked_script:
                return False
            return real_is_file(path_self)

        patches = self._patched()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with mock.patch.object(Path, "is_symlink", fake_is_symlink), mock.patch.object(
                Path, "exists", fake_exists
            ), mock.patch.object(Path, "is_file", fake_is_file):
                with self.assertRaises(SystemExit) as ctx:
                    ecp.plan()

        self.assertIn("scripts/run.py", str(ctx.exception))
        self.assertIn("tracked symlink", str(ctx.exception))
        self.assertIn("other than", str(ctx.exception))
        self.assertNotIn("missing on disk", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
