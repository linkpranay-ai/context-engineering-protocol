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
    path: str  # relative to ctx.repo_root (rewritten from cep_retrofit's
    # target-root-relative value in build_inventory(); see the _repo_rel()
    # helper there for why - this is what every downstream consumer
    # (select/draft/apply) already assumes primary_file means).
    primary_file: str  # relative to ctx.repo_root, same rewrite as `path`
    via_symlink: bool
    real_path: str
    tier: str = ""  # "canonical" | "supplementary" - see cep_retrofit.inventory()
    note: str = ""  # non-empty only for a "supplementary" unit cep_retrofit flags
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
    # Paths cep_retrofit.inventory() pruned because the target's
    # .cep-install.json manifest claims them - surfaced so the human sees what
    # the scan left out. Target-relative, same as unclaimed_dirs (see the
    # _repo_rel() note in build_inventory()).
    excluded_owned_paths: List[str] = field(default_factory=list)
    tier_counts: dict = field(default_factory=dict)  # {"canonical": N, "supplementary": M}


def _flag_stray_duplicate_flat_files(raw_units: list, double_suffix: str = ".prompt.md") -> list:
    """Flags - never drops - a "flat-file" raw unit whose primary-file stem
    exactly matches the directory name of a "skill-dir"/"manifest-dir" unit
    found anywhere else in the same inventory - e.g. a stray
    `docs/engineering/implement.md` alongside a wholly separate
    `skills/engineering/implement/SKILL.md` tree. cep_retrofit.inventory()
    itself intentionally returns the union of all three shape-based
    heuristics with no cross-heuristic winner (see its docstring's binding
    constraint) - that constraint is what keeps it usable against any target
    library without encoding knowledge of one. This name-based judgment call
    - "a flat file named after a skill directory found elsewhere in the
    inventory is very likely stray/duplicate documentation of that same
    logical skill" - belongs here instead, in the wizard's read-only view,
    one specific consumer, not the shared primitive every other
    cep_retrofit.py caller relies on.

    An earlier version of this function required the flat file's directory
    and the matched skill-dir/manifest-dir's own directory to be the same
    directory or one level apart before flagging (see git history for
    `_dirs_proximate()`), and before that, dropped a matching unit outright
    rather than flagging it. Both were found, against a real skill library,
    to silently miss (or silently drop) the exact pair this exists to catch
    - `docs/engineering/implement.md` and
    `skills/engineering/implement/SKILL.md` sit in two entirely separate
    top-level trees, sharing only the leaf name, so no proximity check ever
    matches them. Matching is now unconditional on location: any stem match
    anywhere in the inventory is flagged. This can occasionally flag two
    genuinely unrelated same-stem files (e.g. `rules/build.md` next to an
    unrelated `tools/build/SKILL.md`) - an acceptable trade-off, since the
    flag is advisory only (a "supplementary" tier plus a visible note the
    human reviews before selecting units), never a silent drop - the same
    "never silently drop" constraint the original dedupe design was meant to
    honor in the first place.

    `double_suffix` (cep_retrofit.py's `_FLAT_FILE_DOUBLE_SUFFIX`, passed in
    by build_inventory() so the value lives in one place) is stripped before
    comparing stems, so a `.prompt.md` companion of a skill-dir named
    `widget` (i.e. `widget.prompt.md`) correctly compares as stem
    `"widget"`, not `"widget.prompt"`.

    Mutates and returns `raw_units` in place - the same dicts
    build_inventory() reads tier/note off of afterward - rather than
    filtering the list. Runs before describe()/recommend() (build_inventory()
    calls this on the raw dicts, not the built RetrofitUnit list), same as
    before, though nothing is skipped as a result of it any more."""
    claimed = [
        (Path(u["path"]).name.lower(), u["path"])
        for u in raw_units
        if u["type"] in ("skill-dir", "manifest-dir")
    ]

    def _stem(primary_file: str) -> str:
        lower = primary_file.lower()
        if lower.endswith(double_suffix):
            return Path(primary_file[: -len(double_suffix)]).name.lower()
        return Path(primary_file).stem.lower()

    for u in raw_units:
        if u["type"] != "flat-file":
            continue
        stem = _stem(u["primary_file"])
        claimed_path = next(
            (path for claimed_stem, path in claimed if claimed_stem == stem), None
        )
        if claimed_path is None:
            continue
        u["tier"] = "supplementary"
        dup_note = f"duplicates {claimed_path}"
        existing_note = u.get("note") or ""
        u["note"] = f"{existing_note}; {dup_note}" if existing_note else dup_note

    return raw_units


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

    # cep_retrofit.inventory() returns path/primary_file relative to `target`
    # (the directory it was pointed at). Every downstream consumer of a unit
    # (POST /api/retrofit/select's check_containment(repo_root, primary_file),
    # wizard_retrofit_draft.build_draft(), wizard_retrofit_apply.apply_batch())
    # instead treats primary_file as relative to repo_root - the same
    # convention wizard_picker.py's rel_path already uses everywhere else in
    # this wizard. So every unit's path/primary_file is rewritten here, once,
    # to be repo_root-relative before it ever reaches the frontend, rather
    # than leaving each downstream caller to reconstruct target_rel_path +
    # primary_file itself. Computed up front (not after the loop, as this used
    # to be written) since the loop below needs it for every unit.
    target_rel = target.relative_to(Path(repo_root).resolve()).as_posix()

    def _repo_rel(child_rel: str) -> str:
        if target_rel == ".":
            return child_rel
        return f"{target_rel}/{child_rel}"

    units: List[RetrofitUnit] = []
    for raw_unit in _flag_stray_duplicate_flat_files(raw["units"], cr._FLAT_FILE_DOUBLE_SUFFIX):
        unit = RetrofitUnit(
            unit_id=raw_unit["unit_id"],
            type=raw_unit["type"],
            path=_repo_rel(raw_unit["path"]),
            primary_file=_repo_rel(raw_unit["primary_file"]),
            via_symlink=raw_unit["via_symlink"],
            real_path=raw_unit["real_path"],
            tier=raw_unit.get("tier", ""),
            note=raw_unit.get("note", ""),
        )
        # describe() still needs the original target-relative value, since it
        # reads straight off disk via `target`, not repo_root.
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

    # Recomputed from the final `units`, not taken verbatim from
    # raw["tier_counts"] - _flag_stray_duplicate_flat_files() never drops a
    # unit, but it can still change what "supplementary" means for a given
    # unit's note, and the counts reported to the frontend should reflect
    # this module's own view of `units`, not cep_retrofit's pre-flag one.
    tier_counts: dict = {}
    for unit in units:
        if unit.tier:
            tier_counts[unit.tier] = tier_counts.get(unit.tier, 0) + 1

    return RetrofitInventoryResult(
        target_rel_path=target_rel,
        units=units,
        unclaimed_dirs=raw["unclaimed_dirs"],
        # Passed through target-relative, exactly like unclaimed_dirs above -
        # only per-unit path/primary_file get the _repo_rel() rewrite, because
        # only those are consumed downstream as repo-root paths.
        excluded_owned_paths=raw["excluded_owned_paths"],
        tier_counts=tier_counts,
    )


def to_json_dict(result: RetrofitInventoryResult) -> dict:
    """Plain-dict form for `json.dumps` - same asdict() pattern as wizard_boxes.py."""
    return asdict(result)
