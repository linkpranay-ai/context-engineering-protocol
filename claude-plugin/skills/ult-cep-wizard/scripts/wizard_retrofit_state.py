#!/usr/bin/env python3
"""wizard_retrofit_state.py - owns cache/cep-retrofit/RETROFIT-STATE.json, the
durable per-unit selection/draft state for Journey 3 (consumer/retrofit)
Phase B (D24, ult-cep-wizard).

Why a durable file and not in-memory session state (unlike Phase A, which
needed none): a retrofit run against a 20+-unit library walking per-unit
select -> draft -> review is exactly the multi-round-trip flow a browser
refresh or a wizard-process restart (routine for a local dev tool) would
otherwise blow away - and unlike the layout-onboarding journey there's no
already-durable artifact (context-layout-discovery.md) to re-derive
selections from; cep_retrofit.py is stateless by design (see its own module
docstring). Modeled directly on ult-autoscaffold-content/scripts/
scaffold_state.py's TRIAGE-STATE.json convention: whole-file rewrite, stable
key order, 2-space indent, so diffs stay small and readable. Unlike
scaffold_state.py's modules, retrofit units aren't rediscovered by rescan in
Phase B - Phase A's own build_inventory() is always the live source of truth
for what units *exist*; this file only ever remembers what a human decided
about them.

Never records file *content* - only selections, drafted text, and the target
file's content hash at draft time (wizard_content_hash.hash_file), so a
future Phase C freshness check can detect the target file changing
underneath a stale draft before ever writing to it (mirrors
wizard_apply.py's StaleArtifactError pattern).

Written via wizard_atomic_write.write_text_atomic (same primitive Phase 1's
write path uses). The containing directory is also registered in the
onboarded project's own .gitignore (idempotently, best-effort) - this is
wizard scratch data, never meant to be committed to the project being
onboarded.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wizard_atomic_write as waw  # noqa: E402

SCHEMA_VERSION = 1
STATE_REL_PATH = Path("cache") / "cep-retrofit" / "RETROFIT-STATE.json"
_GITIGNORE_ENTRY = "cache/cep-retrofit/"


class RetrofitStateError(Exception):
    """Raised for any refusal in this module - already-user-facing message."""


def state_path(repo_root) -> Path:
    return Path(repo_root) / STATE_REL_PATH


def _ensure_gitignored(repo_root) -> None:
    """Idempotently appends the state directory to the onboarded project's
    .gitignore. Best-effort only: a missing/unwritable .gitignore never
    blocks a state save (a wizard scratch-data hygiene nicety, not a
    correctness requirement) - failures here are swallowed, not raised."""
    gitignore_path = Path(repo_root) / ".gitignore"
    try:
        existing = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
        lines = [line.strip() for line in existing.splitlines()]
        if _GITIGNORE_ENTRY in lines or _GITIGNORE_ENTRY.rstrip("/") in lines:
            return
        new_content = existing
        if new_content and not new_content.endswith("\n"):
            new_content += "\n"
        new_content += _GITIGNORE_ENTRY + "\n"
        waw.write_text_atomic(gitignore_path, new_content)
    except OSError:
        pass


def load_state(repo_root) -> Dict[str, Any]:
    """Returns the current state dict, or a fresh empty-units skeleton if the
    file doesn't exist yet or fails to parse (a corrupt/missing state file is
    never fatal - it just means "nothing staged yet")."""
    path = state_path(repo_root)
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "units": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": SCHEMA_VERSION, "units": {}}
    if not isinstance(data, dict) or not isinstance(data.get("units"), dict):
        return {"schema_version": SCHEMA_VERSION, "units": {}}
    data.setdefault("schema_version", SCHEMA_VERSION)
    return data


def save_state(repo_root, state: Dict[str, Any]) -> None:
    ordered = {
        "schema_version": state.get("schema_version", SCHEMA_VERSION),
        "units": state.get("units", {}),
    }
    path = state_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    waw.write_text_atomic(path, json.dumps(ordered, indent=2) + "\n")
    _ensure_gitignored(repo_root)


def find_unit(state: Dict[str, Any], unit_id: str) -> Dict[str, Any]:
    entry = state.get("units", {}).get(unit_id)
    if entry is None:
        raise RetrofitStateError(
            f"no selection staged for unit {unit_id!r} - select it first"
        )
    return entry


def upsert_selection(
    state: Dict[str, Any],
    unit_id: str,
    *,
    primary_file: str,
    unit_dir_rel_path: str,
    include: bool,
    contracts: List[str],
    reference_mode: str,
    reference_args: Dict[str, str],
    context_availability: str = "ask",
    target_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Stages (or replaces) one unit's selection. Never touches that unit's
    previously-computed draft_text/insertion_point/target_file_hash if the
    selection is merely being edited - callers that change contracts or
    reference config are expected to re-run draft() afterwards (Phase B's
    POST /api/retrofit/draft), which recomputes and overwrites those fields
    together, atomically, rather than this function guessing whether a stale
    draft is still valid.

    `context_availability` (ISSUES.md Round 2 finding 6, 2026-08-31) is the
    per-unit policy - "ask"/"required"/"optional" per
    wizard_retrofit_draft.CONTEXT_AVAILABILITY_POLICIES, validated by the
    caller (wizard_server.py) before this function ever sees it - persisted
    here so a later draft() call for this unit doesn't need it re-supplied.

    `target_root` (ISSUES.md Round 2 finding 7, 2026-08-31) is None for an
    ordinary in-repo unit (unchanged default - every existing entry shape and
    test keeps working with no migration) or the absolute, already-validated
    external root `primary_file`/`unit_dir_rel_path` are relative to
    otherwise. Persisted per-unit, not as one session-global value, because
    this file already lets a session select/draft units from different
    in-repo subtrees independently - a global external/in-repo toggle
    wouldn't compose with that; a per-unit field does, and defaults to the
    same "None means repo_root" convention every other module in this fix
    uses (wizard_retrofit_inventory.RetrofitInventoryResult.target_root,
    wizard_retrofit_draft.build_draft's containment_root,
    wizard_retrofit_apply.ApplyUnitInput.containment_root)."""
    units = state.setdefault("units", {})
    entry = units.setdefault(unit_id, {})
    entry["primary_file"] = primary_file
    entry["unit_dir_rel_path"] = unit_dir_rel_path
    entry["include"] = bool(include)
    entry["contracts"] = list(contracts)
    entry["reference_mode"] = reference_mode
    entry["reference_args"] = dict(reference_args)
    entry["context_availability"] = context_availability
    entry["target_root"] = target_root
    return entry


def set_draft(
    state: Dict[str, Any],
    unit_id: str,
    *,
    draft_text: str,
    insertion_point: Optional[Dict[str, Any]],
    contracts_included: List[str],
    contracts_skipped_idempotent: List[str],
    target_file_hash: Optional[str],
    context_before: str = "",
    context_after: str = "",
) -> Dict[str, Any]:
    entry = find_unit(state, unit_id)
    entry["draft_text"] = draft_text
    entry["draft_overridden"] = False
    entry["insertion_point"] = insertion_point
    entry["contracts_included"] = list(contracts_included)
    entry["contracts_skipped_idempotent"] = list(contracts_skipped_idempotent)
    entry["target_file_hash"] = target_file_hash
    entry["context_before"] = context_before
    entry["context_after"] = context_after
    return entry


def set_draft_override(state: Dict[str, Any], unit_id: str, draft_text: str) -> Dict[str, Any]:
    entry = find_unit(state, unit_id)
    if "target_file_hash" not in entry:
        raise RetrofitStateError(
            f"unit {unit_id!r} has no computed draft yet - run draft() before overriding it"
        )
    entry["draft_text"] = draft_text
    entry["draft_overridden"] = True
    return entry


def to_json_dict(state: Dict[str, Any]) -> Dict[str, Any]:
    return state
