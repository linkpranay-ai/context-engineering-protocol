"""Regression suite for wizard_tripwire.py (D24 §18.7, locked). Stdlib unittest
only. Run with:

    python -m unittest discover -s scripts/tests -v

decision_ledger.py is copied fresh from the real
ult-institutional-memory-distill/scripts/ at test time (not hand-transcribed), same
convention as test_wizard_layout_source.py copying validate_layout.py/
discover_layers.py - so these tests exercise the real load_ledger/validate_ledger and
cannot silently drift from them. SlotState is imported (not hand-duplicated) from
wizard_layout_source.py, since it's the exact shape read_slots() actually hands this
module in production.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_tripwire as wt  # noqa: E402
from wizard_layout_source import SlotState  # noqa: E402


def _find_real_repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        marker = (
            candidate
            / ".github"
            / "skills"
            / "ult-institutional-memory-distill"
            / "scripts"
            / "decision_ledger.py"
        )
        if marker.exists():
            return candidate
    raise RuntimeError(
        "could not locate the context-engineering-oss repo root from this test "
        "file's location"
    )


REAL_REPO_ROOT = _find_real_repo_root()
REAL_SKILL_DIR = REAL_REPO_ROOT / ".github" / "skills" / "ult-institutional-memory-distill"
REAL_SKILL_MD = REAL_SKILL_DIR / "SKILL.md"
REAL_DECISION_LEDGER = REAL_SKILL_DIR / "scripts" / "decision_ledger.py"


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _install_ult_institutional_memory_distill(root: Path, with_script: bool = True) -> None:
    skill_dir = root / ".github" / "skills" / "ult-institutional-memory-distill"
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(REAL_SKILL_MD, skill_dir / "SKILL.md")
    if with_script:
        shutil.copy(REAL_DECISION_LEDGER, scripts_dir / "decision_ledger.py")


def _default_slot_state(default_path: str) -> SlotState:
    """An uninitialized slot - no marker registers it yet, only resolve_default's
    fallback is available (matches what read_slots() hands back for a decision_ledger
    slot with no marker)."""
    return SlotState(
        slot="decision_ledger",
        owning_skill="ult-institutional-memory-distill",
        initialized=False,
        resolved_paths=[],
        default_path=default_path,
    )


def _initialized_slot_state(resolved_path: str, default_path: str) -> SlotState:
    return SlotState(
        slot="decision_ledger",
        owning_skill="ult-institutional-memory-distill",
        initialized=True,
        resolved_paths=[resolved_path],
        default_path=default_path,
    )


class TestUnavailable(unittest.TestCase):
    def test_none_slot_is_unavailable_owning_skill_not_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = wt.read_summary(tmp, None)
            self.assertFalse(summary.available)
            self.assertIn("not installed", summary.unavailable_reason)

    def test_skill_md_present_but_script_missing_is_unavailable_partial_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_institutional_memory_distill(root, with_script=False)
            slot = _default_slot_state("starter_kit/decision_ledger/DECISION-LEDGER.json")
            summary = wt.read_summary(root, slot)
            self.assertFalse(summary.available)
            self.assertIn("partial", summary.unavailable_reason)


class TestAvailableEmptyLedger(unittest.TestCase):
    def test_no_marker_uses_default_path_and_loads_as_empty_not_error(self):
        """A nonexistent ledger file is a legitimate empty-project state, per
        decision_ledger.load_ledger's own docstring - not an unavailable/error state."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_institutional_memory_distill(root)
            slot = _default_slot_state("starter_kit/decision_ledger/DECISION-LEDGER.json")
            summary = wt.read_summary(root, slot)
            self.assertTrue(summary.available)
            self.assertFalse(summary.initialized)
            self.assertEqual(
                summary.ledger_path, "starter_kit/decision_ledger/DECISION-LEDGER.json"
            )
            self.assertEqual(summary.schema_version, 1)
            self.assertEqual(summary.entries, 0)
            self.assertEqual(summary.cursors, 0)
            self.assertEqual(summary.rejected_sources, 0)
            self.assertEqual(summary.hit_dispositions, 0)
            self.assertEqual(summary.validation_problems, [])


class TestAvailableRealLedger(unittest.TestCase):
    def test_initialized_marker_backed_ledger_is_summarized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_institutional_memory_distill(root)
            ledger_rel = "cache/decision-ledger/DECISION-LEDGER.json"
            _write(
                root / ledger_rel,
                """{
  "schema_version": 1,
  "entries": [
    {
      "id": "d-001",
      "decision": "use stdlib http.server",
      "reasoning": "no pip install step",
      "source": {"type": "design-doc", "ref": "D24"},
      "confidence": "EXTRACTED",
      "distilled_by": "run-1",
      "distilled_through": "2026-08-01T00:00:00Z",
      "created_at": "2026-08-01T00:00:00Z",
      "aliases": [],
      "supersedes": null,
      "superseded_by": null
    }
  ],
  "run_state": {
    "cursors": [{"stream_id": "prs", "last_processed_id": "42", "advanced_at": "2026-08-01T00:00:00Z"}],
    "rejected_sources": [{"stream_id": "prs", "source_id": "99"}]
  },
  "hit_dispositions": []
}""",
            )
            slot = _initialized_slot_state(
                ledger_rel, "starter_kit/decision_ledger/DECISION-LEDGER.json"
            )
            summary = wt.read_summary(root, slot)
            self.assertTrue(summary.available)
            self.assertTrue(summary.initialized)
            self.assertEqual(summary.ledger_path, ledger_rel)
            self.assertEqual(summary.entries, 1)
            self.assertEqual(summary.cursors, 1)
            self.assertEqual(summary.rejected_sources, 1)
            self.assertEqual(summary.hit_dispositions, 0)
            self.assertEqual(summary.validation_problems, [])

    def test_invalid_ledger_surfaces_validation_problems_not_an_exception(self):
        """An entry missing a required field is a real validate_ledger finding, not
        an artificial one - the Trip-wire box must show it, not crash the wizard."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_institutional_memory_distill(root)
            ledger_rel = "cache/decision-ledger/DECISION-LEDGER.json"
            _write(
                root / ledger_rel,
                """{
  "schema_version": 1,
  "entries": [
    {"id": "d-001", "decision": "", "confidence": "NOT-A-REAL-VALUE",
     "aliases": []}
  ],
  "run_state": {"cursors": [], "rejected_sources": []},
  "hit_dispositions": []
}""",
            )
            slot = _initialized_slot_state(
                ledger_rel, "starter_kit/decision_ledger/DECISION-LEDGER.json"
            )
            summary = wt.read_summary(root, slot)
            self.assertTrue(summary.available)
            self.assertEqual(summary.entries, 1)
            self.assertTrue(summary.validation_problems)  # non-empty


if __name__ == "__main__":
    unittest.main()
