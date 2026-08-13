#!/usr/bin/env python3
"""wizard_tripwire.py - read-only Trip-wire box summary for ult-cep-wizard (D24
§18.7, locked).

Wraps `decision_ledger.py`'s own `load_ledger`/`validate_ledger` functions
in-process (imported cross-skill from `ult-institutional-memory-distill/scripts/`,
same pattern `wizard_preflight.py` established for importing from `ult-repo-layout`'s
scripts/ - see `_import_decision_ledger_module` below) rather than subprocessing
`decision_ledger.py show <path>`. `show`'s own CLI handler (`_cmd_show`) only prints
and returns an exit code; this module rebuilds the same summary shape from the two
underlying pure functions it calls (`load_ledger`, `validate_ledger`) and returns it
as data instead - confirmed those two are genuinely all Phase 0 needs; no
`query`/`add-entry`/`disposition`/`alias`/`advance-cursor`/`reject-source` call
anywhere in this module (S4: Phase 0 is read-only, and none of those are read-only
operations - `query` in particular is scored/budget-consuming, not just a read).

Unlike `wizard_preflight.py`'s hard gate on `ult-repo-layout` (a genuine hard
dependency per §18.3), `ult-institutional-memory-distill` is optional here - a repo
without it installed still gets a working wizard, just with the Trip-wire box showing
"not available" instead of a summary. `decision_ledger.py`'s own `load_ledger` already
treats a missing ledger file as a legitimate empty-project state (not an error, per
its own docstring) - this module preserves that: a repo with the skill installed but
never having distilled anything yet gets a real (empty) summary, not an
"unavailable" one.
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Only for type hints - avoids a hard import-time dependency on wizard_layout_source
# (this module only needs the SlotState shape, not the rest of that module).
try:
    from wizard_layout_source import SlotState
except ImportError:  # pragma: no cover - defensive, mirrors other modules' posture
    SlotState = None  # type: ignore[assignment,misc]

DECISION_LEDGER_SLOT = "decision_ledger"
OWNING_SKILL = "ult-institutional-memory-distill"


@dataclass
class TripwireSummary:
    available: bool
    unavailable_reason: Optional[str] = None
    ledger_path: Optional[str] = None
    initialized: bool = False  # True only if a real marker resolved ledger_path -
    # False means ledger_path (if set) is the unregistered default fallback location.
    schema_version: Optional[int] = None
    entries: int = 0
    cursors: int = 0
    rejected_sources: int = 0
    hit_dispositions: int = 0
    validation_problems: List[str] = field(default_factory=list)


def _find_decision_ledger_scripts_dir(repo_root: Path) -> Optional[Path]:
    skill_dir = repo_root / ".github" / "skills" / OWNING_SKILL
    scripts_dir = skill_dir / "scripts"
    if not (scripts_dir / "decision_ledger.py").exists():
        return None
    return scripts_dir


def _import_decision_ledger_module(repo_root: Path):
    scripts_dir = _find_decision_ledger_scripts_dir(repo_root)
    if scripts_dir is None:
        return None
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    return importlib.import_module("decision_ledger")


def read_summary(repo_root, decision_ledger_slot: Optional["SlotState"]) -> TripwireSummary:
    """`decision_ledger_slot` is `wizard_layout_source.LayoutSource.read_slots()`'s
    entry for the `decision_ledger` slot (None if `ult-institutional-memory-distill`
    isn't installed - read_slots() already filters out slots whose owning skill isn't
    present, mirroring validate_layout.py's own filter)."""
    if decision_ledger_slot is None:
        return TripwireSummary(
            available=False,
            unavailable_reason=(
                f"{OWNING_SKILL} is not installed in this repo - the Trip-wire box "
                "needs it to read the decision ledger."
            ),
        )

    repo_root = Path(repo_root).resolve()
    dl = _import_decision_ledger_module(repo_root)
    if dl is None:
        return TripwireSummary(
            available=False,
            unavailable_reason=(
                f"{OWNING_SKILL}'s SKILL.md is present but "
                "scripts/decision_ledger.py was not found - the install looks "
                "partial (same gap wizard_preflight.py checks for ult-repo-layout)."
            ),
        )

    if decision_ledger_slot.resolved_paths:
        ledger_rel_path = decision_ledger_slot.resolved_paths[0]
        initialized = True
    else:
        ledger_rel_path = decision_ledger_slot.default_path
        initialized = False

    ledger = dl.load_ledger(repo_root / ledger_rel_path)
    problems = dl.validate_ledger(ledger)

    return TripwireSummary(
        available=True,
        ledger_path=ledger_rel_path,
        initialized=initialized,
        schema_version=ledger.get("schema_version"),
        entries=len(ledger.get("entries", [])),
        cursors=len(ledger.get("run_state", {}).get("cursors", [])),
        rejected_sources=len(ledger.get("run_state", {}).get("rejected_sources", [])),
        hit_dispositions=len(ledger.get("hit_dispositions", [])),
        validation_problems=list(problems),
    )
