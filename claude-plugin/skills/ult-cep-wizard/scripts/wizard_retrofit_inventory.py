#!/usr/bin/env python3
"""wizard_retrofit_inventory.py - read-only inventory/describe/recommend view for
Journey 3 (consumer/retrofit via `ult-cep-retrofit`), Phase A.

Mirrors wizard_decision_staging.py's dynamic-import pattern for confirm_layers.py,
applied here to cep_retrofit.py instead: this module in-process imports the target
skill's script rather than shelling out, so `recommend()`'s embedded-double-quote
PowerShell-mangling bug (see cep_retrofit.py's own docstring) never has a shell in
the path to trigger it in the first place.

Containment: the retrofit target must be a subdirectory of ctx.repo_root (Journey 3
plan's v1 scope decision - see the plan file's "no LLM in the loop" / "in-repo-only
target" section). `wizard_containment.check_containment` is reused directly, same as
wizard_picker.py and wizard_decision_staging.py, rather than opening a new, less-
constrained path input.

One HTTP round-trip, not N: `build_inventory()` batches inventory() + describe() +
recommend() for every discovered unit into one RetrofitInventoryResult, so the
frontend issues one GET rather than looping a request per unit.

Read-only by design, same posture as wizard_picker.py (§18.7 S1): this module has no
write/apply function anywhere - Phase B/C add drafting and writing in their own,
separate modules.
"""
from __future__ import annotations

import importlib
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wizard_containment as wc  # noqa: E402


class RetrofitInventoryError(Exception):
    """Raised for any inventory request the wizard won't serve - containment
    failure, a non-directory target, or a missing ult-cep-retrofit install. Always
    a user-facing message, never a raw traceback."""


def _find_cep_retrofit_scripts_dir(repo_root) -> Path:
    """Same lookup shape (and same duplication rationale) as
    wizard_decision_staging._find_repo_layout_scripts_dir: this module must be
    independently usable without anything else having already imported
    cep_retrofit.py in this process."""
    scripts_dir = Path(repo_root) / ".github" / "skills" / "ult-cep-retrofit" / "scripts"
    if not (scripts_dir / "cep_retrofit.py").exists():
        raise RetrofitInventoryError(
            f"ult-cep-retrofit's cep_retrofit.py was not found under {scripts_dir} - "
            "is ult-cep-retrofit installed in this repo?"
        )
    return scripts_dir


def _import_cep_retrofit(repo_root):
    scripts_dir_str = str(_find_cep_retrofit_scripts_dir(repo_root))
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    return importlib.import_module("cep_retrofit")


@dataclass
class RetrofitUnit:
    unit_id: str
    type: str  # "skill-dir" | "manifest-dir" | "flat-file"
    path: str  # relative to the retrofit target root
    primary_file: str  # relative to the retrofit target root
    via_symlink: bool
    real_path: str
    name: str = ""
    description: str = ""
    code_related: bool = False
    task_related: bool = False
    matched_code_terms: List[str] = field(default_factory=list)
    matched_task_terms: List[str] = field(default_factory=list)
    describe_error: str = ""  # non-empty only when describe()/recommend() failed


@dataclass
class RetrofitInventoryResult:
    target_rel_path: str  # retrofit target, relative to ctx.repo_root, POSIX-style
    units: List[RetrofitUnit] = field(default_factory=list)
    unclaimed_dirs: List[str] = field(default_factory=list)


def build_inventory(repo_root, target_rel_path: str) -> RetrofitInventoryResult:
    """Containment-checks `target_rel_path` against `repo_root` (v1 in-repo-only
    scope), then runs cep_retrofit's inventory()/describe()/recommend() against
    every discovered unit and returns one batched result.

    A single unit failing describe() (e.g. a race-deleted file, an unreadable
    primary_file) does not abort the whole inventory - that unit is still included,
    with `describe_error` set and the rest of its fields at their empty defaults,
    so the frontend can surface it rather than silently dropping it."""
    try:
        target = wc.check_containment(repo_root, target_rel_path)
    except wc.ContainmentError as exc:
        raise RetrofitInventoryError(str(exc)) from exc

    if not target.is_dir():
        raise RetrofitInventoryError(f"'{target_rel_path}' is not a directory.")

    cr = _import_cep_retrofit(repo_root)

    try:
        raw = cr.inventory(str(target))
    except (OSError, NotADirectoryError) as exc:
        raise RetrofitInventoryError(str(exc)) from exc

    units: List[RetrofitUnit] = []
    for raw_unit in raw["units"]:
        unit = RetrofitUnit(
            unit_id=raw_unit["unit_id"],
            type=raw_unit["type"],
            path=raw_unit["path"],
            primary_file=raw_unit["primary_file"],
            via_symlink=raw_unit["via_symlink"],
            real_path=raw_unit["real_path"],
        )
        primary_abs = target / raw_unit["primary_file"]
        try:
            desc = cr.describe(str(primary_abs))
            unit.name = desc["name"]
            unit.description = desc["description"]
            rec = cr.recommend(unit.description)
            unit.code_related = rec["code_related"]
            unit.task_related = rec["task_related"]
            unit.matched_code_terms = rec["matched_code_terms"]
            unit.matched_task_terms = rec["matched_task_terms"]
        except OSError as exc:
            unit.describe_error = str(exc)
        units.append(unit)

    target_rel = target.relative_to(Path(repo_root).resolve()).as_posix()
    return RetrofitInventoryResult(
        target_rel_path=target_rel,
        units=units,
        unclaimed_dirs=raw["unclaimed_dirs"],
    )


def to_json_dict(result: RetrofitInventoryResult) -> dict:
    """Plain-dict form for `json.dumps` - same asdict() pattern as wizard_boxes.py."""
    return asdict(result)
