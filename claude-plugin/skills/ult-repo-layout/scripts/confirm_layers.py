"""confirm-layers - layer-path decision commit (§17.5-§17.6).

Reads `context-layout-discovery.md` (written by `discover_layers.py`),
validates every `PENDING` decision field against the verbs its own trailing
comment offers, and - only if every field resolves cleanly - writes the
confirmed paths into `context-config.yaml` and stamps the artifact so a
later `discover` run can tell which sections are already settled (§17.6
drift tracking).

Design note (comment-as-grammar): each decision field's trailing comment is
both its own help text AND the machine-readable list of verbs it accepts -
e.g. `decision: PENDING   # CONFIRM: docs/api/ | CUSTOM: <path> | SKIP`. A
bare verb that takes an argument (`CONFIRM`, `ADD`) pulls its default from
that same clause; `CUSTOM` never has a real default (only a literal `<...>`
placeholder) and always needs an explicit `VERB: <value>` edit. This means
every field line is self-contained - including sections with several
independent `decision:` lines (one per candidate) - with no positional
pairing against a table required anywhere.

Nothing is written on any validation failure: this module either applies
every resolved field, or none of them (atomicity - second adversarial
review, M3).
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import validate_layout as vl
from layout_decision_grammar import (
    CONFIRMED_STAMP_RE,
    FIELD_LINE_RE,
    PLACEHOLDER_RE,
    TITLE_TO_BASE_KEY,
    parse_comment_clauses,
    parse_dotted_path,
)

# The regex/vocabulary constants above (and parse_comment_clauses,
# parse_dotted_path, TITLE_TO_BASE_KEY below) used to be defined here and
# duplicated inside discover_layers.py; both now import them from
# layout_decision_grammar.py instead (D24 Phase 1) - this module keeps the
# artifact-parsing/field-resolution/config-write engine, which is what
# actually needs discover_layers.py's rendering conventions to stay in sync
# with, not the shared vocabulary itself.
_parse_comment_clauses = parse_comment_clauses


class FieldError(Exception):
    def __init__(self, section_title, line_no, key, message):
        super().__init__(message)
        self.section_title = section_title
        self.line_no = line_no
        self.key = key
        self.message = message

    def __str__(self):
        where = f"{self.section_title!r} " if self.section_title else ""
        return f"line {self.line_no + 1} {where}[{self.key}]: {self.message}"


class Field:
    """One decision-bearing line in the artifact. Self-contained per the
    comment-as-grammar design - resolving one field never needs to look at
    any other line."""

    def __init__(self, line_no, section_title, key, raw_value, comment):
        self.line_no = line_no
        self.section_title = section_title
        self.key = key
        self.raw_value = raw_value
        self.comment = comment
        self.verb = None
        self.arg = None
        self.already_confirmed = False

    def resolve(self):
        """Populate self.verb/self.arg, or raise FieldError. A line whose
        comment already carries a CONFIRMED stamp is accepted as-is and
        never re-validated (idempotent re-run) - its original grammar
        comment was already overwritten by the stamp, so there is nothing
        left to validate against."""
        if self.comment and CONFIRMED_STAMP_RE.match(self.comment):
            self.already_confirmed = True
            # Still parse verb/arg from the stamped value - §17.6 drift
            # tracking (discover_layers.py) needs to know what was decided,
            # not just that something was.
            verb, _, arg = self.raw_value.strip().partition(":")
            self.verb = verb.strip()
            self.arg = arg.strip() or None
            return
        if self.raw_value.strip() == "PENDING":
            raise FieldError(
                self.section_title, self.line_no, self.key,
                "still PENDING - edit this field before running confirm-layers",
            )
        if not self.comment:
            raise FieldError(
                self.section_title, self.line_no, self.key,
                "comment is missing - only edit the value before the comment, "
                "or re-run `discover` to regenerate it",
            )
        allowed = _parse_comment_clauses(self.comment)
        user_verb, _, user_arg = self.raw_value.strip().partition(":")
        user_verb = user_verb.strip()
        user_arg = user_arg.strip() or None
        if user_verb not in allowed:
            raise FieldError(
                self.section_title, self.line_no, self.key,
                f"'{user_verb}' is not offered here (offered: {', '.join(sorted(allowed))})",
            )
        if user_arg is not None:
            if PLACEHOLDER_RE.search(user_arg):
                raise FieldError(
                    self.section_title, self.line_no, self.key,
                    f"'{user_arg}' still looks like a placeholder - fill in a real value",
                )
            self.verb, self.arg = user_verb, user_arg
            return
        default_arg = allowed[user_verb]
        if default_arg is None:
            self.verb, self.arg = user_verb, None
            return
        if PLACEHOLDER_RE.search(default_arg):
            raise FieldError(
                self.section_title, self.line_no, self.key,
                f"{user_verb} requires an explicit argument, e.g. `{user_verb}: <value>`",
            )
        self.verb, self.arg = user_verb, default_arg


def parse_artifact(text):
    """Split the artifact into raw lines plus the list of decision-bearing
    Fields found in it, in file order."""
    lines = text.splitlines()
    fields = []
    section_title = None
    for i, line in enumerate(lines):
        if line.startswith("## "):
            section_title = line[3:].strip()
            continue
        m = FIELD_LINE_RE.match(line.strip())
        if not m:
            continue
        key, rest = m.group(1), m.group(2)
        if "#" in rest:
            value_part, _, comment_part = rest.partition("#")
            comment = comment_part.strip()
        else:
            value_part, comment = rest, None
        fields.append(Field(i, section_title, key, value_part.strip(), comment))
    return lines, fields


# ---------------------------------------------------------------------------
# Comment-preserving YAML editor (no pyyaml dependency, project convention -
# validate_layout.py's own loader discards comments and cannot round-trip)
# ---------------------------------------------------------------------------

def _line_indent(line):
    return len(line) - len(line.lstrip(" "))


def _key_of(line):
    return line.strip().split(":", 1)[0].strip()


def _is_blank_or_comment(line):
    s = line.strip()
    return s == "" or s.startswith("#")


def _scope_end(lines, start, indent):
    """First index >= start whose content (ignoring blank/comment lines)
    sits at indent <= `indent` - i.e. where a block that started at `indent`
    ends. len(lines) if the block runs to the end of the file."""
    i = start
    while i < len(lines):
        if not _is_blank_or_comment(lines[i]) and _line_indent(lines[i]) <= indent:
            return i
        i += 1
    return len(lines)


def _find_child(lines, start, end, indent, name):
    i = start
    while i < end:
        line = lines[i]
        if not _is_blank_or_comment(line) and _line_indent(line) == indent and _key_of(line) == name:
            return i
        i += 1
    return None


def _locate_or_create_mapping_key(lines, start, end, indent, name):
    idx = _find_child(lines, start, end, indent, name)
    if idx is not None:
        return idx, end
    lines.insert(end, " " * indent + name + ":")
    return end, end + 1


def _walk_to_parent_scope(lines, parents):
    """Ensure every key in `parents` exists as a mapping (creating any that
    are missing), descending one level per key. Returns (start, end, indent)
    - the scope in which the final leaf key lives."""
    indent = 0
    start, end = 0, len(lines)
    for part in parents:
        idx, end = _locate_or_create_mapping_key(lines, start, end, indent, part)
        start = idx + 1
        end = _scope_end(lines, start, indent)
        indent += 2
    return start, end, indent


def set_scalar(lines, dotted_parts, value):
    """Set `dotted_parts[-1]: value` under the mapping chain
    `dotted_parts[:-1]`, creating any missing parent keys. Preserves an
    existing trailing same-line comment verbatim."""
    *parents, leaf = dotted_parts
    start, end, indent = _walk_to_parent_scope(lines, parents)
    idx = _find_child(lines, start, end, indent, leaf)
    prefix = " " * indent
    if idx is None:
        lines.insert(end, f"{prefix}{leaf}: {value}")
        return
    line = lines[idx]
    if "#" in line:
        _, _, comment = line.partition("#")
        lines[idx] = f"{prefix}{leaf}: {value}  #{comment}"
    else:
        lines[idx] = f"{prefix}{leaf}: {value}"


def _list_item_indices(lines, key_idx, end, indent):
    """Indices of the `- item` lines directly under the list key at
    `key_idx` (which sits at `indent`), in order."""
    items = []
    j = key_idx + 1
    while j < end:
        line = lines[j]
        if _is_blank_or_comment(line):
            j += 1
            continue
        if _line_indent(line) == indent + 2 and line.lstrip().startswith("- "):
            items.append(j)
            j += 1
            continue
        break
    return items


def append_list_item(lines, dotted_parts, item):
    """Append `- item` to the list at `dotted_parts`, creating the key (and
    converting an inline `key: []` to block form) if needed."""
    *parents, leaf = dotted_parts
    start, end, indent = _walk_to_parent_scope(lines, parents)
    idx = _find_child(lines, start, end, indent, leaf)
    item_indent = " " * (indent + 2)
    if idx is None:
        lines.insert(end, " " * indent + f"{leaf}:")
        lines.insert(end + 1, f"{item_indent}- {item}")
        return
    items = _list_item_indices(lines, idx, end, indent)
    if items:
        lines.insert(items[-1] + 1, f"{item_indent}- {item}")
        return
    line = lines[idx]
    value_part = line.split(":", 1)[1] if ":" in line else ""
    value_no_comment = value_part.split("#", 1)[0].strip()
    if value_no_comment in ("[]", ""):
        if "#" in line:
            before, _, comment = line.partition("#")
            key_part = before.split(":", 1)[0]
            lines[idx] = f"{key_part}:  #{comment}"
        else:
            lines[idx] = " " * indent + f"{leaf}:"
        lines.insert(idx + 1, f"{item_indent}- {item}")
        return
    # Existing scalar (non-list, non-empty) value with no comprehensible
    # list form - insert the item right after the key line rather than
    # silently dropping it.
    lines.insert(idx + 1, f"{item_indent}- {item}")


def set_list_item(lines, dotted_parts, index, value):
    """Overwrite the `index`-th existing `- item` under `dotted_parts`.
    Errors if the list (or that index within it) doesn't exist - used only
    for the rare cross-layer-collision CUSTOM move that targets an
    `include_roots[N]` candidate rather than a plain `.path`."""
    *parents, leaf = dotted_parts
    start, end, indent = _walk_to_parent_scope(lines, parents)
    idx = _find_child(lines, start, end, indent, leaf)
    dotted = ".".join(dotted_parts)
    if idx is None:
        raise ValueError(f"{dotted} has no existing list to index into")
    items = _list_item_indices(lines, idx, end, indent)
    if index >= len(items):
        raise ValueError(f"{dotted}[{index}] does not exist ({len(items)} item(s) present)")
    target = items[index]
    line = lines[target]
    item_indent = " " * (indent + 2)
    rest = line.split("- ", 1)[1] if "- " in line else ""
    if "#" in rest:
        _, _, comment = rest.partition("#")
        lines[target] = f"{item_indent}- {value}  #{comment}"
    else:
        lines[target] = f"{item_indent}- {value}"


# parse_dotted_path moved to layout_decision_grammar.py (imported above).

# ---------------------------------------------------------------------------
# Applying resolved fields to context-config.yaml
# ---------------------------------------------------------------------------

def apply_field(field, config_lines):
    """Apply one resolved field to config_lines in place. Returns True if a
    config key was written, False if the verb needed no config write
    (SKIP/ACKNOWLEDGE)."""
    base_key = TITLE_TO_BASE_KEY.get(field.section_title)

    if field.key == "decision":
        if field.verb in ("CONFIRM", "CUSTOM"):
            set_scalar(config_lines, base_key.split(".") + ["path"], field.arg)
            return True
        if field.verb == "DISABLE":
            set_scalar(config_lines, base_key.split(".") + ["enabled"], "false")
            return True
        return False  # SKIP / ACKNOWLEDGE

    if field.key == "enable":
        set_scalar(config_lines, base_key.split(".") + ["enabled"],
                    "true" if field.verb == "true" else "false")
        return True

    if field.key == "include_roots_decision":
        if field.verb == "ADD":
            append_list_item(config_lines, base_key.split(".") + ["include_roots"], field.arg)
            return True
        return False  # SKIP

    if field.key == "exclude_decision":
        if field.verb == "ADD":
            append_list_item(config_lines, base_key.split(".") + ["exclude"], field.arg)
            return True
        return False  # SKIP

    if field.key == "collision_decision":
        if field.verb == "CUSTOM":
            dotted, _, new_path = field.arg.partition("->")
            parts, index = parse_dotted_path(dotted.strip())
            new_path = new_path.strip()
            if index is None:
                set_scalar(config_lines, parts, new_path)
            else:
                set_list_item(config_lines, parts, index, new_path)
            return True
        return False  # ACKNOWLEDGE

    raise AssertionError(f"unknown field key {field.key!r}")


def stamp_field(lines, field, timestamp):
    """Rewrite a resolved field's line in the artifact, replacing its
    grammar comment with a CONFIRMED stamp - the record §17.6 drift tracking
    reads back on a later `discover` run."""
    idx = field.line_no
    line = lines[idx]
    prefix = line[: len(line) - len(line.lstrip(" "))]
    resolved_value = field.verb if field.arg is None else f"{field.verb}: {field.arg}"
    lines[idx] = f"{prefix}{field.key}: {resolved_value}   # CONFIRMED {timestamp}"


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _check_single_primary_choice(fields, errors):
    """Guard the H-2 case: a section may render several independent
    `decision:` lines (one per candidate), of which at most one may resolve
    to CONFIRM/CUSTOM (the chosen `path`) - silently letting a second one
    also resolve to CONFIRM/CUSTOM would just make the last write win with
    no signal to the user that their other choice was discarded."""
    by_section = {}
    for f in fields:
        if f.key == "decision" and not f.already_confirmed and f.verb in ("CONFIRM", "CUSTOM"):
            by_section.setdefault(f.section_title, []).append(f)
    for section_title, chosen in by_section.items():
        if len(chosen) > 1:
            lines_desc = ", ".join(f"line {f.line_no + 1}" for f in chosen)
            errors.append(
                f"{section_title!r}: {len(chosen)} candidates were both confirmed as the "
                f"primary path ({lines_desc}) - pick exactly one, SKIP the rest"
            )


def run_confirm(repo_root):
    """Returns (exit_code, messages)."""
    repo_root = Path(repo_root).resolve()
    config_path = repo_root / "context-config.yaml"
    config = vl.load_yaml_file(config_path) or {}
    wr = vl._normalize_workspace_root(config)
    artifact_dir = (repo_root / wr) if wr and wr != "." else repo_root
    artifact_path = artifact_dir / "context-layout-discovery.md"

    if not artifact_path.exists():
        return 1, [f"{artifact_path} not found - run `discover` first."]

    lines, fields = parse_artifact(artifact_path.read_text(encoding="utf-8"))

    errors = []
    for field in fields:
        try:
            field.resolve()
        except FieldError as e:
            errors.append(str(e))
    if not errors:
        _check_single_primary_choice(fields, errors)
    if errors:
        return 1, errors

    to_resolve = [f for f in fields if not f.already_confirmed]
    if not to_resolve:
        return 0, ["Nothing to confirm - every field was already confirmed."]

    config_lines = config_path.read_text(encoding="utf-8").splitlines() if config_path.exists() else []
    timestamp = _now_iso()
    wrote = 0
    for field in to_resolve:
        if apply_field(field, config_lines):
            wrote += 1
        stamp_field(lines, field, timestamp)

    if config_lines:
        config_path.write_text("\n".join(config_lines) + "\n", encoding="utf-8")
    artifact_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0, [f"Confirmed {len(to_resolve)} field(s), wrote {wrote} config key(s)."]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", nargs="?", default=".", help="repo root (default: .)")
    args = parser.parse_args(argv)

    code, messages = run_confirm(args.repo_root)
    for message in messages:
        print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
