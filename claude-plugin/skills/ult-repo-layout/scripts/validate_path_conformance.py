#!/usr/bin/env python3
"""validate_path_conformance.py - non-blocking path-dependency-conformance
scan (D21 v3 §16.8), backing amb-review-contribution's 7th review dimension,
"Path-dependency conformance".

Scans a contributed skill's SKILL.md (and any supporting `.md` files) for
write-verb-object path literals: lines matching `save(s|d|ing) ... to`,
`writ(e|es|ten|ing) ... to`, `creat(e|es|ed|ing) ... at`, or
`output(s|ted|ting)? ... to`, immediately followed (same line) by a
backtick-quoted, path-shaped literal.

Entirely informational (§16.8, resolves H3) - never fails/exits non-zero for
findings. For each matched literal:
  - if it matches a registered slot/config-key/starter-kit-dropzone's pre-D21
    or workspace_root-relative default (from layout-slots-registry.yaml,
    §16.4): "... is registered (§16.4) - resolve its path via §15.5 (or this
    key's resolution algorithm) instead of hardcoding '<literal>' ..."
  - otherwise: "possible new path convention ('<literal>') - consider
    registering it in layout-slots-registry.yaml (§16.4)."

Python 3 stdlib only - vendorable alongside validate_layout.py, whose
load_yaml_file() this module reuses to read layout-slots-registry.yaml (a
no-op if that file is absent - every consuming project).

CLI:
    python validate_path_conformance.py --validate <skill-md-or-dir> [<repo-root>]
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_layout import load_yaml_file  # noqa: E402


# Bounded (.{0,40}) so the verb and "to"/"at" stay in the same clause.
WRITE_VERB_RE = re.compile(
    r"(?:\bsav(?:e|es|ed|ing)\b.{0,40}\bto\b)"
    r"|(?:\bwrit(?:e|es|ten|ing)\b.{0,40}\bto\b)"
    r"|(?:\bcreat(?:e|es|ed|ing)\b.{0,40}\bat\b)"
    r"|(?:\boutput(?:s|ted|ting)?\b.{0,40}\bto\b)",
    re.IGNORECASE,
)

BACKTICK_RE = re.compile(r"`([^`]+)`")


def _is_path_shaped(literal):
    """A backtick-quoted literal counts as "path-shaped" if it contains a
    '/', has no whitespace, and isn't a URL - excludes prose, file-tree
    annotations, and cross-reference links."""
    if "/" not in literal:
        return False
    if literal.startswith(("http://", "https://")):
        return False
    if any(c.isspace() for c in literal):
        return False
    return True


def _normalize(path_str):
    """Strip a literal '{workspace_root}/' prefix and any trailing '/', for
    comparison against layout-slots-registry.yaml's pre_d21_default /
    workspace_root_leaf / workspace_root_default columns."""
    path_str = path_str.strip()
    if path_str.startswith("{workspace_root}/"):
        path_str = path_str[len("{workspace_root}/"):]
    elif path_str == "{workspace_root}":
        path_str = ""
    return path_str.rstrip("/")


def load_registry_entries(repo_root):
    """Flatten layout-slots-registry.yaml's slots/config_keys/
    starter_kit_dropzones sections into one list of entry dicts. Returns []
    if the file is absent - the file is library-level-only (§16.8), so this
    is the normal case for every consuming project; every match is then
    reported as a possible new convention rather than an already-registered
    one."""
    registry = load_yaml_file(Path(repo_root) / "layout-slots-registry.yaml")
    if registry is None:
        return []
    entries = []
    for section in ("slots", "config_keys", "starter_kit_dropzones"):
        for entry in registry.get(section) or []:
            if isinstance(entry, dict):
                entries.append(entry)
    return entries


def _registered_match(literal, registry_entries):
    """Return the registry entry whose pre_d21_default or
    workspace_root_leaf/workspace_root_default matches `literal` (after
    normalization), or None."""
    normalized = _normalize(literal)
    if not normalized:
        return None
    for entry in registry_entries:
        for key in ("pre_d21_default", "workspace_root_leaf", "workspace_root_default"):
            value = entry.get(key)
            if isinstance(value, str) and _normalize(value) == normalized:
                return entry
    return None


def find_markdown_files(target):
    """`target` may be a single .md file, or a skill directory - in which
    case every .md file under it (SKILL.md plus supporting files such as
    references/*.md) is scanned."""
    target = Path(target)
    if target.is_file():
        return [target]
    return sorted(target.rglob("*.md"))


def scan_file(path, registry_entries):
    """Scan one markdown file for write-verb-object path literals. Returns a
    list of (line_no, message) tuples - all informational."""
    findings = []
    text = path.read_text(encoding="utf-8-sig")
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not WRITE_VERB_RE.search(line):
            continue
        for literal in BACKTICK_RE.findall(line):
            if not _is_path_shaped(literal):
                continue
            entry = _registered_match(literal, registry_entries)
            if entry is None:
                findings.append((
                    line_no,
                    f"possible new path convention ('{literal}') - consider "
                    f"registering it in layout-slots-registry.yaml (§16.4).",
                ))
            elif entry.get("project_layout_slot"):
                findings.append((
                    line_no,
                    f"slot '{entry.get('id')}' is registered (§16.4) - "
                    f"resolve its path via §15.5 instead of hardcoding "
                    f"'{literal}', so projects that relocate "
                    f"'{entry.get('id')}' aren't broken by this skill.",
                ))
            else:
                findings.append((
                    line_no,
                    f"'{literal}' matches the registered default for "
                    f"'{entry.get('id')}' (§16.4) - resolve it via "
                    f"context-config.yaml's resolution algorithm for that "
                    f"key instead of hardcoding, so projects that customize "
                    f"'{entry.get('id')}' aren't broken by this skill.",
                ))
    return findings


def validate(target, repo_root="."):
    """Scan `target` (a SKILL.md file or a skill directory) for
    path-dependency-conformance findings. Returns a list of report strings -
    always informational, no pass/fail."""
    registry_entries = load_registry_entries(repo_root)
    report = []
    for md_path in find_markdown_files(target):
        for line_no, message in scan_file(md_path, registry_entries):
            report.append(f"INFO: {md_path}:{line_no}: {message}")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="SKILL.md file or skill directory to scan")
    parser.add_argument(
        "repo_root", nargs="?", default=".",
        help="repo root containing layout-slots-registry.yaml, if any (default: .)",
    )
    parser.add_argument("--validate", action="store_true", help="run the scan and report")
    args = parser.parse_args(argv)

    if not args.validate:
        parser.print_help(sys.stderr)
        return 2

    report = validate(args.target, args.repo_root)
    if report:
        for line in report:
            print(line)
    else:
        print("No path-dependency-conformance findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
