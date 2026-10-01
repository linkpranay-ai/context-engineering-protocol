"""Regression suite for wizard_autoscaffold_probe.py (Proposal Sec 9.4/10, "W1:
probe cost"). Stdlib unittest only. Run with:

    python -m unittest discover -s scripts/tests -v

scaffold_state.py is copied fresh from the real
ult-autoscaffold-content/scripts/ at test time (not hand-transcribed), same
convention as test_wizard_tripwire.py copying decision_ledger.py - so these tests
exercise the real probe_size()/filename constants and cannot silently drift from
them.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_autoscaffold_probe as wap  # noqa: E402
import wizard_atomic_write as waw  # noqa: E402


def _find_real_repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        marker = (
            candidate
            / ".github"
            / "skills"
            / "ult-autoscaffold-content"
            / "scripts"
            / "scaffold_state.py"
        )
        if marker.exists():
            return candidate
    raise RuntimeError(
        "could not locate the context-engineering-oss repo root from this test "
        "file's location"
    )


REAL_SCRIPTS_DIR = (
    _find_real_repo_root()
    / ".github"
    / "skills"
    / "ult-autoscaffold-content"
    / "scripts"
)
REAL_SCAFFOLD_STATE = REAL_SCRIPTS_DIR / "scaffold_state.py"
# scaffold_state.py imports this sibling directly (`import
# autoscaffold_atomic_write as aaw`) - both must be copied together or the
# dynamic import in wizard_autoscaffold_probe.py fails with
# ModuleNotFoundError, same as it would for a real partial install.
REAL_ATOMIC_WRITE = REAL_SCRIPTS_DIR / "autoscaffold_atomic_write.py"


def _install_ult_autoscaffold_content(root: Path) -> None:
    scripts_dir = root / ".github" / "skills" / "ult-autoscaffold-content" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(REAL_SCAFFOLD_STATE, scripts_dir / "scaffold_state.py")
    shutil.copy(REAL_ATOMIC_WRITE, scripts_dir / "autoscaffold_atomic_write.py")


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _git_init_with_commit(root: Path) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-q", "-m", "initial")


class TestOwningSkillNotInstalled(unittest.TestCase):
    def test_returns_unknown_when_scaffold_state_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = wap.get_evidence(root)
            self.assertEqual(evidence, wap.UNKNOWN_EVIDENCE)

    def test_writes_no_cache_when_scaffold_state_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wap.get_evidence(root)
            self.assertFalse((root / "cache" / "autoscaffold-content" / "probe.json").exists())


class TestFreshProbeAndCacheWrite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _install_ult_autoscaffold_content(self.root)
        _git_init_with_commit(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_returns_real_probe_size_shape(self):
        evidence = wap.get_evidence(self.root)
        self.assertIsInstance(evidence, dict)
        self.assertIn("grounded_viable", evidence)
        self.assertIn("greenfield", evidence)
        # _git_init_with_commit() commits a top-level README.md, which is a
        # real (non-dot-prefixed) file - scaffold_state._any_real_file_exists()
        # correctly reports this repo as NOT greenfield. Asserting the exact,
        # non-trivial value (rather than just key presence) confirms the real
        # probe_size() ran, not a stub.
        self.assertFalse(evidence["greenfield"])

    def test_writes_cache_file(self):
        wap.get_evidence(self.root)
        cache_path = self.root / "cache" / "autoscaffold-content" / "probe.json"
        self.assertTrue(cache_path.exists())

    def test_cache_file_has_key_and_evidence(self):
        wap.get_evidence(self.root)
        cache_path = self.root / "cache" / "autoscaffold-content" / "probe.json"
        import json

        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        self.assertIn("key", payload)
        self.assertIn("evidence", payload)
        self.assertIn("head", payload["key"])
        self.assertIn("signals", payload["key"])


class TestCacheHit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _install_ult_autoscaffold_content(self.root)
        _git_init_with_commit(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_second_call_does_not_rerun_probe(self):
        first = wap.get_evidence(self.root)
        self.assertIsInstance(first, dict)

        module = wap._import_scaffold_state_module(self.root)
        with patch.object(
            module, "probe_size", side_effect=AssertionError("probe_size should not run on a cache hit")
        ):
            second = wap.get_evidence(self.root)
        self.assertEqual(second, first)


class TestCacheInvalidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _install_ult_autoscaffold_content(self.root)
        _git_init_with_commit(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_head_change_invalidates_cache(self):
        wap.get_evidence(self.root)
        cache_path = self.root / "cache" / "autoscaffold-content" / "probe.json"
        import json

        before = json.loads(cache_path.read_text(encoding="utf-8"))

        (self.root / "CONTRIBUTING.md").write_text("# Contributing\n", encoding="utf-8")
        _git(self.root, "add", "CONTRIBUTING.md")
        _git(self.root, "commit", "-q", "-m", "add contributing")

        evidence = wap.get_evidence(self.root)
        after = json.loads(cache_path.read_text(encoding="utf-8"))

        self.assertNotEqual(before["key"]["head"], after["key"]["head"])
        self.assertIsInstance(evidence, dict)

    def test_signal_file_mtime_change_invalidates_cache_without_head_change(self):
        # Create the signal file, then take a snapshot cache BEFORE committing it
        # (so HEAD is unchanged across the mutation) - only the file's mtime
        # should be what forces a fresh probe.
        contributing = self.root / "CONTRIBUTING.md"
        contributing.write_text("v1\n", encoding="utf-8")
        wap.get_evidence(self.root)  # caches with CONTRIBUTING.md present, untracked

        cache_path = self.root / "cache" / "autoscaffold-content" / "probe.json"
        import json

        before = json.loads(cache_path.read_text(encoding="utf-8"))

        # Touch with a distinctly different mtime (filesystems can coalesce
        # mtimes written in quick succession at low resolution).
        import os
        import time

        new_mtime = time.time() + 5
        os.utime(contributing, (new_mtime, new_mtime))

        wap.get_evidence(self.root)
        after = json.loads(cache_path.read_text(encoding="utf-8"))

        self.assertEqual(before["key"]["head"], after["key"]["head"])
        self.assertNotEqual(before["key"]["signals"], after["key"]["signals"])


class TestTimeoutDegradesToUnknown(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _install_ult_autoscaffold_content(self.root)
        _git_init_with_commit(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_slow_probe_returns_unknown_and_writes_no_cache(self):
        module = wap._import_scaffold_state_module(self.root)

        def _slow_probe(repo_root):
            import time

            time.sleep(0.3)
            return {"grounded_viable": {}, "greenfield": True}

        with patch.object(wap, "_PROBE_BUDGET_SECONDS", 0.05), patch.object(
            module, "probe_size", side_effect=_slow_probe
        ):
            evidence = wap.get_evidence(self.root)

        self.assertEqual(evidence, wap.UNKNOWN_EVIDENCE)
        self.assertFalse((self.root / "cache" / "autoscaffold-content" / "probe.json").exists())


class TestProbeErrorDegradesToUnknown(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _install_ult_autoscaffold_content(self.root)
        _git_init_with_commit(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_probe_exception_returns_unknown_and_writes_no_cache(self):
        module = wap._import_scaffold_state_module(self.root)
        with patch.object(module, "probe_size", side_effect=RuntimeError("boom")):
            evidence = wap.get_evidence(self.root)

        self.assertEqual(evidence, wap.UNKNOWN_EVIDENCE)
        self.assertFalse((self.root / "cache" / "autoscaffold-content" / "probe.json").exists())


class TestNoGitRepo(unittest.TestCase):
    def test_works_without_a_git_repo_head_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_autoscaffold_content(root)

            evidence = wap.get_evidence(root)
            self.assertIsInstance(evidence, dict)

            import json

            cache_path = root / "cache" / "autoscaffold-content" / "probe.json"
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertIsNone(payload["key"]["head"])


class TestCacheWriteFailureIsNonFatal(unittest.TestCase):
    def test_atomic_write_error_does_not_prevent_returning_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_autoscaffold_content(root)
            _git_init_with_commit(root)

            with patch.object(
                waw, "write_text_atomic", side_effect=waw.AtomicWriteError("disk full")
            ):
                evidence = wap.get_evidence(root)

            self.assertIsInstance(evidence, dict)
            self.assertIn("grounded_viable", evidence)


if __name__ == "__main__":
    unittest.main()
