#!/usr/bin/env python3
"""validate_approved_by.py - schema check for the `approved_by` trust signal.

`approved_by` replaced the old `human_approved: true|false` boolean
(references/context-package-schema.md). It's a list: empty until a human
approves the package, then exactly one `{actor: human:<id>, at: <ISO8601>}`
entry is appended (Step 9 of SKILL.md). v1 enforces at most one entry --
multi-approver review is explicit future scope, not now.

This checks any `contexts/<feature-slug>_<task-type>_*.yaml` package file
(never its `.addenda.yaml` sibling, which never carries this field) or an
`org-conventions/<task_type>.yaml` convention file:
  - `approved_by` is present at all
  - it's list-shaped (`[]` or `- actor: ... / at: ...` entries)
  - it has at most one entry
  - each entry present has both `actor` and `at`, and `actor` looks like
    `human:<id>`

Python 3 stdlib only (argparse, re, sys, pathlib) - vendorable alongside
content_hash.py / content_safety_scan.py, no pip install step.

CLI:
    python validate_approved_by.py <dir-or-file>
"""

import argparse
import re
import sys
from pathlib import Path

_APPROVED_BY_LINE_RE = re.compile(r"^([ \t]*)approved_by:[ \t]*(\[\])?[ \t]*$", re.MULTILINE)
_ENTRY_START_RE = re.compile(r"^[ \t]*-[ \t]*actor:[ \t]*(\S*)[ \t]*$")
_AT_RE = re.compile(r"^[ \t]*at:[ \t]*(\S+)[ \t]*$")


def gather_package_files(target):
    """Return a sorted list of package `.yaml` files under `target` (or just
    `target` itself if it's a single file), excluding `.addenda.yaml`
    siblings, which never carry `approved_by`.
    """
    target = Path(target)
    if target.is_file():
        if target.name.endswith(".addenda.yaml"):
            raise SystemExit("Not a package file (addenda files never carry approved_by): {}".format(target))
        return [target]
    if not target.is_dir():
        raise SystemExit("Path does not exist: {}".format(target))
    return sorted(
        p for p in target.rglob("*.yaml")
        if not p.name.endswith(".addenda.yaml")
    )


def parse_approved_by(text):
    """Return (found, entries, problems) for one file's text.

    `found` is False if no top-level `approved_by:` line exists at all.
    `entries` is a list of {"actor": str|None, "at": str|None} dicts, one per
    `- actor: ...` block found under the field. `problems` lists malformed
    entries (missing actor/at, or actor not shaped like `human:<id>`).
    """
    match = _APPROVED_BY_LINE_RE.search(text)
    if not match:
        return False, [], []

    if match.group(2) == "[]":
        return True, [], []

    indent = len(match.group(1))
    lines = text[match.end():].splitlines()
    entries = []
    problems = []
    current = None
    for line in lines:
        if line.strip() == "":
            continue
        line_indent = len(line) - len(line.lstrip(" \t"))
        if line_indent <= indent and line.strip():
            break  # dedent back to a sibling/parent key -- field body ends here

        entry_match = _ENTRY_START_RE.match(line)
        if entry_match:
            if current is not None:
                entries.append(current)
            current = {"actor": entry_match.group(1) or None, "at": None}
            continue

        at_match = _AT_RE.match(line)
        if at_match and current is not None:
            current["at"] = at_match.group(1)

    if current is not None:
        entries.append(current)

    for i, entry in enumerate(entries, start=1):
        if not entry["actor"]:
            problems.append("entry {}: missing actor".format(i))
        elif not entry["actor"].startswith("human:"):
            problems.append("entry {}: actor {!r} does not start with 'human:'".format(i, entry["actor"]))
        if not entry["at"]:
            problems.append("entry {}: missing at".format(i))

    return True, entries, problems


def validate_file(path):
    """Return a list of problem strings for `path` (empty list = valid)."""
    text = Path(path).read_text(encoding="utf-8")
    found, entries, problems = parse_approved_by(text)
    if not found:
        return ["missing approved_by field"]
    if len(entries) > 1:
        problems.append(
            "{} entries found, v1 allows at most one (multi-approver is future scope)".format(len(entries))
        )
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="validate_approved_by.py",
        description="Validate the approved_by trust-signal field in context "
                    "package / org-convention YAML files.",
    )
    parser.add_argument("target", help="Directory or single .yaml file to check.")
    args = parser.parse_args(argv)

    files = gather_package_files(args.target)
    if not files:
        print("validate_approved_by: no package files found.")
        return 0

    flagged = {}
    for path in files:
        problems = validate_file(path)
        if problems:
            flagged[str(path)] = problems

    if not flagged:
        print("validate_approved_by: {} file(s) checked, all valid.".format(len(files)))
        return 0

    print("validate_approved_by: {} of {} file(s) failed validation:".format(len(flagged), len(files)))
    for path, problems in sorted(flagged.items()):
        print("\n{}:".format(path))
        for problem in problems:
            print("  - {}".format(problem))
    return 1


if __name__ == "__main__":
    sys.exit(main())
