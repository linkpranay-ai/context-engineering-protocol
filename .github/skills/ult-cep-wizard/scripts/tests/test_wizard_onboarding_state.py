"""Regression suite for wizard_onboarding_state.py (D24 Phase 2). Stdlib unittest
only, same posture as the rest of this skill's test suite. Run with:

    python -m unittest discover -s scripts/tests -v

Same fixture-freshness posture as test_wizard_preflight.py: each fixture repo is a
fresh tempdir per test, and validate_layout.py/discover_layers.py/
layout_decision_grammar.py/confirm_layers.py are copied fresh from the real
ult-repo-layout/scripts/ at test time (not hand-transcribed) so these tests exercise
wizard_onboarding_state against the real modules' real, current behavior.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_onboarding_state as wos  # noqa: E402


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
REAL_SKILL_DIR = REAL_REPO_ROOT / ".github" / "skills" / "ult-repo-layout"
REAL_SCRIPTS_DIR = REAL_SKILL_DIR / "scripts"


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _install_ult_repo_layout(root: Path) -> None:
    """Copies the real SKILL.md + all four scripts LayoutSource needs
    (validate_layout, discover_layers, layout_decision_grammar, confirm_layers) -
    a superset of test_wizard_preflight.py's own helper, since this module (unlike
    preflight's now-single check) constructs a real LayoutSource for three of its
    four states."""
    skill_dir = root / ".github" / "skills" / "ult-repo-layout"
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(REAL_SKILL_DIR / "SKILL.md", skill_dir / "SKILL.md")
    for name in (
        "validate_layout.py",
        "discover_layers.py",
        "layout_decision_grammar.py",
        "confirm_layers.py",
    ):
        shutil.copy(REAL_SCRIPTS_DIR / name, scripts_dir / name)


def _make_clean_repo(root: Path) -> None:
    """Installed, never-run - validates clean (fresh/unconfigured is not a FAIL, only
    INFO lines - see validate_layout.validate's own docstring), no discovery artifact
    yet. The needs_discover fixture."""
    _install_ult_repo_layout(root)


def _make_broken_repo(root: Path) -> None:
    """Two `.layout-slots.yaml` markers for the same slot at different locations -
    validate_layout.validate's own §15.9 bijectivity check (S15) FAILs on this
    (validate_layout.py:851-861), independent of anything D23-related."""
    _install_ult_repo_layout(root)
    (root / ".github" / "skills" / "ult-context-generate").mkdir(parents=True)
    marker = (
        "slots:\n  - slot: context_packages\n    kind: directory\n"
        "    schema_version: 1\n"
    )
    _write(root / "contexts" / ".layout-slots.yaml", marker)
    _write(root / "contexts2" / ".layout-slots.yaml", marker)


SINGLE_PENDING_ARTIFACT = """# Context Layout Discovery - test-repo

## What-L2 - project's own requirements/spec docs
**Status:** enabled by default.

    decision: PENDING   # CONFIRM: docs/reqs/ | CUSTOM: <path> | SKIP
"""

STAGED_ARTIFACT = """# Context Layout Discovery - test-repo

## What-L2 - project's own requirements/spec docs
**Status:** enabled by default.

    decision: CONFIRM: docs/reqs/   # CONFIRM: docs/reqs/ | CUSTOM: <path> | SKIP
"""

ALL_CONFIRMED_ARTIFACT = """# Context Layout Discovery - test-repo

## What-L2 - project's own requirements/spec docs
**Status:** enabled by default.

    decision: CONFIRM: docs/reqs/   # CONFIRMED 2026-01-01
"""


def _install_d20_marker(root: Path) -> None:
    """Registers a real D20 slot marker (context_packages, owned by
    ult-context-generate) - used by the tests proving d20_initialized flips
    independently of `name`."""
    (root / ".github" / "skills" / "ult-context-generate").mkdir(
        parents=True, exist_ok=True
    )
    _write(
        root / "contexts" / ".layout-slots.yaml",
        "slots:\n  - slot: context_packages\n    kind: directory\n"
        "    schema_version: 1\n",
    )


class TestLayoutBroken(unittest.TestCase):
    def test_validate_failure_yields_layout_broken(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_broken_repo(root)
            state = wos.compute_state(root)
            self.assertEqual(state.name, wos.LAYOUT_BROKEN)
            self.assertFalse(state.validate_ok)
            self.assertTrue(any(f.startswith("FAIL") for f in state.validate_failures))
            self.assertFalse(state.discovery_artifact_exists)


class TestNeedsDiscover(unittest.TestCase):
    def test_clean_repo_with_no_artifact_yields_needs_discover(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_clean_repo(root)
            state = wos.compute_state(root)
            self.assertEqual(state.name, wos.NEEDS_DISCOVER)
            self.assertTrue(state.validate_ok)
            self.assertFalse(state.discovery_artifact_exists)
            self.assertFalse(state.d20_initialized)

    def test_d20_initialized_does_not_change_needs_discover(self):
        """D20 status is informational only - a repo can have run
        `ult-repo-layout init` (D20-initialized) but never run `discover` (D23) -
        must still land on needs_discover, not be treated as steady."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_clean_repo(root)
            _install_d20_marker(root)
            state = wos.compute_state(root)
            self.assertEqual(state.name, wos.NEEDS_DISCOVER)
            self.assertTrue(state.d20_initialized)


class TestDecisionsPending(unittest.TestCase):
    def test_pending_field_yields_decisions_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_clean_repo(root)
            _write(root / "context-layout-discovery.md", SINGLE_PENDING_ARTIFACT)
            state = wos.compute_state(root)
            self.assertEqual(state.name, wos.DECISIONS_PENDING)
            self.assertTrue(state.discovery_artifact_exists)
            self.assertEqual(state.decision_counts["pending"], 1)
            self.assertFalse(state.d20_initialized)

    def test_staged_field_yields_decisions_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_clean_repo(root)
            _write(root / "context-layout-discovery.md", STAGED_ARTIFACT)
            state = wos.compute_state(root)
            self.assertEqual(state.name, wos.DECISIONS_PENDING)
            self.assertEqual(state.decision_counts["staged"], 1)

    def test_staged_field_with_d20_initialized_is_still_decisions_pending(self):
        """Second required d20_initialized combination: D23-staged + D20-initialized
        - proves D20 status never overrides the D23-derived state either way."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_clean_repo(root)
            _install_d20_marker(root)
            _write(root / "context-layout-discovery.md", STAGED_ARTIFACT)
            state = wos.compute_state(root)
            self.assertEqual(state.name, wos.DECISIONS_PENDING)
            self.assertTrue(state.d20_initialized)


class TestSteadyState(unittest.TestCase):
    def test_all_confirmed_yields_steady_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_clean_repo(root)
            _write(root / "context-layout-discovery.md", ALL_CONFIRMED_ARTIFACT)
            state = wos.compute_state(root)
            self.assertEqual(state.name, wos.STEADY_STATE)
            self.assertEqual(state.decision_counts["confirmed"], 1)
            self.assertEqual(state.decision_counts["pending"], 0)
            self.assertEqual(state.decision_counts["staged"], 0)


class TestJsonDict(unittest.TestCase):
    def test_to_json_dict_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_clean_repo(root)
            state = wos.compute_state(root)
            payload = wos.to_json_dict(state)
            self.assertEqual(
                set(payload.keys()),
                {
                    "state",
                    "validate_ok",
                    "validate_failures",
                    "discovery_artifact_exists",
                    "decision_counts",
                    "d20_initialized",
                    "workspace_root_current",
                    "workspace_root_offer_eligible",
                },
            )
            self.assertEqual(payload["state"], "needs_discover")


class TestWorkspaceRootOffer(unittest.TestCase):
    """ISSUES.md Round 2 finding 9 (2026-08-31): the wizard-UI workspace_root
    namespacing offer must appear exactly at needs_discover-before-D20-init, and
    nowhere else."""

    def test_eligible_at_needs_discover_before_d20_init(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_clean_repo(root)
            state = wos.compute_state(root)
            self.assertEqual(state.name, wos.NEEDS_DISCOVER)
            self.assertTrue(state.workspace_root_offer_eligible)
            self.assertIsNone(state.workspace_root_current)

    def test_not_eligible_once_d20_initialized(self):
        # run_init itself refuses once D20-initialized (never-silently-reset) -
        # the offer must not even be shown in that case.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_clean_repo(root)
            _install_d20_marker(root)
            state = wos.compute_state(root)
            self.assertEqual(state.name, wos.NEEDS_DISCOVER)
            self.assertFalse(state.workspace_root_offer_eligible)

    def test_not_eligible_at_layout_broken(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_broken_repo(root)
            state = wos.compute_state(root)
            self.assertFalse(state.workspace_root_offer_eligible)

    def test_not_eligible_at_decisions_pending_or_steady_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_clean_repo(root)
            _write(root / "context-layout-discovery.md", ALL_CONFIRMED_ARTIFACT)
            state = wos.compute_state(root)
            self.assertEqual(state.name, wos.STEADY_STATE)
            self.assertFalse(state.workspace_root_offer_eligible)

    def test_workspace_root_current_reflects_already_configured_value(self):
        # A repo that ran `init --workspace-root docs/` through the CLI/agent flow
        # still reports the value here, even though the offer itself is no longer
        # eligible (d20_initialized is now True).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_clean_repo(root)
            _install_d20_marker(root)
            _write(
                root / "context-config.yaml",
                "layout:\n  workspace_root: docs/\n",
            )
            state = wos.compute_state(root)
            self.assertEqual(state.workspace_root_current, "docs")
            self.assertFalse(state.workspace_root_offer_eligible)


if __name__ == "__main__":
    unittest.main()
