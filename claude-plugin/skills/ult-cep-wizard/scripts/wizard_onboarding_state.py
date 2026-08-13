#!/usr/bin/env python3
"""wizard_onboarding_state.py - the brownfield onboarding state machine (D24 Phase 2,
§18.14 - see references/wizard-onboarding-state-machine.md for the full writeup).

Root-cause finding this module fixes: wizard_preflight.py's old check 2
(`_check_initialized`, now retired) tested the wrong axis. It checked for D20
slot-registry state (`project_layout` key / `.layout-slots.yaml` markers - written by
ult-repo-layout's interactive `init`/`reconcile` flow), but this wizard's own
Decisions UI operates on the D23 discover/confirm-layers system
(`context-layout-discovery.md`, direct `layers.what_l2.path`-style keys in
context-config.yaml) - confirmed by direct read that confirm_layers.py never touches
`project_layout` or any marker file. A repo that only ever runs `discover` +
`confirm-layers` (the real brownfield flow) could never pass the old check 2, no
matter how complete its setup was.

`compute_state(repo_root)` replaces it with real state detection along the axis the
wizard actually depends on (D23), computed fresh on every call - never cached, same
"everything read fresh from disk" principle wizard_layout_source.py documents. D20
status (`d20_initialized`) is relocated here as a separate, non-gating informational
boolean - carried on every state, but never used to choose which one renders (see
wizard_boxes.py: a D20-uninitialized repo already degrades gracefully today, e.g.
GuidelinesBox.initialized=False - a normal empty state, not an error).

State table:
  layout_broken     - validate_layout.validate() itself returns ok=False. Nothing else
                       is attempted over a known-broken config.
  needs_discover     - validates clean, but context-layout-discovery.md doesn't exist
                       yet. Guide-only intro + a real "Run Discover" button.
  decisions_pending  - artifact exists, at least one field is still pending/staged.
  steady_state       - artifact exists, every field is confirmed.
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wizard_layout_source  # noqa: E402

LAYOUT_BROKEN = "layout_broken"
NEEDS_DISCOVER = "needs_discover"
DECISIONS_PENDING = "decisions_pending"
STEADY_STATE = "steady_state"


@dataclass
class OnboardingState:
    name: str  # one of the four module-level constants above
    validate_ok: bool
    validate_failures: List[str]  # only non-empty when validate_ok is False
    discovery_artifact_exists: bool
    decision_counts: Dict[str, int] = field(
        default_factory=lambda: {"pending": 0, "staged": 0, "confirmed": 0}
    )
    d20_initialized: bool = False  # informational only - never gates `name`


def _import_validate_layout(repo_root: Path):
    """Same lookup/import pattern wizard_layout_source.py's own
    `_import_repo_layout_modules` uses, duplicated rather than imported for the same
    reason that module documents duplicating wizard_preflight.py's version: this
    module needs to call `validate_layout.validate()` directly (not through
    LayoutSource, whose constructor would raise on failure instead of reporting it as
    a state) and must stay usable on its own. Existence of validate_layout.py itself
    is not re-checked here - wizard_preflight.py's own (sole remaining) check already
    guarantees that before this module is ever reached from a running server."""
    scripts_dir_str = str(
        repo_root / ".github" / "skills" / "ult-repo-layout" / "scripts"
    )
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    return importlib.import_module("validate_layout")


def _is_d20_initialized(repo_root: Path, validate_layout) -> bool:
    """Relocated verbatim from wizard_preflight.py's old `_check_initialized` (D20
    axis) - same predicate, but returns a bool instead of raising. Reuses
    validate_layout.py's own SLOT_REGISTRY/_owning_skill_installed/find_slot_markers
    helpers directly, same reuse-not-reimplement posture as everywhere else in this
    skill that touches D20/D23 state."""
    vl = validate_layout
    config = vl.load_yaml_file(repo_root / "context-config.yaml") or {}
    markers = vl.find_markers(repo_root)
    for slot, spec in vl.SLOT_REGISTRY.items():
        if not vl._owning_skill_installed(repo_root, spec["owning_skill"]):
            continue
        if vl.find_slot_markers(markers, slot):
            return True
    return "project_layout" in config


def compute_state(repo_root) -> OnboardingState:
    """The single entry point `GET /api/state` calls. Assumes ult-repo-layout is
    installed (wizard_preflight.py's sole remaining check already guarantees this at
    server startup) - anything past that is read fresh here every call, never cached."""
    repo_root = Path(repo_root).resolve()
    validate_layout = _import_validate_layout(repo_root)
    d20_initialized = _is_d20_initialized(repo_root, validate_layout)

    ok, report = validate_layout.validate(repo_root)
    if not ok:
        failures = [line for line in report if line.startswith("FAIL")]
        return OnboardingState(
            name=LAYOUT_BROKEN,
            validate_ok=False,
            validate_failures=failures,
            discovery_artifact_exists=False,
            d20_initialized=d20_initialized,
        )

    # validate_ok is True, so LayoutSource's own constructor-time re-check of the
    # same condition cannot raise here - safe to construct unconditionally.
    layout_source = wizard_layout_source.LayoutSource(repo_root)
    artifact_path = layout_source.discovery_artifact_path
    if not artifact_path.exists():
        return OnboardingState(
            name=NEEDS_DISCOVER,
            validate_ok=True,
            validate_failures=[],
            discovery_artifact_exists=False,
            d20_initialized=d20_initialized,
        )

    counts = {"pending": 0, "staged": 0, "confirmed": 0}
    for f in layout_source.read_decisions():
        counts[f.state] = counts.get(f.state, 0) + 1

    name = DECISIONS_PENDING if (counts["pending"] or counts["staged"]) else STEADY_STATE
    return OnboardingState(
        name=name,
        validate_ok=True,
        validate_failures=[],
        discovery_artifact_exists=True,
        decision_counts=counts,
        d20_initialized=d20_initialized,
    )


def to_json_dict(state: OnboardingState) -> dict:
    return {
        "state": state.name,
        "validate_ok": state.validate_ok,
        "validate_failures": state.validate_failures,
        "discovery_artifact_exists": state.discovery_artifact_exists,
        "decision_counts": state.decision_counts,
        "d20_initialized": state.d20_initialized,
    }
