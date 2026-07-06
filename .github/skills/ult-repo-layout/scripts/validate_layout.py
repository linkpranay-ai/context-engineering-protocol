#!/usr/bin/env python3
"""validate_layout.py - deterministic project_layout checks (D20 v2 §15.9,
D21 v3 §16.2).

Reads `.layout-slots.yaml` markers (§15.3) and `context-config.yaml`'s
`project_layout`/`cache`/`layout` sections, and reports whether this repo's
registered path-slots are well-formed and internally consistent. No LLM -
plain filesystem + git checks, suitable for CI / pre-commit (`reconcile
--validate`, §15.7).

Phase 1 + Phase 3b + Phase 2 scope: `context_packages` (D20 §15.11 Phase 1),
the two Gap-B slots `plans_output`/`brainstorm_output` (D21 §16.4/§16.10 Phase
3b), and Phase 2's five remaining D20 slots - `compiled_guidelines`,
`user_stories_output`, `security_docs`, `security_report`, `project_plan_docs`
(D20 §15.11 Phase 2) - are all registered slots. The checks below are written
to cover any number of registered slots; Phase 2 is the second slot-count
increase to exercise that "no changes to the check logic itself" claim, this
time spanning a `kind: file` slot (`compiled_guidelines`) and four sibling
`output_docs/<family>/` directory slots.

Phase 3c adds two checks (8-9 below) for `layers.what_l2.*` (D21 §16.5/§16.7) -
these are config-key checks, not slot checks, so they're architecturally
separate from SLOT_REGISTRY/markers: `what_l2` has no marker file of its own,
just `path`/`exclude`/`include_roots`/`index_path` keys in `context-config.yaml`.

Checks (§15.9, plus §16.2's D21 Phase 3a additions):
  1. Bijectivity - no slot has more than one marker; no two slots resolve to
     the same path.
  2. Type consistency - a slot's resolved path, if it exists, matches its
     declared `kind` (directory vs file).
  3. Nesting - flagged only for same-kind slots sharing a path prefix, since
     `nests_under:` whitelisting and `context_addenda`-style recursive-scan
     nesting aren't reachable with Phase 1's single slot.
  4. Path well-formedness - repo-relative only (no absolute paths, no `..`),
     and no Windows-reserved device names / trailing space-or-dot segments
     (S14).
  5. Cross-platform normalization - `project_layout.slots.*.path` values must
     be POSIX-style (forward slashes) (S12).
  6. Config-vanished git-history check (S4) - `context-config.yaml` once had
     `initialized: true` in its history but the current file has no
     `project_layout` section.
  7. `workspace_root` well-formedness (D21 §16.2, S22) - `layout.workspace_root`,
     if set, must be a non-empty repo-relative path other than `.`/`''`
     (reuses check 4's rules). `.`/`''` is a hard-stop FAIL, not a silent
     fallback to either default.
  8. `what_l2.index_path` exclusion (D21 §16.5, M3 invariant) - if
     `layers.what_l2.index_path` resolves to a path under
     `layers.what_l2.path`, it must be covered by a `what_l2.exclude` entry,
     or What-L2 could index its own index file. FAIL if violated; a no-op
     when `index_path` resolves outside `what_l2.path` entirely (the default
     when `workspace_root` is unset).
  9. `what_l2.exclude` typo check (D21 §16.11 S21 / round-2 L2) - each
     `what_l2.exclude` entry should prefix-match (case-sensitively, at
     validation time) an existing subtree under `what_l2.path`. An entry that
     matches nothing existing is a likely typo or case mismatch - WARN, not
     FAIL (S19's "correctly-spelled, doesn't-exist-yet" case is explicitly
     exempted: this check only fires when `what_l2.path` itself exists).
  10. `layout-slots-registry.yaml` consistency (D21 §16.8, Phase 3e) - if that
      file exists at `repo_root`, its `slots:` entries with
      `project_layout_slot: true` must exactly match SLOT_REGISTRY's keys in
      this script. FAIL on drift in either direction. A no-op (the file is
      library-level-only, never copied into consuming projects) for every
      consuming project and every test fixture.

Also reports a non-blocking WARN (D21 S18) when an unmarked slot has content
at both its pre-D21 default and its `workspace_root`-relative default - a
likely partial migration.

Phase 2 adds an S8 (§15.8) partial-install gate: if this repo has a
`.github/skills/` directory, a slot whose `owning_skill` isn't present under
it is skipped entirely (no INFO/WARN/FAIL, not part of bijectivity/nesting) -
an adopter who installed only the `developer` bundle never sees messages about
`security_docs`/`security_report`/`project_plan_docs`. Repos with no
`.github/skills/` directory at all (including every pre-Phase-2 test fixture
in this suite) are unaffected - the gate is a no-op there.

Python 3 stdlib only (re, subprocess, sys, pathlib) - vendorable alongside
md_index.py / content_hash.py.

CLI:
    python validate_layout.py --validate [<repo-root>]
"""

import argparse
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# §15.2 slot registry (Phase 1: context_packages; Phase 3b: + plans_output,
# brainstorm_output; Phase 2: + compiled_guidelines, user_stories_output,
# security_docs, security_report, project_plan_docs)
# ---------------------------------------------------------------------------

SLOT_REGISTRY = {
    "context_packages": {
        "kind": "directory",
        "default": "contexts/",
        # falls back to this config key (Phase 0) if project_layout isn't set
        "default_from": ("cache", "product_context_path"),
        # D21 §16.2/§16.4: {workspace_root}/<this leaf>, if layout.workspace_root
        # is set (and well-formed) and no marker/explicit slot path exists.
        "workspace_root_leaf": "contexts/",
        "owning_skill": "ult-context-generate",
    },
    "plans_output": {
        "kind": "directory",
        "default": "docs/superpowers/plans/",
        # D21 §16.4 (Gap-B, NEW slot - no pre-existing config-key fallback).
        "workspace_root_leaf": "outputs/plans/",
        "owning_skill": "writing-plans",
    },
    "brainstorm_output": {
        "kind": "directory",
        "default": "docs/superpowers/specs/",
        # D21 §16.4 (Gap-B, NEW slot - no pre-existing config-key fallback).
        "workspace_root_leaf": "outputs/specs/",
        "owning_skill": "brainstorming",
    },
    "compiled_guidelines": {
        "kind": "file",
        "default": "starter_kit/project_guidelines/COMPILED-GUIDELINES.md",
        # D21 §16.4: bucket-reassigned inputs -> cache (a derived/regenerable
        # artifact, not a human drop-zone) as well as re-rooted.
        "workspace_root_leaf": "cache/project-guidelines/COMPILED-GUIDELINES.md",
        "owning_skill": "compiling-project-guidelines",
    },
    "user_stories_output": {
        "kind": "directory",
        "default": "output_docs/user-stories/",
        "workspace_root_leaf": "outputs/user-stories/",
        "owning_skill": "spw-write-user-story",
    },
    "security_docs": {
        "kind": "directory",
        "default": "output_docs/security_docs/",
        "workspace_root_leaf": "outputs/security_docs/",
        "owning_skill": "sec-threat-model",
    },
    "security_report": {
        "kind": "directory",
        "default": "output_docs/security_report/",
        "workspace_root_leaf": "outputs/security_report/",
        "owning_skill": "security-test-report",
    },
    "project_plan_docs": {
        "kind": "directory",
        "default": "output_docs/project_plan_docs/",
        "workspace_root_leaf": "outputs/project_plan_docs/",
        "owning_skill": "pm-project-plan",
    },
}

WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

IGNORED_DIR_NAMES = {".git", "__pycache__", "node_modules", ".venv"}


# ---------------------------------------------------------------------------
# YAML-lite reader - just enough block-style YAML for context-config.yaml and
# .layout-slots.yaml (mappings, sequences-of-mappings/scalars, comments,
# scalars). No anchors, flow style, or multiline block scalars.
# ---------------------------------------------------------------------------

def _parse_scalar(s):
    s = s.strip()
    if s.startswith('"') or s.startswith("'"):
        quote = s[0]
        end = s.find(quote, 1)
        return s[1:end] if end != -1 else s.strip(quote)
    if "#" in s:
        s = s.split("#", 1)[0].strip()
    if s == "" or s in ("~", "null", "Null", "NULL"):
        return None
    if s in ("true", "True", "TRUE"):
        return True
    if s in ("false", "False", "FALSE"):
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def load_yaml_lite(text):
    """Parse a restricted block-style YAML subset into nested dict/list/scalars."""
    lines = []
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        lines.append((indent, stripped))

    root = {}
    stack = [(-1, root)]  # (indent, container)

    i = 0
    while i < len(lines):
        indent, content = lines[i]
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]

        if content.startswith("- "):
            item = content[2:]
            if not isinstance(parent, list):
                raise ValueError(f"expected sequence at indent {indent}: {content!r}")
            if ":" in item and not (item.startswith('"') or item.startswith("'")):
                key, _, val = item.partition(":")
                key = key.strip()
                val = val.strip()
                new_item = {}
                parent.append(new_item)
                if val == "":
                    child = _peek_child_kind(lines, i, indent)
                    new_item[key] = child
                    stack.append((indent, new_item))
                    if child is not None:
                        stack.append((indent, child))
                else:
                    new_item[key] = _parse_scalar(val)
                    stack.append((indent, new_item))
            else:
                parent.append(_parse_scalar(item))
            i += 1
            continue

        if ":" not in content:
            raise ValueError(f"cannot parse line: {content!r}")
        key, _, val = content.partition(":")
        key = key.strip().strip('"').strip("'")
        val = val.strip()
        if not isinstance(parent, dict):
            raise ValueError(f"expected mapping at indent {indent}: {content!r}")
        if val == "":
            child = _peek_child_kind(lines, i, indent)
            parent[key] = child
            if child is not None:
                stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(val)
        i += 1

    return root


def _peek_child_kind(lines, i, indent):
    """Decide whether the line after `i` opens a nested list, dict, or null."""
    if i + 1 < len(lines):
        next_indent, next_content = lines[i + 1]
        if next_indent > indent:
            return [] if next_content.startswith("- ") else {}
    return None


def load_yaml_file(path):
    path = Path(path)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8-sig")
    return load_yaml_lite(text)


# ---------------------------------------------------------------------------
# Marker discovery (§15.3)
# ---------------------------------------------------------------------------

def _stable_sort_key(marker_path, repo_root):
    rel = marker_path.relative_to(repo_root)
    return (len(rel.parts), rel.as_posix())


def find_markers(repo_root):
    """Return [(marker_path, [slot-entry dicts])] for every .layout-slots.yaml
    under repo_root, in §15.5/§15.7's stable order (path depth, then lexical)."""
    repo_root = Path(repo_root)
    markers = []
    for marker_path in repo_root.rglob(".layout-slots.yaml"):
        if any(part in IGNORED_DIR_NAMES for part in marker_path.parts):
            continue
        data = load_yaml_file(marker_path) or {}
        markers.append((marker_path, data.get("slots") or []))
    markers.sort(key=lambda m: _stable_sort_key(m[0], repo_root))
    return markers


def find_slot_markers(markers, slot):
    """Return the [(marker_path, entry)] pairs declaring `slot: <slot>`."""
    found = []
    for marker_path, entries in markers:
        for entry in entries:
            if entry.get("slot") == slot:
                found.append((marker_path, entry))
    return found


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------

def _owning_skill_installed(repo_root, owning_skill):
    """§15.8 S8 (partial install): whether `owning_skill` is part of this
    project's installed skill set. If the repo has no `.github/skills/`
    directory at all (not using this skill-bundle scheme, or a bare test
    fixture), there's nothing to gate against - returns True (no-op,
    preserves pre-Phase-2 behavior)."""
    skills_dir = repo_root / ".github" / "skills"
    if not skills_dir.is_dir():
        return True
    return (skills_dir / owning_skill).is_dir()


def _normalize_workspace_root(config):
    """Return `layout.workspace_root`, trailing-slash-stripped, or None if
    absent/not-a-string/empty. Does NOT check well-formedness (S22) - see
    check_workspace_root_wellformedness for that."""
    layout = config.get("layout")
    if not isinstance(layout, dict):
        return None
    wr = layout.get("workspace_root")
    if not isinstance(wr, str) or wr == "":
        return None
    return wr.rstrip("/")


def resolve_pre_d21_default(slot, config):
    """The slot's pre-D21 documented default (§16.2 step 4) - SLOT_REGISTRY's
    `default_from` config key if set, else its `default`. Unchanged from
    Phase 0/1."""
    spec = SLOT_REGISTRY[slot]
    default_from = spec.get("default_from")
    if default_from:
        node = config
        for key in default_from:
            if not isinstance(node, dict) or key not in node:
                node = None
                break
            node = node[key]
        if isinstance(node, str) and node:
            return node
    return spec["default"]


def resolve_workspace_root_default(slot, config):
    """The slot's workspace_root-relative default (§16.2 step 3 / §16.4), or
    None if `layout.workspace_root` is absent or malformed (`.`/`''`, S22)."""
    wr = _normalize_workspace_root(config)
    if not wr or wr == ".":
        return None
    leaf = SLOT_REGISTRY[slot].get("workspace_root_leaf")
    if not leaf:
        return None
    return f"{wr}/{leaf}"


def resolve_default(slot, config):
    """The slot's *resolved* default (§16.2, resolves M4) - the term D20
    §15.5 calls "documented default" wherever a slot has no marker: the
    workspace_root-relative default (step 3) if `layout.workspace_root` is
    set and well-formed, else the pre-D21 documented default (step 4)."""
    return resolve_workspace_root_default(slot, config) or resolve_pre_d21_default(slot, config)


def resolved_path_for_marker(marker_path, entry, spec, repo_root):
    kind = entry.get("kind", spec["kind"])
    slot_dir = marker_path.parent
    target = slot_dir if kind == "directory" else slot_dir / entry.get("file", "")
    return target.relative_to(repo_root), kind


# ---------------------------------------------------------------------------
# What-L2 resolution helpers (D21 §16.5/§16.7, Phase 3c)
#
# `layers.what_l2.*` are config keys, not SLOT_REGISTRY slots - there's no
# marker file for "what_l2", just path-shaped keys in context-config.yaml.
# Each helper below mirrors the SLOT_REGISTRY resolution pattern
# (explicit config value > workspace_root-relative default > pre-D21
# default), per the §16.4 table row for each key.
# ---------------------------------------------------------------------------

def resolve_what_l2_path(config):
    """`layers.what_l2.path` (§16.4/§16.5): the explicit config value if set,
    else `{workspace_root}/` if `layout.workspace_root` is set and
    well-formed, else the pre-D21 default `docs/requirements/`."""
    what_l2 = (config.get("layers") or {}).get("what_l2")
    if isinstance(what_l2, dict):
        path = what_l2.get("path")
        if isinstance(path, str) and path:
            return path
    wr = _normalize_workspace_root(config)
    if wr and wr != ".":
        return f"{wr}/"
    return "docs/requirements/"


def resolve_what_l2_exclude(config):
    """`layers.what_l2.exclude` (§16.5): list of subtree paths relative to
    `what_l2.path` to skip. Defaults to `[]`."""
    what_l2 = (config.get("layers") or {}).get("what_l2")
    if isinstance(what_l2, dict):
        exclude = what_l2.get("exclude")
        if isinstance(exclude, list):
            return [e for e in exclude if isinstance(e, str)]
    return []


def resolve_what_l2_index_path(config):
    """`layers.what_l2.index_path` (§16.4): the explicit config value if set,
    else `{workspace_root}/cache/specs-out/l2_index.json` if
    `layout.workspace_root` is set and well-formed, else the pre-D21 default
    `specs-out/l2_index.json`."""
    what_l2 = (config.get("layers") or {}).get("what_l2")
    if isinstance(what_l2, dict):
        index_path = what_l2.get("index_path")
        if isinstance(index_path, str) and index_path:
            return index_path
    wr = _normalize_workspace_root(config)
    if wr and wr != ".":
        return f"{wr}/cache/specs-out/l2_index.json"
    return "specs-out/l2_index.json"


# ---------------------------------------------------------------------------
# Path well-formedness (§15.9 #4, S14)
# ---------------------------------------------------------------------------

def check_path_wellformedness(rel_path):
    problems = []
    for part in rel_path.parts:
        if part == "..":
            problems.append("contains a '..' segment - paths must be repo-relative (M3)")
            continue
        # Exact match only (sans extension): "COM1-migration" is a normal,
        # valid Windows folder name - only "COM1"/"COM1.ext" etc. are reserved.
        base = part.split(".", 1)[0].upper()
        if base in WINDOWS_RESERVED_NAMES:
            problems.append(f"segment '{part}' is a Windows-reserved device name (S14)")
        if part != part.rstrip(" .") and part not in (".", ".."):
            problems.append(f"segment '{part}' has a trailing space or '.' - invalid on Windows (S14)")
    return problems


# ---------------------------------------------------------------------------
# workspace_root well-formedness (D21 §16.2, S22)
# ---------------------------------------------------------------------------

def check_workspace_root_wellformedness(config):
    """§16.2/S22: `layout.workspace_root`, if present, must be a non-empty
    repo-relative path other than '.' or ''. Returns a list of problem
    strings (empty if the key is absent or well-formed)."""
    layout = config.get("layout")
    if not isinstance(layout, dict) or "workspace_root" not in layout:
        return []
    wr = layout.get("workspace_root")
    if not isinstance(wr, str) or wr.rstrip("/") in ("", "."):
        return [
            f"layout.workspace_root = {wr!r} is invalid - the repo root "
            f"cannot be the workspace root (S22). Use a repo-relative "
            f"subdirectory (e.g. 'docs/'), or remove the key entirely to "
            f"opt out."
        ]
    problems = check_path_wellformedness(Path(wr.rstrip("/")))
    return [f"layout.workspace_root = '{wr}' - {p}" for p in problems]


# ---------------------------------------------------------------------------
# What-L2 exclude/index_path checks (D21 §16.5/§16.11, Phase 3c)
# ---------------------------------------------------------------------------

def check_what_l2_index_path_excluded(config):
    """§16.5 M3 invariant: if `what_l2.index_path` resolves to a path under
    `what_l2.path`, it MUST be covered by a `what_l2.exclude` entry - else
    What-L2 could index its own index file. Returns a list of problem strings
    (empty if `index_path` resolves outside `what_l2.path` entirely - the
    default whenever `layout.workspace_root` is unset - or is covered by an
    exclude entry)."""
    what_l2_parts = Path(resolve_what_l2_path(config).rstrip("/")).parts
    index_parts = Path(resolve_what_l2_index_path(config)).parts

    if index_parts[:len(what_l2_parts)] != what_l2_parts:
        return []

    rel_parts = index_parts[len(what_l2_parts):]

    exclude_parts = []
    for entry in resolve_what_l2_exclude(config):
        stripped = entry.rstrip("/\\")
        if stripped:
            exclude_parts.append(Path(stripped).parts)

    if any(rel_parts[:len(ep)] == ep for ep in exclude_parts):
        return []

    return [
        f"layers.what_l2.index_path = '{resolve_what_l2_index_path(config)}' "
        f"resolves under layers.what_l2.path = "
        f"'{resolve_what_l2_path(config)}' but is not covered by any "
        f"what_l2.exclude entry (M3 invariant, §16.5) - What-L2 could index "
        f"its own index file. Add an exclude entry covering "
        f"'{rel_parts[0]}/'."
    ]


def check_what_l2_exclude_typos(repo_root, config):
    """§16.11 S21 / round-2 L2: each `what_l2.exclude` entry should
    prefix-match an existing subtree under `what_l2.path`, checked
    case-sensitively at validation time (reuses S12's cross-platform
    case-sensitivity machinery). An entry that matches nothing existing under
    `what_l2.path` is a likely typo or case mismatch (S21) - WARN, since it
    silently widens the indexed corpus rather than breaking anything outright.
    A no-op if `what_l2.exclude` is empty, or if `what_l2.path` itself doesn't
    exist yet (S19's "correctly-spelled, doesn't-exist-yet" framing - nothing
    to compare against)."""
    exclude = resolve_what_l2_exclude(config)
    if not exclude:
        return []

    target = Path(repo_root) / resolve_what_l2_path(config).rstrip("/")
    if not target.is_dir():
        return []

    existing_parts = {p.relative_to(target).parts for p in target.rglob("*")}

    problems = []
    for entry in exclude:
        stripped = entry.rstrip("/\\")
        if not stripped:
            continue
        entry_parts = Path(stripped).parts
        if not any(parts[:len(entry_parts)] == entry_parts for parts in existing_parts):
            problems.append(
                f"what_l2.exclude entry '{entry}' does not match any existing "
                f"subtree under '{resolve_what_l2_path(config)}' (S21) - check "
                f"spelling and case; if the directory simply doesn't exist yet, "
                f"this entry is harmless (S19)."
            )
    return problems


# ---------------------------------------------------------------------------
# Config-vanished git-history check (§15.9 #6, S4)
# ---------------------------------------------------------------------------

def check_git_history(repo_root, config):
    try:
        result = subprocess.run(
            ["git", "log", "--all", "-S", "initialized: true", "--", "context-config.yaml"],
            cwd=str(repo_root), capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    had_history = bool(result.stdout.strip())
    has_current = isinstance(config.get("project_layout"), dict)
    if had_history and not has_current:
        return (
            "FAIL: context-config.yaml's history contains 'initialized: true' "
            "(project_layout was configured at some point), but the current "
            "file has no project_layout section - likely accidental deletion "
            "(S4). Run /ult-repo-layout reconcile."
        )
    return None


# ---------------------------------------------------------------------------
# layout-slots-registry.yaml consistency check (D21 §16.8, Phase 3e)
# ---------------------------------------------------------------------------

def check_registry_consistency(repo_root):
    """D21 §16.8: if `layout-slots-registry.yaml` exists at `repo_root` (the
    library-level superset registry - never copied into consuming projects),
    its `slots:` entries with `project_layout_slot: true` must exactly match
    SLOT_REGISTRY's keys (this script's source of truth). FAIL on drift in
    either direction. Returns [] (no-op) if the file is absent - true for
    every consuming project and every test fixture in this suite."""
    registry = load_yaml_file(Path(repo_root) / "layout-slots-registry.yaml")
    if registry is None:
        return []

    registry_ids = {
        entry.get("id")
        for entry in (registry.get("slots") or [])
        if isinstance(entry, dict) and entry.get("project_layout_slot") is True
    }
    code_ids = set(SLOT_REGISTRY.keys())

    problems = []
    for missing in sorted(code_ids - registry_ids):
        problems.append(
            f"SLOT_REGISTRY has slot '{missing}', but layout-slots-registry.yaml "
            f"has no 'slots:' entry for it with project_layout_slot: true "
            f"(registry/code drift, §16.8)."
        )
    for extra in sorted(registry_ids - code_ids):
        problems.append(
            f"layout-slots-registry.yaml declares slot '{extra}' with "
            f"project_layout_slot: true, but SLOT_REGISTRY has no entry for "
            f"it (registry/code drift, §16.8)."
        )
    return problems


# ---------------------------------------------------------------------------
# Top-level validation
# ---------------------------------------------------------------------------

def validate(repo_root):
    """Run all §15.9 checks. Returns (ok: bool, report: list[str])."""
    repo_root = Path(repo_root).resolve()
    report = []
    ok = True

    config = load_yaml_file(repo_root / "context-config.yaml") or {}
    markers = find_markers(repo_root)

    resolved_paths = {}  # slot -> (rel_path, kind)
    any_marker_for_registered_slot = False

    for slot, spec in SLOT_REGISTRY.items():
        if not _owning_skill_installed(repo_root, spec["owning_skill"]):
            continue

        matches = find_slot_markers(markers, slot)

        if not matches:
            default = resolve_default(slot, config)
            report.append(
                f"INFO: slot '{slot}' has no marker - not yet initialized via "
                f"ult-repo-layout; using default '{default}'. Run "
                f"/ult-repo-layout init or reconcile to register it."
            )

            # S18 (D21 §16.2/§16.9, resolves M5): an unmarked slot whose
            # pre-D21 default AND workspace_root-relative default both exist
            # on disk looks like a partial migration - non-blocking warn.
            wr_default = resolve_workspace_root_default(slot, config)
            pre_default = resolve_pre_d21_default(slot, config)
            if wr_default and wr_default != pre_default:
                if (repo_root / pre_default).exists() and (repo_root / wr_default).exists():
                    report.append(
                        f"WARN: slot '{slot}' has content at both its pre-D21 "
                        f"default ('{pre_default}') and its workspace_root-relative "
                        f"default ('{wr_default}'), but no marker - looks like a "
                        f"partial migration (S18). Run /ult-repo-layout reconcile "
                        f"to choose one location; until then, the unmarked "
                        f"resolved default ('{wr_default}') is used."
                    )
            continue

        any_marker_for_registered_slot = True

        if len(matches) > 1:
            ok = False
            locs = ", ".join(
                (m.parent.relative_to(repo_root).as_posix() or ".") for m, _ in matches
            )
            report.append(
                f"FAIL: slot '{slot}' has markers at multiple locations "
                f"({locs}) - bijectivity violation (S15). Run "
                f"/ult-repo-layout reconcile to resolve."
            )
            continue

        marker_path, entry = matches[0]
        rel_path, kind = resolved_path_for_marker(marker_path, entry, spec, repo_root)
        resolved_paths[slot] = (rel_path, kind)

        target = repo_root / rel_path
        if target.exists():
            actual_kind = "directory" if target.is_dir() else "file"
            if actual_kind != kind:
                ok = False
                report.append(
                    f"FAIL: slot '{slot}' declares kind '{kind}' but "
                    f"'{rel_path.as_posix()}' is a {actual_kind} on disk "
                    f"(type-consistency violation)."
                )
        else:
            report.append(
                f"INFO: slot '{slot}' marker found at '{rel_path.as_posix()}' "
                f"but that path doesn't exist yet."
            )

        cached = (
            config.get("project_layout", {})
            .get("slots", {})
            .get(slot, {})
            .get("path")
        )
        if cached:
            cached_norm = cached.rstrip("/")
            resolved_norm = rel_path.as_posix().rstrip("/") or "."
            if cached_norm != resolved_norm:
                report.append(
                    f"NOTE: project_layout.slots.{slot}.path = '{cached}' but "
                    f"its marker is at '{rel_path.as_posix()}/' - the index is "
                    f"stale (S5). Run /ult-repo-layout reconcile to refresh it."
                )

    # Cross-slot bijectivity: no two slots resolve to the same path.
    seen = {}
    for slot, (rel_path, _kind) in resolved_paths.items():
        if rel_path in seen:
            ok = False
            report.append(
                f"FAIL: slots '{seen[rel_path]}' and '{slot}' both resolve to "
                f"'{rel_path.as_posix()}' (bijectivity violation)."
            )
        else:
            seen[rel_path] = slot

    # Nesting (§15.9 #3): flag same-kind slots sharing a path prefix, excluding
    # '.' (repo root) per H4. With one registered slot this is a no-op.
    items = list(resolved_paths.items())
    for idx, (slot_a, (path_a, kind_a)) in enumerate(items):
        for slot_b, (path_b, kind_b) in items[idx + 1:]:
            if kind_a != kind_b:
                continue
            if path_a == Path(".") or path_b == Path("."):
                continue
            a_parts, b_parts = path_a.parts, path_b.parts
            shorter, longer = (a_parts, b_parts) if len(a_parts) <= len(b_parts) else (b_parts, a_parts)
            if longer[: len(shorter)] == shorter:
                ok = False
                report.append(
                    f"FAIL: slots '{slot_a}' ('{path_a.as_posix()}') and "
                    f"'{slot_b}' ('{path_b.as_posix()}') nest (same kind, "
                    f"shared path prefix) with no 'nests_under:' whitelist "
                    f"entry covering this pair."
                )

    # Path well-formedness (S14 / M3) on every marker directory.
    for marker_path, _entries in markers:
        rel = marker_path.parent.relative_to(repo_root)
        for problem in check_path_wellformedness(rel):
            ok = False
            report.append(f"FAIL: marker at '{rel.as_posix()}' - {problem}")

    # Cross-platform normalization (S12): project_layout.slots.*.path must be
    # POSIX-style (no backslashes).
    for slot, info in (config.get("project_layout", {}).get("slots", {}) or {}).items():
        path = info.get("path") if isinstance(info, dict) else None
        if isinstance(path, str) and "\\" in path:
            ok = False
            report.append(
                f"FAIL: project_layout.slots.{slot}.path = '{path}' uses "
                f"backslashes - must be POSIX-style forward slashes (S12)."
            )

    # Config-vanished git-history check (S4).
    s4 = check_git_history(repo_root, config)
    if s4:
        ok = False
        report.append(s4)

    # workspace_root well-formedness (D21 §16.2, S22): '.'/'' is a hard-stop,
    # not a silent fallback to either default.
    for problem in check_workspace_root_wellformedness(config):
        ok = False
        report.append(f"FAIL: {problem}")

    # what_l2.index_path exclusion (D21 §16.5, M3 invariant).
    for problem in check_what_l2_index_path_excluded(config):
        ok = False
        report.append(f"FAIL: {problem}")

    # what_l2.exclude typo check (D21 §16.11 S21 / round-2 L2) - non-blocking.
    for problem in check_what_l2_exclude_typos(repo_root, config):
        report.append(f"WARN: {problem}")

    # layout-slots-registry.yaml consistency (D21 §16.8, Phase 3e) - no-op if
    # the file is absent (every consuming project and test fixture).
    for problem in check_registry_consistency(repo_root):
        ok = False
        report.append(f"FAIL: {problem}")

    if not any_marker_for_registered_slot and "project_layout" not in config:
        report.insert(
            0,
            "INFO: project_layout is not initialized for this repo. Run "
            "/ult-repo-layout init (new project) or "
            "/ult-repo-layout discover (existing project) to set it up.",
        )

    return ok, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", nargs="?", default=".", help="repo root (default: .)")
    parser.add_argument("--validate", action="store_true", help="run all checks and report")
    args = parser.parse_args(argv)

    if not args.validate:
        parser.print_help(sys.stderr)
        return 2

    ok, report = validate(args.repo_root)
    for line in report:
        print(line)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
