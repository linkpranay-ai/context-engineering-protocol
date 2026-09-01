#!/usr/bin/env python3
"""wizard_retrofit_apply.py - batched write path for Journey 3
(consumer/retrofit) Phase C (D24, ult-cep-wizard).

**This is the phase that grows the write surface.** Phase 1's write path
(wizard_apply.py) touches exactly two CEP-owned artifacts
(context-layout-discovery.md, context-config.yaml). This module writes to
*any file the target picker can reach under the project* - the whole point
of retrofitting a consumer skill library. wizard_containment.check_containment
is still the fail-closed boundary; see references/wizard-security-model.md
and SECURITY.md for the write-surface note landing together with this phase.

Per-unit (not per-batch) mechanics, mirroring SKILL.md Step 8's own stated
contract ("a write failure on one file is reported for that file and does
not abort the rest of the batch"):

  1. Skip fast if there is nothing staged to insert (`draft_text` empty) -
     covers both "never drafted" and "already fully applied in a prior
     request" (see state-update note below) without touching the filesystem.
  2. Freshness check: re-hash the target file and compare against the hash
     captured when its diff preview was computed
     (wizard_retrofit_draft.build_draft's `target_file_hash`). A mismatch
     means the file changed underneath this session - reject this unit only,
     asking for a reload+re-draft, never silently overwrite.
  3. Last-instant idempotency guard: re-run `cep_retrofit.check_pointer` on
     exactly the contracts this draft would insert, immediately before
     writing. If all are already present, skip without writing - this is
     what makes re-posting the same batch after a partial success safe by
     construction (Journey 3 plan's own words). If *some but not all* are
     already present, fail closed rather than attempt a partial re-slice of
     an already-baked draft_text block (see `apply_unit` docstring) - this
     branch is defense-in-depth; every currently-designed caller path keeps
     it unreachable (see note below), but the function does not rely on
     that invariant holding.
  4. Splice `draft_text` in at `insertion_point["line"]` (0-indexed, insert-
     before semantics - the exact contract cep_retrofit.find_insertion_point
     and wizard_retrofit_draft._extract_context both already assume) and
     write atomically via wizard_atomic_write.write_text_atomic.
  5. Every step above returns rather than raises on every anticipated
     failure mode; `apply_batch` additionally wraps each `apply_unit` call in
     a bare except so one truly unexpected exception still can't take the
     rest of the batch down with it.

State-update note (caller's responsibility, not this module's): after a
successful apply, the caller (wizard_server.py's route handler) is expected
to clear the unit's draft_text/insertion_point/contracts_included and record
the post-write hash via wizard_retrofit_state.set_draft(..., draft_text="",
...) - the exact same shape wizard_retrofit_draft.build_draft() already uses
for "nothing left to insert here". This keeps "fully applied" and "fully
satisfied on disk already" a single representation instead of two states
this module would otherwise have to keep in sync, and is what makes step 1's
fast-path skip correctly turn a resubmitted already-applied unit into
`skipped_idempotent` without ever re-checking the filesystem. Because of
that contract, step 3's "some but not all present" branch is provably
unreachable via the normal select -> draft -> apply -> (re-)apply flow: step
2's hash-equality gate means the file's content (and therefore
check_pointer's result for these exact contracts) is byte-identical to what
it was when contracts_included was computed at draft time, when by
construction none of contracts_included were yet present.
"""
from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wizard_atomic_write as waw  # noqa: E402
import wizard_containment as wc  # noqa: E402
import wizard_content_hash as wch  # noqa: E402


def _find_cep_retrofit_scripts_dir(repo_root) -> Path:
    """Same lookup wizard_retrofit_draft.py's own (private) version does -
    duplicated for the same reason every other importer in this skill
    duplicates its own: this module must be independently usable and
    independently unit-testable without relying on another module having
    already run in the same process."""
    scripts_dir = Path(repo_root) / ".github" / "skills" / "ult-cep-retrofit" / "scripts"
    if not (scripts_dir / "cep_retrofit.py").exists():
        raise RetrofitApplyError(
            f"ult-cep-retrofit's cep_retrofit.py was not found under {scripts_dir} - "
            f"is ult-cep-retrofit installed in this repo?"
        )
    return scripts_dir


def _import_cep_retrofit(repo_root):
    scripts_dir_str = str(_find_cep_retrofit_scripts_dir(repo_root))
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    return importlib.import_module("cep_retrofit")


class RetrofitApplyError(Exception):
    """Raised only by the module-level helpers above; apply_unit/apply_batch
    themselves never raise this - every anticipated failure becomes a
    "failed" ApplyUnitResult instead (see module docstring, step 5)."""


@dataclass
class ApplyUnitInput:
    """Everything apply_unit needs for one unit, already resolved out of
    RETROFIT-STATE.json by the caller - this module never reads state or a
    unit_id -> state-entry mapping itself, matching wizard_retrofit_draft's
    own pure-function shape. unit_id is carried along purely so
    apply_batch's results can be attributed back to the right card in the
    UI; it plays no part in any decision this module makes."""

    unit_id: str
    primary_file: Optional[str]
    insertion_point: Optional[Dict[str, Any]]
    draft_text: str
    contracts_included: List[str]
    target_file_hash: Optional[str]
    # ISSUES.md Round 2 finding 7 (2026-08-31): the absolute, already-
    # validated external root `primary_file` is relative to, when this unit's
    # target isn't ctx.repo_root - None (the default) is the unchanged
    # in-repo case. Same "None means repo_root" convention as
    # wizard_retrofit_inventory.RetrofitInventoryResult.target_root and
    # wizard_retrofit_draft.build_draft's containment_root.
    containment_root: Optional[str] = None


@dataclass
class ApplyUnitResult:
    unit_id: str
    status: str  # "applied" | "skipped_idempotent" | "failed"
    reason: str
    contracts_applied: List[str] = field(default_factory=list)
    contracts_skipped_idempotent: List[str] = field(default_factory=list)
    target_file_hash_after: Optional[str] = None


def apply_unit(repo_root, unit_input: ApplyUnitInput) -> ApplyUnitResult:
    """Applies one unit's already-drafted insertion to disk. See module
    docstring for the full step-by-step contract. Never raises for an
    anticipated failure - always returns a "failed" result with a
    human-readable `reason` instead, so apply_batch's loop never needs a
    try/except around the expected cases (only around the unexpected ones,
    see apply_batch)."""
    uid = unit_input.unit_id

    if not unit_input.draft_text:
        return ApplyUnitResult(
            unit_id=uid,
            status="skipped_idempotent",
            reason="nothing staged to insert (already applied, or never drafted)",
        )
    if not unit_input.primary_file:
        return ApplyUnitResult(unit_id=uid, status="failed", reason="no primary_file recorded for this unit")
    insertion_point = unit_input.insertion_point
    if not insertion_point or not isinstance(insertion_point.get("line"), int):
        return ApplyUnitResult(
            unit_id=uid,
            status="failed",
            reason="no insertion point recorded - re-draft this unit before applying",
        )

    try:
        target = wc.check_containment(
            unit_input.containment_root or repo_root, unit_input.primary_file
        )
    except wc.ContainmentError as exc:
        return ApplyUnitResult(unit_id=uid, status="failed", reason=str(exc))
    if not target.is_file():
        return ApplyUnitResult(unit_id=uid, status="failed", reason=f"{unit_input.primary_file} is not a file")

    current_hash = wch.hash_file(target)
    if current_hash != unit_input.target_file_hash:
        return ApplyUnitResult(
            unit_id=uid,
            status="failed",
            reason="target file changed since this draft was computed - reload and re-draft before applying",
        )

    try:
        cr = _import_cep_retrofit(repo_root)
    except RetrofitApplyError as exc:
        return ApplyUnitResult(unit_id=uid, status="failed", reason=str(exc))

    contracts_included = list(unit_input.contracts_included)
    try:
        already_present = cr.check_pointer(str(target), contracts_included)
    except OSError as exc:
        return ApplyUnitResult(unit_id=uid, status="failed", reason=str(exc))

    still_needed = [c for c in contracts_included if not already_present.get(c)]
    if not still_needed:
        return ApplyUnitResult(
            unit_id=uid,
            status="skipped_idempotent",
            reason="already present",
            contracts_skipped_idempotent=contracts_included,
        )
    if len(still_needed) != len(contracts_included):
        # Partial overlap: some but not all of this draft's contracts are
        # already present. draft_text is one pre-baked block covering every
        # contract in contracts_included together (SKILL.md Step 6.4) - it
        # cannot be safely re-sliced into "only the still-needed sentences"
        # without re-running draft_insertion_text, which this module
        # deliberately never does (no LLM/no re-templating on the write
        # path - see module docstring). Fail closed rather than risk a
        # partial or duplicate insertion. See module docstring for why this
        # branch is not reachable via the normal flow.
        return ApplyUnitResult(
            unit_id=uid,
            status="failed",
            reason=(
                "some but not all of this unit's contracts are already present - "
                "re-draft this unit to pick up the current state before applying"
            ),
        )

    try:
        original = target.read_text(encoding="utf-8")
    except OSError as exc:
        return ApplyUnitResult(unit_id=uid, status="failed", reason=str(exc))

    had_trailing_newline = original.endswith("\n")
    lines = original.splitlines()
    line = max(0, min(insertion_point["line"], len(lines)))
    new_lines = lines[:line] + unit_input.draft_text.split("\n") + lines[line:]
    new_text = "\n".join(new_lines)
    if had_trailing_newline:
        new_text += "\n"

    try:
        waw.write_text_atomic(target, new_text)
    except waw.AtomicWriteError as exc:
        return ApplyUnitResult(unit_id=uid, status="failed", reason=str(exc))

    return ApplyUnitResult(
        unit_id=uid,
        status="applied",
        reason="",
        contracts_applied=contracts_included,
        target_file_hash_after=wch.hash_file(target),
    )


def apply_batch(repo_root, units: List[ApplyUnitInput]) -> List[ApplyUnitResult]:
    """Applies each unit independently, in the given order. apply_unit()
    already returns rather than raises for every anticipated failure; the
    bare except here is last-resort isolation for a genuinely unexpected
    bug in one unit, so it still can't 500 the whole batch or stop siblings
    from being attempted (SKILL.md Step 8's own contract - see module
    docstring)."""
    results: List[ApplyUnitResult] = []
    for unit_input in units:
        try:
            results.append(apply_unit(repo_root, unit_input))
        except Exception as exc:  # noqa: BLE001 - deliberate last-resort per-unit isolation
            results.append(
                ApplyUnitResult(
                    unit_id=unit_input.unit_id,
                    status="failed",
                    reason=f"unexpected error: {exc}",
                )
            )
    return results
