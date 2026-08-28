#!/usr/bin/env python3
"""cep_retrofit.py - deterministic helpers for the ult-cep-retrofit metaskill.

CEP-retrofit metaskill (design reviewed via one fresh-context adversarial
pass, 2026-08-05): points at an existing skill library,
inventories it generically, lets a human confirm which skills get retrofitted with
which CONSUMING-*.md pointer(s), then drafts -- never silently writes -- the
insertion. This script owns only the deterministic, mechanical pieces: inventory,
description extraction, recommendation *signals* (never a final decision),
idempotency checking, and insertion-point detection. Every judgment call (which
skills, which contracts, where CEP itself lives, whether a draft is approved) stays
in the calling skill's own human-confirmed steps -- the same split as
decision_ledger.py's `query` (deterministic candidates) vs. ult-context-generate's
Step 7.7 (human tiering).

Format-agnostic by construction (see the design draft's binding constraint, 3):
every heuristic here is shape-based (does this directory contain a file matching a
known pattern), with one narrow, documented exception -- a small set of root-level
filenames (AGENTS.md, README.md, etc. -- see _NON_SKILL_FLAT_NAMES) are excluded by
literal name, but only at the target root itself (depth 0), never at any nested
depth, so a nested file that happens to share one of those names (e.g.
`rules/agents.md`) is unaffected. Everywhere else this runs the same way against
any target library, seen or unseen, and never encodes knowledge of any specific
private library.

Symlink handling: a symlinked directory is inventoried at one level (its own direct
files are checked against the same heuristics, with the real path recorded) but
never recursed into further -- this bounds traversal to a single symlink hop with no
possibility of a cycle, rather than silently skipping symlinked content entirely.

Python 3 stdlib only (argparse, json, os, re, sys, pathlib) -- vendorable alongside
decision_ledger.py, no pip install step.

Subcommands:
  cep_retrofit.py inventory <root>
      Walk <root>, return {"units": [...], "unclaimed_dirs": [...]}. Union of three
      shape-based heuristics -- never a single winner, so a library mixing
      conventions (e.g. SKILL.md-style skill directories alongside flat
      *.prompt.md files as real siblings) doesn't lose one convention's files
      silently. Excludes conventional generated/dependency/VCS directories by
      default. See inventory()'s docstring for the exact per-directory rules.

  cep_retrofit.py describe <path>
      Extract {"name", "description"} from one unit's primary file, via
      frontmatter field -> first heading + first paragraph -> first non-blank
      line, in that order.

  cep_retrofit.py recommend --description "<text>"
  cep_retrofit.py recommend --description-file <path>
      Signal only, never a decision: {"code_related": bool, "task_related": bool,
      "matched_code_terms": [...], "matched_task_terms": [...]}. The calling skill
      turns this into a human-facing recommendation per contract (design draft
      Step 4); it is not itself a selection. --description and --description-file
      are mutually exclusive and one is required. Prefer --description-file on
      Windows/PowerShell (or any shell) whenever the extracted description hasn't
      been visually confirmed quote-free: a description containing embedded double
      quotes (e.g. `asks to "review since X"`) can be silently mangled or truncated
      by PowerShell's argument quoting before this script ever sees it, producing a
      false "neither" classification with no error -- found for real via a
      cross-runtime retrofit run against a third-party library (two skills'
      genuine descriptions both contained embedded quotes). Writing the description
      to a file and passing its path sidesteps shell-quoting entirely.

  cep_retrofit.py check-pointer <file> --contracts C1.md,C2.md
      {"C1.md": bool, "C2.md": bool} -- contract-*identity* match (the bare
      filename appearing anywhere in the text), not a literal-path match, so a
      pointer written under one reference shape (relative path) is still
      recognized as present after a later run resolves a different shape (e.g. a
      plugin-qualified reference).

  cep_retrofit.py find-insertion-point <file>
      {"method": "see-also"|"frontmatter"|"heading"|"prepend", "line": int,
       "heading": str or null}. Checked in order: an existing See Also /
      References / Related section; the end of YAML frontmatter; a heading that
      reads as overview/process content (explicit qualify/disqualify lists, not
      free-floating semantic judgment); prepend near the top. This never returns
      "no insertion point at all" -- "prepend" is the guaranteed fallback: what it
      guards against is guessing a *wrong* structural location, not declining to
      insert. The calling skill's own Step 6 is still free to skip a file for
      other reasons (e.g. an already-satisfied idempotency check).

Every subcommand prints one JSON object to stdout and exits 0, or prints an error to
stderr and exits 1. Read-only -- this script never writes to any file; drafting and
writing stay in the calling skill's own preview-then-confirm steps (design draft
Step 7/8).
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_EXCLUDES = {
    ".git", ".hg", ".svn", "node_modules", "dist", "build", ".venv", "venv",
    "__pycache__", ".tox", ".mypy_cache", ".pytest_cache", "site-packages",
    ".idea", ".vscode",
    # Deliberately tooling/VCS-only. A previous round also excluded "adr",
    # ".changeset", and ".out-of-scope" by name, on the theory that those
    # are repository-governance shapes that never hold real skill units --
    # but that reasoning doesn't hold once the shape check (below, in
    # walk()) is fixed to run and win *before* any name-based exclusion:
    # a directory happening to be named "adr" that holds ordinary markdown
    # notes (not a SKILL.md) is no different from one named "notes" or
    # "docs" holding the same -- see inventory()'s docstring on tiering for
    # how that content is surfaced (as a lower-confidence "supplementary"
    # unit) instead of silently dropped by a denylist entry that would need
    # a new name added every time some other org's governance convention
    # showed up.
}

_SKILL_FILENAMES = ("SKILL.md", "skill.md")
_MANIFEST_PATTERNS = (
    re.compile(r"^skill\.ya?ml$", re.IGNORECASE),
    re.compile(r"^skill\.json$", re.IGNORECASE),
    re.compile(r"^manifest\.\w+$", re.IGNORECASE),
)
_FLAT_FILE_SUFFIXES = (".md", ".mdc")
_FLAT_FILE_DOUBLE_SUFFIX = ".prompt.md"
_NON_SKILL_FLAT_NAMES = {
    "readme.md", "license.md", "changelog.md", "contributing.md",
    "code_of_conduct.md",
    # Root-level AI-coding-agent instruction files, same class as the OSS
    # governance filenames above: a broadly used, cross-project naming
    # convention (not any specific library's own name), so excluding them
    # here doesn't encode knowledge of any one private library. A repo's own
    # AGENTS.md/CLAUDE.md/CONTEXT.md describes how to work in that repo as a
    # whole - it is not itself a retrofittable skill unit.
    #
    # Checked at depth 0 (the inventory target's own root) only -- see
    # _is_flat_skill_file's `is_root` parameter. A nested file that happens
    # to share one of these names (e.g. `rules/agents.md`, a real per-rule
    # doc in some other convention) is a different thing entirely and must
    # not be swept up by a root-level-instruction-file rule that doesn't
    # apply to it.
    "agents.md", "claude.md", "context.md",
}

_CODE_TRIGGER_TERMS = {
    "read", "reads", "write", "writes", "modify", "modifies", "modifying",
    "review", "reviews", "reviewing", "judge", "judges", "refactor",
    "refactors", "lint", "linting", "code", "tests", "test", "testing",
}
_TASK_TRIGGER_TERMS = {
    "design", "designs", "designing", "plan", "plans", "planning", "implement",
    "implements", "implementing", "debug", "debugs", "debugging", "feature",
    "task", "change", "changes",
}
_WORD_RE = re.compile(r"[a-z0-9]+")

_SEE_ALSO_HEADINGS = {"see also", "references", "related"}
_QUALIFY_HEADINGS = {"overview", "how this works", "process", "steps", "usage"}
_DISQUALIFY_HEADINGS = {"license", "contributing", "changelog", "examples"}
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_FRONTMATTER_BLOCK_RE = re.compile(r"^---\s*\r?\n(.*?)\r?\n---", re.DOTALL)
_FRONTMATTER_FIELD_RE = re.compile(r"^(name|description|summary):\s*(.+)$", re.MULTILINE)


def _is_flat_skill_file(name, is_root=False):
    lower = name.lower()
    if is_root and lower in _NON_SKILL_FLAT_NAMES:
        return False
    if lower.endswith(_FLAT_FILE_DOUBLE_SUFFIX):
        return True
    return any(lower.endswith(suf) for suf in _FLAT_FILE_SUFFIXES)


def _rel(path, root):
    return os.path.relpath(str(path), str(root)).replace(os.sep, "/")


def _read_cep_manifest(root):
    """Reads `.cep-install.json` at `root` (written by install.ps1/
    install.sh) and returns its `owned_paths` as a set of resolved absolute
    Paths, or None if no manifest exists or it can't be parsed. Deliberately
    duplicated per-consumer rather than factored into a shared module (see
    this file's own module docstring on why no-shared-library is the house
    convention here). Callers must treat None as "no signal available" and
    fall back to pre-manifest behavior -- never an error for an
    unmanifested library."""
    manifest_path = Path(root) / ".cep-install.json"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    owned = data.get("owned_paths")
    if not isinstance(owned, list):
        return None
    result = set()
    for item in owned:
        if isinstance(item, str) and item:
            result.add((Path(root) / item).resolve())
    return result


def inventory(root, excludes=None, manifest_owned=None):
    """Union of three shape-based heuristics -- never a single winner.

    Per directory, in order:
      (a) contains SKILL.md/skill.md -> one "skill-dir" unit; its subtree is not
          descended further (scripts/, references/, sibling *.md files belong to
          that unit, not separate candidates).
      (b) else, contains exactly one recognizable manifest file
          (skill.yaml/skill.json/manifest.*) -> one "manifest-dir" unit, subtree
          not descended further. More than one manifest-like match is ambiguous
          and falls through to the unclaimed-dirs report instead of guessing.
      (c) each direct *.md/*.mdc/*.prompt.md file not already inside a
          claimed skill-dir/manifest-dir -> its own "flat-file" unit. This runs
          in every directory visited, not just the root, so a library that nests
          flat-file skills under a subdirectory (e.g. `.cursor/rules/*.mdc`) is
          still covered.

    Anything left over that isn't claimed by (a)/(b)/(c) but directly holds
    markdown/YAML/JSON content is reported in "unclaimed_dirs" for the calling
    skill to ask the human about -- never silently included or excluded.

    Every unit carries a "tier": "canonical" for (a)/(b) units (a real,
    dedicated marker file -- high confidence this is a genuine skill unit)
    or "supplementary" for (c) units (a bare markdown file -- a weaker
    guess; it could just as easily be ordinary documentation). A
    "supplementary" unit whose containing directory is named "docs" (at any
    depth, matched case-insensitively, so `Docs/` and `DOCS/` count the same
    as `docs/`) additionally carries a non-empty "note" flagging
    that weaker signal explicitly, rather than being dropped by a
    docs-specific denylist entry. Nothing is ever removed from the walk
    output on tier grounds alone -- tiering is a confidence label for the
    calling skill to group/filter by, not a fourth exclusion heuristic. The
    returned dict's "tier_counts" gives a quick `{"canonical": N,
    "supplementary": M}` summary across all units.

    If `root` has a `.cep-install.json` manifest (written by install.ps1/
    install.sh -- see _read_cep_manifest), its `owned_paths` are excluded on
    top of DEFAULT_EXCLUDES, checked *before* the (a)/(b) shape checks above
    -- so CEP's own installed content is never surfaced as a candidate unit
    for retrofitting, whether `owned_paths` names a container like
    `.github/skills` (the full-install case) or the individual skill
    directories themselves (the `-Only`-install case, where every owned
    directory also carries a SKILL.md and would match shape check (a) if
    ownership were tested second). Pass
    `manifest_owned` explicitly to override auto-detection (mainly for
    tests); pass `manifest_owned=set()` to disable manifest-based exclusion
    entirely. Every path this exclusion actually prunes -- directory or
    individual file -- is listed in the returned dict's
    "excluded_owned_paths" (root-relative, same path convention as
    "unclaimed_dirs"), so the calling skill can show a human what the scan
    left out and why, instead of the exclusion being invisible.
    """
    excludes = DEFAULT_EXCLUDES if excludes is None else excludes
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"not a readable directory: {root}")
    if manifest_owned is None:
        manifest_owned = _read_cep_manifest(root) or set()

    units = []
    unclaimed_dirs = []
    excluded_owned_paths = []

    def walk(dir_path, is_root, via_symlink, name=None):
        try:
            entries = sorted(os.scandir(dir_path), key=lambda e: e.name)
        except OSError:
            return  # permission-denied/race-condition subdir: skip, don't abort the whole scan

        filenames = [e.name for e in entries if e.is_file(follow_symlinks=True)]
        subdirs = [e for e in entries if e.is_dir(follow_symlinks=True)]

        if not is_root and Path(dir_path).resolve() in manifest_owned:
            # Manifest ownership is checked *first*, ahead of the shape
            # checks below: a directory the target's own .cep-install.json
            # names in owned_paths is CEP's own installed content whatever
            # it happens to look like. Ordering matters because CEP's
            # installed skill directories always carry a SKILL.md, so an
            # -Only install (whose manifest names skill-dirs directly rather
            # than a container) would otherwise match the skill-dir shape
            # and be reported as a human-authored candidate -- while that
            # same manifest's sibling flat files were being excluded in the
            # same scan. Pruned like DEFAULT_EXCLUDES: not descended into,
            # not reported as unclaimed either -- but recorded in
            # "excluded_owned_paths" so the exclusion is visible to the
            # calling skill rather than silent.
            excluded_owned_paths.append(_rel(dir_path, root))
            return

        skill_file = next((f for f in filenames if f in _SKILL_FILENAMES), None)
        if skill_file is not None and not is_root:
            units.append({
                "unit_id": _rel(dir_path, root),
                "type": "skill-dir",
                "path": _rel(dir_path, root),
                "primary_file": _rel(os.path.join(dir_path, skill_file), root),
                "via_symlink": via_symlink,
                "real_path": os.path.realpath(dir_path),
                "tier": "canonical",
                "note": "",
            })
            return

        manifest_matches = [
            f for f in filenames if any(p.match(f) for p in _MANIFEST_PATTERNS)
        ]
        if len(manifest_matches) == 1 and not is_root:
            units.append({
                "unit_id": _rel(dir_path, root),
                "type": "manifest-dir",
                "path": _rel(dir_path, root),
                "primary_file": _rel(os.path.join(dir_path, manifest_matches[0]), root),
                "via_symlink": via_symlink,
                "real_path": os.path.realpath(dir_path),
                "tier": "canonical",
                "note": "",
            })
            return

        if not is_root and name in excludes:
            # Name-based exclusion is strictly weaker than the shape checks
            # above: this directory didn't match SKILL.md/manifest-file
            # shape, so its name now takes over purely as a descent-bounding
            # signal for known tooling/VCS directories (node_modules, .git,
            # etc., DEFAULT_EXCLUDES's fixed, generic set) -- never a reason
            # to drop a directory that *does* have skill/manifest shape. A
            # directory named "node_modules" holding real SKILL.md content
            # is caught by the checks above and never reaches this line; one
            # holding only its usual dependency-tree contents is pruned here
            # exactly as before, not scanned for flat-file units or reported
            # as unclaimed.
            return

        owned_filenames = set()
        for f in filenames:
            if _is_flat_skill_file(f, is_root):
                fpath = os.path.join(dir_path, f)
                if Path(fpath).resolve() in manifest_owned:
                    # This exact file is CEP's own installed content (an
                    # individually-listed owned_paths entry, not just a
                    # container directory already pruned above) -- excluded
                    # like any other manifest-owned path, and recorded in
                    # "excluded_owned_paths" so the exclusion stays visible.
                    # Its bare name is remembered so the unclaimed-dirs check
                    # below doesn't count content this scan just excluded.
                    excluded_owned_paths.append(_rel(fpath, root))
                    owned_filenames.add(f)
                    continue
                note = ""
                if "docs" in {p.lower() for p in Path(_rel(dir_path, root)).parts}:
                    note = (
                        'flat-file unit found under a directory named "docs" '
                        '(at this or an ancestor level) -- a weaker signal '
                        'than a dedicated skill-dir/manifest-dir (heuristic '
                        '(c) vs. (a)/(b)); treat as supplementary, not '
                        'canonical'
                    )
                units.append({
                    "unit_id": _rel(fpath, root),
                    "type": "flat-file",
                    "path": _rel(fpath, root),
                    "primary_file": _rel(fpath, root),
                    "via_symlink": via_symlink,
                    "real_path": os.path.realpath(fpath),
                    "tier": "supplementary",
                    "note": note,
                })

        if not is_root:
            # Files the flat-file loop above just pruned as manifest-owned
            # don't count as candidate content: a directory whose only
            # qualifying file is CEP's own installed content isn't
            # human-authored material needing a retrofit decision, and
            # reporting it as unclaimed would contradict the same scan's
            # own "excluded_owned_paths" entry for that file.
            has_candidate_content = any(
                _is_flat_skill_file(f, is_root) or f.lower().endswith((".yaml", ".yml", ".json"))
                for f in filenames
                if f not in owned_filenames
            )
            if has_candidate_content and skill_file is None and len(manifest_matches) != 1:
                unclaimed_dirs.append(_rel(dir_path, root))

        if via_symlink:
            return  # bounded: one level of symlink dereference, never recursed further

        for e in subdirs:
            walk(e.path, False, e.is_symlink(), e.name)

    walk(str(root), True, False)
    tier_counts = {"canonical": 0, "supplementary": 0}
    for u in units:
        tier_counts[u["tier"]] += 1
    return {
        "units": units,
        "unclaimed_dirs": sorted(unclaimed_dirs),
        "excluded_owned_paths": sorted(excluded_owned_paths),
        "tier_counts": tier_counts,
    }


def describe(path):
    """{"name", "description"} via frontmatter -> heading+paragraph -> first line."""
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig", errors="replace")

    name = None
    description = None
    body = text

    m = _FRONTMATTER_BLOCK_RE.match(text)
    if m:
        fm_text = m.group(1)
        for field_m in _FRONTMATTER_FIELD_RE.finditer(fm_text):
            key, value = field_m.group(1), field_m.group(2).strip()
            if key == "name" and name is None:
                name = value
            elif key in ("description", "summary") and description is None:
                description = value
        body = text[m.end():]

    if name is None:
        heading_m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        if heading_m:
            name = heading_m.group(1).strip()
    if name is None:
        name = p.stem

    if description is None:
        lines = body.splitlines()
        para = []
        started = False
        for line in lines:
            stripped = line.strip()
            if not started:
                if stripped.startswith("#"):
                    started = True
                continue
            if not stripped:
                if para:
                    break
                continue
            para.append(stripped)
        if para:
            description = " ".join(para)

    if description is None:
        for line in body.splitlines():
            stripped = line.strip()
            if stripped:
                description = stripped
                break

    return {"name": name or "", "description": description or ""}


def recommend(description):
    """Signal only -- {code_related, task_related, matched_*_terms}. Never a decision."""
    words = set(_WORD_RE.findall(description.lower()))
    code_hits = sorted(words & _CODE_TRIGGER_TERMS)
    task_hits = sorted(words & _TASK_TRIGGER_TERMS)
    return {
        "code_related": bool(code_hits),
        "task_related": bool(task_hits),
        "matched_code_terms": code_hits,
        "matched_task_terms": task_hits,
    }


def check_pointer(file_path, contracts):
    """{contract_filename: already_present_bool}, matched by identity not literal path."""
    text = Path(file_path).read_text(encoding="utf-8-sig", errors="replace")
    return {c: (c in text) for c in contracts}


def find_insertion_point(file_path):
    """{"method", "line", "heading"} -- see module docstring for the checked order."""
    text = Path(file_path).read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()

    for i, line in enumerate(lines):
        hm = _HEADING_RE.match(line)
        if hm and hm.group(2).strip().lower() in _SEE_ALSO_HEADINGS:
            return {"method": "see-also", "line": i + 1, "heading": hm.group(2).strip()}

    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return {"method": "frontmatter", "line": i + 1, "heading": None}

    for i, line in enumerate(lines):
        hm = _HEADING_RE.match(line)
        if not hm:
            continue
        heading_text = hm.group(2).strip().lower()
        if heading_text in _DISQUALIFY_HEADINGS:
            continue
        if heading_text in _QUALIFY_HEADINGS:
            return {"method": "heading", "line": i + 1, "heading": hm.group(2).strip()}

    return {"method": "prepend", "line": 0, "heading": None}


def _cmd_inventory(args):
    try:
        result = inventory(args.root)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def _cmd_describe(args):
    try:
        result = describe(args.path)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def _cmd_recommend(args):
    if args.description_file is not None:
        try:
            description = Path(args.description_file).read_text(
                encoding="utf-8-sig", errors="replace"
            )
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    else:
        description = args.description
    print(json.dumps(recommend(description), indent=2))
    return 0


def _cmd_check_pointer(args):
    contracts = [c.strip() for c in args.contracts.split(",") if c.strip()]
    try:
        result = check_pointer(args.file, contracts)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def _cmd_find_insertion_point(args):
    try:
        result = find_insertion_point(args.file)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="cep_retrofit.py",
        description="Deterministic helpers for the ult-cep-retrofit metaskill.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_inv = sub.add_parser(
        "inventory",
        help="Inventory candidate skill units under a directory (union of shape-based heuristics).",
    )
    p_inv.add_argument("root")
    p_inv.set_defaults(func=_cmd_inventory)

    p_desc = sub.add_parser(
        "describe", help="Extract {name, description} from one unit's primary file.",
    )
    p_desc.add_argument("path")
    p_desc.set_defaults(func=_cmd_describe)

    p_rec = sub.add_parser(
        "recommend",
        help="Signal-only code/task-relatedness of a description (never a final contract choice).",
    )
    p_rec_src = p_rec.add_mutually_exclusive_group(required=True)
    p_rec_src.add_argument(
        "--description",
        help=(
            "Description text inline. Fragile on Windows PowerShell (and any shell) when the "
            "text contains embedded double-quotes, e.g. a description like Use when the user "
            'says "debug this" — PowerShell\'s argument quoting can silently truncate or split '
            "such a string before this script ever sees it, producing a false 'neither' "
            "classification with no error. Prefer --description-file for any description you "
            "haven't visually confirmed is quote-free."
        ),
    )
    p_rec_src.add_argument(
        "--description-file",
        help=(
            "Read the description from a file instead of the command line — sidesteps all "
            "shell-quoting hazards entirely. Recommended default: write the extracted "
            "description to a temp file (or reuse `describe`'s own output) and pass its path "
            "here rather than retyping the text into a shell argument."
        ),
    )
    p_rec.set_defaults(func=_cmd_recommend)

    p_chk = sub.add_parser(
        "check-pointer",
        help="Check whether a file already references given CONSUMING-*.md contract(s), by identity.",
    )
    p_chk.add_argument("file")
    p_chk.add_argument(
        "--contracts", required=True,
        help="Comma-separated contract filenames, e.g. CONSUMING-CONTEXT-PACKAGE.md,CONSUMING-CODE-GRAPH.md",
    )
    p_chk.set_defaults(func=_cmd_check_pointer)

    p_ins = sub.add_parser(
        "find-insertion-point",
        help="Find where a CEP pointer block should go in a file.",
    )
    p_ins.add_argument("file")
    p_ins.set_defaults(func=_cmd_find_insertion_point)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
