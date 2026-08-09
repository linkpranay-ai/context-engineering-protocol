#!/usr/bin/env python3
"""wizard_decision_staging.py - stages a resolved verb into a PENDING decision
line of `context-layout-discovery.md` (D24 §18.3, "wizard proposes, CLI
commits", locked).

This module never writes `context-config.yaml` and never writes a CONFIRMED
stamp - it only rewrites the value half of one still-PENDING line, in place,
preserving that line's trailing grammar comment verbatim so a later
`confirm_layers.run_confirm()` (or a human editing the file directly) parses
the staged line exactly the way it would parse a hand edit. The real commit -
writing `context-config.yaml` and stamping the artifact - only ever happens
through `confirm_layers.run_confirm()` itself (see `wizard_apply.py`).

Disambiguating which line: a §17.4 section can render more than one
decision-bearing line sharing the same `field_key` - e.g. What-L2's H-2 case
(no Requirements-category match at all) renders one `decision:` line per
surviving candidate, and `include_roots_decision:`/`exclude_decision:`/
`collision_decision:` all repeat once per candidate too (see
discover_layers.py's per-candidate rendering). `(section_title, field_key)`
alone is therefore not always a unique line locator. `stage_decision` accepts
an optional `line_no` (the exact 0-based line index `confirm_layers.Field`
reports, e.g. surfaced to the caller by a prior `/api/decisions` read) to
disambiguate; it is required only when more than one candidate line shares
the same `(section_title, field_key)`, and `stage_decision` raises
`DecisionStagingError` naming every candidate line if it was needed but
omitted, rather than guessing.

CUSTOM-argument validation (round-3 H1): `confirm_layers.py` itself performs
no path validation beyond the placeholder check - the artifact is
hand-editable by design, so a human typing a bad path there is caught (or
not) by whatever the filesystem does with it. The wizard is a GUI, not a text
editor, so this module enforces the stricter contract directly at the
staging boundary: repo-relative, forward slashes only, no parent-traversal,
no drive letter, no literal `#` (would truncate the trailing grammar comment
the same way it truncates `confirm_layers.set_scalar`'s inline YAML comment),
and the resolved path must sit inside `repo_root` -
`wizard_containment.check_containment` is reused directly rather than
reimplementing containment a second time.
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wizard_atomic_write as waw  # noqa: E402
import wizard_containment as wc  # noqa: E402


class DecisionStagingError(Exception):
    """Raised for any staging refusal - already-user-facing message."""


_DRIVE_LETTER_RE = re.compile(r"^[A-Za-z]:")


def _find_repo_layout_scripts_dir(repo_root) -> Path:
    """Same lookup wizard_layout_source.py's own (private) version does -
    duplicated for the same reason it duplicates wizard_preflight.py's own
    copy (see that module's docstring): this module must be independently
    usable without either of those having already run in the same
    process."""
    scripts_dir = Path(repo_root) / ".github" / "skills" / "ult-repo-layout" / "scripts"
    if not (scripts_dir / "confirm_layers.py").exists():
        raise DecisionStagingError(
            f"ult-repo-layout's confirm_layers.py was not found under "
            f"{scripts_dir} - is ult-repo-layout installed in this repo?"
        )
    return scripts_dir


def _import_confirm_layers(repo_root):
    scripts_dir_str = str(_find_repo_layout_scripts_dir(repo_root))
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    return importlib.import_module("confirm_layers")


def validate_custom_arg(repo_root, rel_path):
    """Enforce round-3 H1 before a CUSTOM value is ever staged into the
    artifact. Returns the validated, repo-relative string unchanged (not the
    resolved absolute Path `check_containment` returns) - callers stage this
    exact string into the artifact, which records repo-relative paths, never
    absolute ones. Raises DecisionStagingError on any violation."""
    if rel_path is None or not rel_path.strip():
        raise DecisionStagingError("path must not be empty")
    raw = rel_path.strip()
    if "#" in raw:
        raise DecisionStagingError(
            f"path must not contain '#' (would truncate the artifact's trailing "
            f"comment): {raw!r}"
        )
    if "\\" in raw:
        raise DecisionStagingError(
            f"path must use forward slashes only, got a backslash: {raw!r}"
        )
    if raw.startswith("/") or raw.startswith("~"):
        raise DecisionStagingError(f"path must be repo-relative, not absolute: {raw!r}")
    if _DRIVE_LETTER_RE.match(raw):
        raise DecisionStagingError(
            f"path must be repo-relative, not a drive-letter absolute path: {raw!r}"
        )
    parts = raw.split("/")
    if ".." in parts:
        raise DecisionStagingError(f"path must not contain '..': {raw!r}")
    # A trailing slash is the project's own convention for directory paths
    # (e.g. "docs/requirements/") and must not be rejected as an "empty
    # segment" - only a slash anywhere else (a leading or doubled slash)
    # is one.
    non_trailing = parts[:-1] if parts[-1] == "" else parts
    if "" in non_trailing:
        raise DecisionStagingError(
            f"path must not contain an empty path segment (e.g. a double slash): {raw!r}"
        )

    try:
        wc.check_containment(repo_root, raw)
    except wc.ContainmentError as exc:
        raise DecisionStagingError(str(exc)) from exc

    return raw


def format_decision_line(prefix, key, verb, arg, comment):
    """Renders one decision line, preserving `comment` (the field's original
    grammar clause text) verbatim so `layout_decision_grammar.
    parse_comment_clauses` parses the staged line identically to how it
    would parse a hand edit. `prefix` is the original line's leading
    whitespace - matches `confirm_layers.stamp_field`'s own
    prefix-preserving convention."""
    value = verb if arg is None else f"{verb}: {arg}"
    return f"{prefix}{key}: {value}   # {comment}"


def _resolve_collision_custom_arg(repo_root, arg):
    """collision_decision's CUSTOM argument has a compound shape -
    `<dotted.path> -> <new path>` (see confirm_layers.apply_field's own
    `field.arg.partition("->")`) - not a plain path, so validate_custom_arg
    cannot be run over the whole string. Splits it, validates only the new
    path half, and returns the recombined argument."""
    if arg is None or "->" not in arg:
        raise DecisionStagingError(
            "CUSTOM for a collision decision requires "
            "'<dotted.path> -> <new path>'"
        )
    dotted_part, _, new_path_part = arg.partition("->")
    dotted_part = dotted_part.strip()
    new_path_part = new_path_part.strip()
    if not dotted_part or not new_path_part:
        raise DecisionStagingError(
            "CUSTOM for a collision decision requires both a dotted path and a "
            "new path around '->'"
        )
    new_path_part = validate_custom_arg(repo_root, new_path_part)
    return f"{dotted_part} -> {new_path_part}"


def stage_decision(repo_root, artifact_path, section_title, field_key, verb,
                    arg=None, line_no=None):
    """Stage `verb`[: `arg`] into the PENDING decision line identified by
    `(section_title, field_key[, line_no])` in `artifact_path`. Refuses:

    - the line doesn't exist, or more than one candidate line matches
      `(section_title, field_key)` and `line_no` wasn't given to
      disambiguate (see module docstring);
    - the line isn't PENDING (already staged or CONFIRMED - re-staging over
      an existing decision must go through an explicit re-stage of that
      exact `line_no`, never an implicit "whichever PENDING line matches"
      fallback);
    - `verb` isn't one of the clauses the line's own trailing comment offers
      (stage-time mirror of `confirm_layers.Field.resolve()`'s own check, so
      a bad verb is rejected before it ever reaches the artifact, not just
      on the eventual `confirm-layers` run);
    - `verb` is CUSTOM and `arg` fails `validate_custom_arg` (or, for
      `collision_decision`, `_resolve_collision_custom_arg`);
    - staging this line would create a second CONFIRM/CUSTOM `decision:`
      choice in the same section (stage-time mirror of
      `confirm_layers._check_single_primary_choice` - intentionally
      duplicated for fast UX feedback rather than shared, flagged in the
      plan as a by-hand sync risk since the two checks aren't literally the
      same code).

    Writes via `wizard_atomic_write.write_text_atomic` - this module's first
    production caller. Returns nothing; raises `DecisionStagingError` on any
    refusal.
    """
    cl = _import_confirm_layers(repo_root)
    artifact_path = Path(artifact_path)
    if not artifact_path.exists():
        raise DecisionStagingError(f"{artifact_path} does not exist")
    text = artifact_path.read_text(encoding="utf-8")
    lines, fields = cl.parse_artifact(text)

    candidates = [f for f in fields if f.section_title == section_title and f.key == field_key]
    if not candidates:
        raise DecisionStagingError(
            f"no {field_key!r} field found in section {section_title!r}"
        )
    if len(candidates) > 1:
        if line_no is None:
            lines_desc = ", ".join(str(f.line_no + 1) for f in candidates)
            raise DecisionStagingError(
                f"{len(candidates)} {field_key!r} fields exist in section "
                f"{section_title!r} (lines {lines_desc}) - pass line_no to pick one"
            )
        matched = [f for f in candidates if f.line_no == line_no]
        if not matched:
            raise DecisionStagingError(
                f"no {field_key!r} field at line {line_no + 1} in section {section_title!r}"
            )
        field = matched[0]
    else:
        field = candidates[0]
        if line_no is not None and field.line_no != line_no:
            raise DecisionStagingError(
                f"line_no {line_no + 1} does not match the only {field_key!r} field "
                f"in section {section_title!r} (found at line {field.line_no + 1})"
            )

    if field.comment and cl.CONFIRMED_STAMP_RE.match(field.comment):
        raise DecisionStagingError(
            f"line {field.line_no + 1} is already CONFIRMED - cannot re-stage a "
            f"committed field"
        )
    if field.raw_value.strip() != "PENDING":
        raise DecisionStagingError(
            f"line {field.line_no + 1} is already staged as "
            f"{field.raw_value.strip()!r} - re-stage explicitly if you want to change it"
        )
    if not field.comment:
        raise DecisionStagingError(
            f"line {field.line_no + 1} has no grammar comment to stage against"
        )

    allowed = cl.parse_comment_clauses(field.comment)
    if verb not in allowed:
        raise DecisionStagingError(
            f"{verb!r} is not offered on line {field.line_no + 1} "
            f"(offered: {', '.join(sorted(allowed))})"
        )

    default_arg = allowed[verb]
    if verb == "CUSTOM" and field_key == "collision_decision":
        arg = _resolve_collision_custom_arg(repo_root, arg)
    elif verb == "CUSTOM":
        if arg is None or not arg.strip():
            raise DecisionStagingError("CUSTOM requires an explicit path argument")
        arg = validate_custom_arg(repo_root, arg)
    elif arg is None and default_arg is not None:
        if cl.PLACEHOLDER_RE.search(default_arg):
            raise DecisionStagingError(
                f"{verb!r} requires an explicit argument, e.g. `{verb}: <value>`"
            )
        arg = default_arg

    if arg is not None and cl.PLACEHOLDER_RE.search(arg):
        raise DecisionStagingError(f"{arg!r} still looks like a placeholder - fill in a real value")

    if field_key == "decision" and verb in ("CONFIRM", "CUSTOM"):
        for other in fields:
            if other is field or other.section_title != section_title or other.key != "decision":
                continue
            if other.comment and cl.CONFIRMED_STAMP_RE.match(other.comment):
                continue  # already-committed choice, not a staging-time conflict
            other_verb, _, _ = other.raw_value.strip().partition(":")
            if other_verb.strip() in ("CONFIRM", "CUSTOM"):
                raise DecisionStagingError(
                    f"section {section_title!r} already has a primary choice staged "
                    f"at line {other.line_no + 1} ({other.raw_value.strip()}) - SKIP "
                    f"the other candidates before staging a new primary choice"
                )

    target_line = lines[field.line_no]
    prefix_len = len(target_line) - len(target_line.lstrip(" "))
    prefix = target_line[:prefix_len]
    lines[field.line_no] = format_decision_line(prefix, field.key, verb, arg, field.comment)

    waw.write_text_atomic(artifact_path, "\n".join(lines) + "\n")
