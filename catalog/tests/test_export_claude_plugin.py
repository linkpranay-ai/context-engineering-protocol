"""Tests for export_claude_plugin.py's existing_plugin_files() (a 2026-09
follow-up review, Finding 6: local-only build artifacts under claude-plugin/
must not show up as false "extra" files under --check). Stdlib unittest
only. Run with:

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
        _write_and_track(self.root, ".gitignore", "__pycache__/\n.pytest_cache/\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_gitignored_pycache_under_the_plugin_tree_is_not_reported_as_extra(self):
        # The exact shape this gate exists to catch: running the mirrored
        # skill's own test suite directly against claude-plugin/ leaves
        # __pycache__ behind under a real skill directory. That's a
        # gitignored local artifact, not a stale/extra plugin file, and
        # must not make --check false-fail.
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


if __name__ == "__main__":
    unittest.main()
