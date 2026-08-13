"""Regression suite for wizard_discover.py (D24 Phase 2, §18.14). Stdlib unittest
only. Run with:

    python -m unittest discover -s scripts/tests -v

discover_layers.py/confirm_layers.py/layout_decision_grammar.py are copied fresh from
the real ult-repo-layout/scripts/ at test time (not hand-transcribed stubs), same
convention as test_wizard_apply.py - so run_discover is exercised against the real
discover_layers.run_discovery/confirm_layers.parse_artifact, not a paraphrase that
could silently drift from them.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_content_hash as wch  # noqa: E402
import wizard_discover as wd  # noqa: E402


def _find_real_repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        marker = (
            candidate
            / ".github"
            / "skills"
            / "ult-repo-layout"
            / "scripts"
            / "validate_layout.py"
        )
        if marker.exists():
            return candidate
    raise RuntimeError(
        "could not locate the context-engineering-oss repo root from this test "
        "file's location"
    )


REAL_REPO_ROOT = _find_real_repo_root()
REAL_SCRIPTS_DIR = REAL_REPO_ROOT / ".github" / "skills" / "ult-repo-layout" / "scripts"


def _install_ult_repo_layout(repo_root: Path) -> None:
    scripts_dir = repo_root / ".github" / "skills" / "ult-repo-layout" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "validate_layout.py",
        "discover_layers.py",
        "layout_decision_grammar.py",
        "confirm_layers.py",
    ):
        shutil.copy(REAL_SCRIPTS_DIR / name, scripts_dir / name)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


WHAT_L2_TITLE = "What-L2 - project's own requirements/spec docs"
HOW_L2_TITLE = "How-L2 - this project's own compiled conventions"

STAGED_ARTIFACT = f"""# Context Layout Discovery - test-repo

## {WHAT_L2_TITLE}
**Status:** enabled by default.

    decision: CONFIRM: docs/reqs/   # CONFIRM: docs/reqs/ | CUSTOM: <path> | SKIP

## {HOW_L2_TITLE}
**Status:** enabled by default.

    decision: PENDING   # CONFIRM: .github/ | CUSTOM: <path> | SKIP
"""

ALL_CONFIRMED_ARTIFACT = f"""# Context Layout Discovery - test-repo

## {WHAT_L2_TITLE}
**Status:** enabled by default.

    decision: CONFIRM: docs/reqs/   # CONFIRMED 2026-01-01
"""


class TestFirstRun(unittest.TestCase):
    def test_first_run_with_no_prior_artifact_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            artifact_path = root / "context-layout-discovery.md"
            self.assertFalse(artifact_path.exists())

            result = wd.run_discover(root, artifact_path, loaded_artifact_hash=None)

            self.assertTrue(artifact_path.exists())
            self.assertIsNotNone(result.artifact_hash_after)
            self.assertEqual(result.discarded_staged_sections, [])


class TestStaleArtifactGuard(unittest.TestCase):
    def test_wrong_loaded_hash_raises_stale_before_anything_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            artifact_path = root / "context-layout-discovery.md"
            _write(artifact_path, STAGED_ARTIFACT)

            with self.assertRaises(wd.StaleArtifactError):
                wd.run_discover(root, artifact_path, loaded_artifact_hash="not-the-real-hash")

            # Refused before ever calling discover_layers - artifact untouched.
            self.assertEqual(artifact_path.read_text(encoding="utf-8"), STAGED_ARTIFACT)

    def test_wrong_loaded_hash_still_raises_stale_even_with_force(self):
        """The freshness check runs before the staged-decision guard - force=True
        does not bypass it."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            artifact_path = root / "context-layout-discovery.md"
            _write(artifact_path, STAGED_ARTIFACT)

            with self.assertRaises(wd.StaleArtifactError):
                wd.run_discover(
                    root, artifact_path, loaded_artifact_hash="not-the-real-hash", force=True
                )


class TestAtRiskDecisionsGuard(unittest.TestCase):
    def test_staged_field_blocks_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            artifact_path = root / "context-layout-discovery.md"
            _write(artifact_path, STAGED_ARTIFACT)
            current_hash = wch.hash_artifact(artifact_path)

            with self.assertRaises(wd.AtRiskDecisionsError) as ctx:
                wd.run_discover(root, artifact_path, loaded_artifact_hash=current_hash)

            self.assertIn(WHAT_L2_TITLE, ctx.exception.at_risk_sections)
            # Refused before calling discover_layers - artifact untouched.
            self.assertEqual(artifact_path.read_text(encoding="utf-8"), STAGED_ARTIFACT)

    def test_force_true_proceeds_and_reports_discarded_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            artifact_path = root / "context-layout-discovery.md"
            _write(artifact_path, STAGED_ARTIFACT)
            current_hash = wch.hash_artifact(artifact_path)

            result = wd.run_discover(
                root, artifact_path, loaded_artifact_hash=current_hash, force=True
            )

            self.assertIn(WHAT_L2_TITLE, result.discarded_staged_sections)
            self.assertIsNotNone(result.artifact_hash_after)
            self.assertNotEqual(result.artifact_hash_after, current_hash)


class TestConfirmedSectionsPassThrough(unittest.TestCase):
    def test_all_confirmed_artifact_does_not_trigger_at_risk_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            artifact_path = root / "context-layout-discovery.md"
            _write(artifact_path, ALL_CONFIRMED_ARTIFACT)
            current_hash = wch.hash_artifact(artifact_path)

            # Must not raise AtRiskDecisionsError - every field is already
            # CONFIRMED-stamped, so discover_layers.py's own drift tracking
            # carries the section forward untouched.
            result = wd.run_discover(root, artifact_path, loaded_artifact_hash=current_hash)

            self.assertEqual(result.discarded_staged_sections, [])
            after_text = artifact_path.read_text(encoding="utf-8")
            self.assertIn("CONFIRMED 2026-01-01", after_text)


if __name__ == "__main__":
    unittest.main()
