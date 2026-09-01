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
  11. Layer path population (D23 §17.8, S28) - WARN if an
      *enabled* layer's resolved path (`layers.what_l2.path`,
      `layers.what_l1.path`, `how_dimension.how_l2.path`,
      `how_dimension.how_l1.path`) doesn't exist or contains no files.
      What-L2/How-L2 are always checked (no opt-out in the shipped config
      surface); What-L1/How-L1 are checked only when their own `enabled: true`
      is set - a disabled opt-in layer left at its placeholder/absent `path`
      never warns. Closes the silent-fallback risk described in
      `ult-context-generate/SKILL.md:1122-1128` (a misconfigured path and a
      genuinely empty layer previously produced identical, silent behavior).

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
    python validate_layout.py --init [--workspace-root <path>] [--ci-hook] [--dry-run] [<repo-root>]

`--init` backs only the mechanical half of SKILL.md's `init` mode - scaffold
each installed slot's directory/marker, write `project_layout` into
context-config.yaml, and, only with `--ci-hook` (opt-in - omitted by
default), a pre-commit hook. The conversational half (asking the human for
project_name/description, whether to opt into workspace_root, generating
context-config.yaml itself, offering to rename/relocate a slot's default
location, suggesting - never silently adding - what_l2.include_roots) stays
the agent's job; see `run_init` below and SKILL.md's `init` section.
"""

import argparse
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# §15.2 slot registry (Phase 1: context_packages; Phase 3b: + plans_output,
# brainstorm_output; Phase 2: + compiled_guidelines, user_stories_output,
# security_docs, security_report, project_plan_docs; trip-wire:
# + decision_ledger; D24 Phase B: + autoscaffold_content_state,
# autoscaffold_content_index)
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
        "default": "output_docs/plans/",
        # D21 §16.4 (Gap-B, NEW slot - no pre-existing config-key fallback).
        "workspace_root_leaf": "outputs/plans/",
        # illustrative -- not shipped in this repo
        "owning_skill": "example-plan-writer",
    },
    "brainstorm_output": {
        "kind": "directory",
        "default": "output_docs/brainstorm/",
        # D21 §16.4 (Gap-B, NEW slot - no pre-existing config-key fallback).
        "workspace_root_leaf": "outputs/brainstorm/",
        # illustrative -- not shipped in this repo
        "owning_skill": "example-brainstorm-writer",
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
        "owning_skill": "example-consumer",
    },
    "security_docs": {
        "kind": "directory",
        "default": "output_docs/security_docs/",
        "workspace_root_leaf": "outputs/security_docs/",
        "owning_skill": "example-threat-modeler",
    },
    "security_report": {
        "kind": "directory",
        "default": "output_docs/security_report/",
        "workspace_root_leaf": "outputs/security_report/",
        "owning_skill": "example-report-writer",
    },
    "project_plan_docs": {
        "kind": "directory",
        "default": "output_docs/project_plan_docs/",
        "workspace_root_leaf": "outputs/project_plan_docs/",
        "owning_skill": "example-project-planner",
    },
    "decision_ledger": {
        "kind": "file",
        "default": "starter_kit/decision_ledger/DECISION-LEDGER.json",
        # trip-wire - a derived/regenerable artifact
        # (entries only ever added via decision_ledger.py, never hand-edited),
        # same bucket-reassignment rationale as compiled_guidelines above.
        "workspace_root_leaf": "cache/decision-ledger/DECISION-LEDGER.json",
        "owning_skill": "ult-institutional-memory-distill",
    },
    "autoscaffold_content_state": {
        "kind": "file",
        "default": "starter_kit/autoscaffold-content/TRIAGE-STATE.json",
        # D24 Phase B - a derived/regenerable checkpoint (per-module tier/
        # status/output_path), only ever written via scaffold_state.py,
        # same bucket-reassignment rationale as decision_ledger above.
        "workspace_root_leaf": "cache/autoscaffold-content/TRIAGE-STATE.json",
        "owning_skill": "ult-autoscaffold-content",
    },
    "autoscaffold_content_index": {
        "kind": "file",
        "default": "starter_kit/autoscaffold-content/CEP-INDEX.md",
        # D24 Phase B - rendered from autoscaffold_content_state by
        # scaffold_state.py render-index, never hand-edited.
        "workspace_root_leaf": "cache/autoscaffold-content/CEP-INDEX.md",
        "owning_skill": "ult-autoscaffold-content",
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


def resolve_what_l2_path_for_init(config, effective_workspace_root):
    """Like resolve_what_l2_path, but resolves against an explicit
    workspace_root value instead of re-reading `layout.workspace_root` from
    config. run_init needs this: when --workspace-root is passed to the
    same `init` call, it hasn't been persisted to context-config.yaml yet
    at the point run_init decides whether What-L2's shipped default path
    exists on disk."""
    what_l2 = (config.get("layers") or {}).get("what_l2")
    if isinstance(what_l2, dict):
        path = what_l2.get("path")
        if isinstance(path, str) and path:
            return path
    if effective_workspace_root and effective_workspace_root != ".":
        return f"{effective_workspace_root}/"
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


def resolve_what_l2_include_roots(config):
    """`layers.what_l2.include_roots` (§16.7): list of additional directory
    paths, relative to the repo root, indexed wholesale alongside
    `what_l2.path`. Defaults to `[]`."""
    what_l2 = (config.get("layers") or {}).get("what_l2")
    if isinstance(what_l2, dict):
        include_roots = what_l2.get("include_roots")
        if isinstance(include_roots, list):
            return [r for r in include_roots if isinstance(r, str)]
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


def resolve_what_l2_enabled(config):
    """`layers.what_l2.enabled`: defaults to True (the starter kit ships
    What-L2 always-on, unlike the opt-in What-L1/How-L1) if absent or not a
    dict. `run_init` is the only code path that ever writes this key
    explicitly, and only when the layer's own shipped default path doesn't
    exist yet in the target repo (S28) - see run_init's own comment."""
    what_l2 = (config.get("layers") or {}).get("what_l2")
    if isinstance(what_l2, dict):
        return bool(what_l2.get("enabled", True))
    return True


def resolve_what_l2_path_explicit(config):
    """True if `layers.what_l2.path` is set explicitly in config, as
    opposed to falling back to the workspace_root-relative or pre-D21
    default inside resolve_what_l2_path. run_init uses this to avoid
    silently disabling a path the user deliberately configured, even if
    that path doesn't exist on disk yet."""
    what_l2 = (config.get("layers") or {}).get("what_l2")
    return isinstance(what_l2, dict) and bool(what_l2.get("path"))


# ---------------------------------------------------------------------------
# What-L1 / How-L2 / How-L1 resolution helpers (D23 §17.8, S28)
#
# Unlike what_l2 (above), none of these three get a `workspace_root`-relative
# default - §16.5's widening is specific to What-L2 (D21). How-L2 has a
# documented pre-D21 default (`org/`, ult-context-generate/SKILL.md:106);
# What-L1/How-L1 are opt-in with no documented fallback path - an enabled
# layer with no `path` set has nothing to resolve, which is itself the S28
# condition (see check_layer_paths_populated).
# ---------------------------------------------------------------------------

def resolve_how_l2_path(config):
    """`how_dimension.how_l2.path`: the explicit config value if set, else the
    pre-D21 documented default `org/` (ult-context-generate/SKILL.md:106)."""
    how_l2 = (config.get("how_dimension") or {}).get("how_l2")
    if isinstance(how_l2, dict):
        path = how_l2.get("path")
        if isinstance(path, str) and path:
            return path
    return "org/"


def resolve_how_l2_enabled(config):
    """`how_dimension.how_l2.enabled`: defaults to True, same rationale as
    resolve_what_l2_enabled."""
    how_l2 = (config.get("how_dimension") or {}).get("how_l2")
    if isinstance(how_l2, dict):
        return bool(how_l2.get("enabled", True))
    return True


def resolve_how_l2_path_explicit(config):
    """True if `how_dimension.how_l2.path` is set explicitly in config -
    same rationale as resolve_what_l2_path_explicit."""
    how_l2 = (config.get("how_dimension") or {}).get("how_l2")
    return isinstance(how_l2, dict) and bool(how_l2.get("path"))


def resolve_what_l1_path(config):
    """`layers.what_l1.path`: the explicit config value if set, else None -
    What-L1 is opt-in with no documented fallback path."""
    what_l1 = (config.get("layers") or {}).get("what_l1")
    if isinstance(what_l1, dict):
        path = what_l1.get("path")
        if isinstance(path, str) and path:
            return path
    return None


def resolve_what_l1_enabled(config):
    """`layers.what_l1.enabled`: defaults to False (opt-in, per the starter
    kit template) if absent or not a dict."""
    what_l1 = (config.get("layers") or {}).get("what_l1")
    if isinstance(what_l1, dict):
        return bool(what_l1.get("enabled", False))
    return False


def resolve_how_l1_path(config):
    """`how_dimension.how_l1.path`: the explicit config value if set, else
    None - How-L1 is opt-in with no documented fallback path."""
    how_l1 = (config.get("how_dimension") or {}).get("how_l1")
    if isinstance(how_l1, dict):
        path = how_l1.get("path")
        if isinstance(path, str) and path:
            return path
    return None


def resolve_how_l1_enabled(config):
    """`how_dimension.how_l1.enabled`: defaults to False (opt-in, per the
    starter kit template) if absent or not a dict."""
    how_l1 = (config.get("how_dimension") or {}).get("how_l1")
    if isinstance(how_l1, dict):
        return bool(how_l1.get("enabled", False))
    return False


# ---------------------------------------------------------------------------
# Path well-formedness (§15.9 #4, S14)
# ---------------------------------------------------------------------------

def check_path_wellformedness(rel_path):
    problems = []
    # An absolute path (POSIX '/...', Windows 'C:\...', or a UNC share
    # '\\server\share\...') is never repo-relative, and joining one onto a
    # root with pathlib silently discards the root rather than raising -
    # `repo_root / rel_path` just becomes `rel_path` itself. Every caller of
    # this function (run_init's --workspace-root, config's layout.workspace_root,
    # and the per-marker well-formedness loop) needs that path rejected here
    # rather than at the join site, since the join site cannot tell the
    # difference between "joined fine" and "silently replaced" after the fact
    # (2026-09-01: closes the gap where such a value reached an HTTP-exposed
    # write path unchecked).
    #
    # `.is_absolute()`/`.drive` alone are not enough: a POSIX-style value
    # like "/etc/x" parsed as a plain `Path` on a Windows host becomes a
    # `WindowsPath` with no drive, and pathlib does NOT consider a driveless
    # rooted path "absolute" on Windows - yet `repo_root / "/etc/x"` still
    # discards `repo_root` the same way. `.root` catches that case (and every
    # other rooted-but-driveless variant) on any host OS without needing to
    # know in advance which OS produced the string.
    if rel_path.is_absolute() or rel_path.drive or rel_path.root:
        problems.append(
            f"'{rel_path}' is an absolute path - paths must be repo-relative (M3)"
        )
        return problems
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
# Layer path population check (D23 §17.8, S28)
# ---------------------------------------------------------------------------

def check_layer_paths_populated(repo_root, config):
    """§17.8/S28: WARN if an *enabled* layer's resolved path doesn't exist or
    contains no files. What-L2 and How-L2 default to `enabled: true` (the
    starter kit ships them always-on) and are checked unless `run_init` has
    explicitly set `enabled: false` for one - it does this only when that
    layer's own shipped default path doesn't exist yet in the target repo,
    so a fresh install validates silent-clean instead of warning about its
    own shipped defaults on day one (see run_init). What-L1 and How-L1 are
    opt-in and checked only when their own `enabled: true` is set. A
    disabled What-L1/How-L1 - the starter kit's default - is never checked,
    so leaving an opt-in layer at its placeholder or absent `path` never
    warns.

    Before this check, a misconfigured path and a project that genuinely has
    no such content produced identical, silent behavior (D8 fallback,
    `ult-context-generate/SKILL.md:1122-1128`). This does not fix that
    fallback - it only surfaces, non-blockingly, that the fallback is about
    to be taken for a layer the project declared it wants."""
    problems = []

    layer_checks = [
        ("layers.what_l2", resolve_what_l2_path(config), resolve_what_l2_enabled(config)),
        ("how_dimension.how_l2", resolve_how_l2_path(config), resolve_how_l2_enabled(config)),
        ("layers.what_l1", resolve_what_l1_path(config), resolve_what_l1_enabled(config)),
        ("how_dimension.how_l1", resolve_how_l1_path(config), resolve_how_l1_enabled(config)),
    ]

    for label, path, enabled in layer_checks:
        if not enabled:
            continue
        if not path:
            problems.append(
                f"{label} is enabled but no path is configured (S28) - this "
                f"layer will silently resolve as empty. Set {label}.path, or "
                f"set {label}.enabled: false if this layer is intentionally "
                f"unused."
            )
            continue
        target = Path(repo_root) / path.rstrip("/")
        if not target.exists():
            problems.append(
                f"{label}.path = '{path}' is enabled but does not exist "
                f"(S28) - this layer will silently resolve as empty rather "
                f"than surfacing a configuration mistake. Create the "
                f"directory, fix the path, or set {label}.enabled: false if "
                f"this layer is intentionally unused."
            )
        elif target.is_dir() and not any(target.rglob("*")):
            problems.append(
                f"{label}.path = '{path}' is enabled and exists but is "
                f"empty (S28) - this layer will silently resolve as empty. "
                f"Add content, fix the path, or set {label}.enabled: false "
                f"if this layer is intentionally unused."
            )
    return problems


# ---------------------------------------------------------------------------
# Layer candidate path population check (D23 §17.8 per-candidate extension,
# second adversarial review C-2)
# ---------------------------------------------------------------------------

def check_layer_candidate_paths_populated(repo_root, config):
    """§17.8 C-2 addendum (per-candidate extension, D23 second adversarial
    review): once `include_roots` entries exist, the shipped primary-path
    check above never inspects them - only `what_l2.path` itself. WARN if any
    confirmed `include_roots[i]` entry doesn't exist or is empty, exactly the
    same silent-empty-layer risk §17.8 exists to catch for the primary path.
    `exclude` entries are deliberately not duplicated here:
    `check_what_l2_exclude_typos` already WARNs when an exclude entry matches
    nothing existing, and an empty-but-existing excluded directory is a
    harmless no-op with no actionable claim behind a WARN."""
    problems = []
    target_base = Path(repo_root)
    for i, rel in enumerate(resolve_what_l2_include_roots(config)):
        label = f"layers.what_l2.include_roots[{i}]"
        target = target_base / rel.rstrip("/")
        if not target.exists():
            problems.append(
                f"{label} = '{rel}' does not exist (§17.8 per-candidate "
                f"extension) - this content root will silently resolve as "
                f"empty. Fix the path, remove the entry, or restore the "
                f"directory."
            )
        elif target.is_dir() and not any(target.rglob("*")):
            problems.append(
                f"{label} = '{rel}' exists but is empty (§17.8 per-candidate "
                f"extension) - this content root will silently resolve as "
                f"empty. Add content or remove the entry."
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
# Comment-preserving YAML editor (no pyyaml dependency - load_yaml_lite above
# discards comments and cannot round-trip). This is the same engine
# confirm_layers.py already has (its own "Comment-preserving YAML editor"
# section) - duplicated here rather than imported, because
# layout_decision_grammar.py (the one module this skill already shares
# between discover_layers.py/confirm_layers.py/wizard_layout_source.py)
# documents this write engine as deliberately staying local to
# confirm_layers.py, bound up with run_confirm's atomicity contract, not
# reusable vocabulary; and importing confirm_layers.py itself here would be
# circular (confirm_layers.py already imports this module as `vl`). Same
# no-shared-library-across-modules convention as the manifest reader in
# each of cep_retrofit.py/scaffold_state.py/wizard_docs.py/discover_layers.py.
# `run_init` below is this module's own first marker/config *writer* - every
# other function above it is read-only.
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


def _remove_top_level_key(lines, name):
    """Remove an existing top-level `name:` mapping block (key line through
    its full scope) in place, if present. No-op if absent."""
    idx = _find_child(lines, 0, len(lines), 0, name)
    if idx is None:
        return
    end = _scope_end(lines, idx + 1, 0)
    del lines[idx:end]


# ---------------------------------------------------------------------------
# init mode (§15.5/§16.2, mechanical half only - see module docstring)
# ---------------------------------------------------------------------------

PRE_COMMIT_HOOK_TEXT = (
    "#!/bin/sh\n"
    "# Scaffolded by `ult-repo-layout init --ci-hook` (SKILL.md \"CI / "
    "pre-commit hook\", S15.9). No LLM involved - a deterministic "
    "project_layout check. Fails open (exit 0) rather than blocking a\n"
    "# commit if python3/python isn't on PATH or the check itself errors -\n"
    "# this hook is meant to be a convenience nudge, never a hard gate an\n"
    "# adopter didn't explicitly ask for.\n"
    "PY=$(command -v python3 || command -v python) || exit 0\n"
    "\"$PY\" .github/skills/ult-repo-layout/scripts/validate_layout.py --validate || exit 0\n"
)


def _scaffold_pre_commit_hook(repo_root):
    """Write a `.git/hooks/pre-commit` wrapper invoking `validate_layout.py
    --validate`, per SKILL.md's "CI / pre-commit hook" section - the doc's
    own "no LLM involved, just wire it in" framing, and the one integration
    point that exists in every git repo without guessing which CI system is
    present. Never overwrites an existing hook. Returns a message string
    describing what happened (scaffolded / skipped-and-why), never raises."""
    hooks_dir = repo_root / ".git" / "hooks"
    if not hooks_dir.is_dir():
        return (
            "Skipped pre-commit hook - no .git/hooks/ directory found. Wire "
            "'validate_layout.py --validate' into your CI/pre-commit setup "
            "by hand (see SKILL.md \"CI / pre-commit hook\")."
        )
    hook_path = hooks_dir / "pre-commit"
    if hook_path.exists():
        return (
            f"Skipped pre-commit hook - '{hook_path.relative_to(repo_root).as_posix()}' "
            f"already exists. Add 'python .github/skills/ult-repo-layout/scripts/"
            f"validate_layout.py --validate' to it by hand if you want this "
            f"check wired in."
        )
    hook_path.write_text(PRE_COMMIT_HOOK_TEXT, encoding="utf-8")
    try:
        hook_path.chmod(hook_path.stat().st_mode | 0o111)
    except OSError:
        pass  # best-effort - e.g. unsupported on this filesystem
    return f"Scaffolded pre-commit hook at '{hook_path.relative_to(repo_root).as_posix()}'."


def _preview_pre_commit_hook(repo_root):
    """Read-only sibling of `_scaffold_pre_commit_hook` for `run_init(...,
    dry_run=True)` - same three branches, same phrasing, never writes
    anything. Kept separate rather than adding a `dry_run` flag to the real
    function because the two are trivial (two existence checks) and the
    "Would " prefix on every branch reads more clearly as its own small
    function than as a parameterized one."""
    hooks_dir = repo_root / ".git" / "hooks"
    if not hooks_dir.is_dir():
        return (
            "Would skip pre-commit hook - no .git/hooks/ directory found. Wire "
            "'validate_layout.py --validate' into your CI/pre-commit setup "
            "by hand (see SKILL.md \"CI / pre-commit hook\")."
        )
    hook_path = hooks_dir / "pre-commit"
    if hook_path.exists():
        return (
            f"Would skip pre-commit hook - "
            f"'{hook_path.relative_to(repo_root).as_posix()}' already exists."
        )
    return (
        f"Would scaffold pre-commit hook at "
        f"'{hook_path.relative_to(repo_root).as_posix()}'."
    )


def _marker_entry_lines(slot, kind, file_name):
    lines = [f"  - slot: {slot}", f"    kind: {kind}"]
    if file_name:
        lines.append(f"    file: {file_name}")
    lines.append(f"    schema_version: {2 if kind == 'file' else 1}")
    return lines


def _write_marker(marker_dir, slot, kind, file_name):
    """Write or extend `<marker_dir>/.layout-slots.yaml` with one new
    `slot:` entry (see "Marker file format" in SKILL.md). Slots that resolve
    to the same directory share one marker file's `slots:` list - if the
    file already exists (a sibling `kind: file` slot scaffolded earlier in
    this same `init` run, e.g. autoscaffold_content_state and
    autoscaffold_content_index sharing one directory), the new entry is
    appended rather than the file being overwritten."""
    marker_path = marker_dir / ".layout-slots.yaml"
    entry_lines = _marker_entry_lines(slot, kind, file_name)
    if marker_path.exists():
        existing = load_yaml_file(marker_path) or {}
        already_present = any(
            isinstance(e, dict) and e.get("slot") == slot
            for e in (existing.get("slots") or [])
        )
        if already_present:
            return
        lines = marker_path.read_text(encoding="utf-8-sig").splitlines()
        lines.extend(entry_lines)
        marker_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        marker_path.write_text("slots:\n" + "\n".join(entry_lines) + "\n", encoding="utf-8")


def _write_project_layout_section(lines, entries):
    """Append a fresh `project_layout:` block with one `slots:` entry per
    `(slot -> (path, kind, owning_skill))` in `entries` (insertion order),
    replacing any existing `project_layout:` scope outright. `run_init` only
    ever reaches this after its refuse-if-initialized gate, so there is
    nothing to merge - only a stray partial block (e.g. from a previously
    interrupted `init` run) to clear before writing the real one."""
    _remove_top_level_key(lines, "project_layout")
    if lines and lines[-1].strip() != "":
        lines.append("")
    block = ["project_layout:", "  version: 1", "  initialized: true", "  slots:"]
    for slot, (path, kind, owning_skill) in entries.items():
        block.append(f"    {slot}:")
        block.append(f"      path: {path}")
        block.append(f"      kind: {kind}")
        block.append(f"      owning_skill: {owning_skill}")
    lines.extend(block)


def run_init(repo_root, workspace_root=None, ci_hook=False, dry_run=False):
    """Back only the mechanical half of `init` mode (SKILL.md "Modes >
    init") - scaffold each installed slot's directory/marker, write
    `project_layout` into context-config.yaml, and, only if `ci_hook` is
    explicitly requested (opt-in - a fresh `init` never touches
    `.git/hooks/` on its own), a pre-commit hook. The conversational half -
    asking the human for project_name/description, whether to opt into
    workspace_root, generating context-config.yaml itself from the
    starter-kit template, offering to rename/relocate a slot's default
    location before scaffolding, and suggesting (never silently adding)
    what_l2.include_roots when output_docs_structure/ exists - stays the
    agent's job: the same split every other ult-* skill in this repo
    already draws between SKILL.md-driven agent behavior and a
    deterministic script (confirm_layers.py's own "agent/human produces the
    decisions, the script applies them atomically" precedent).

    An already-initialized repo is refused (project_layout is never
    rewritten) with one exception: `ci_hook=True` on a repeat call
    scaffolds the pre-commit hook alone and succeeds, since the hook is
    opt-in and would otherwise be unreachable after the first `init`.

    `dry_run=True` (ISSUES.md Round 2 finding 9, 2026-08-31 - the wizard's
    first-run `workspace_root` preview, `/api/init/preview`) runs every
    eligibility check and the full slot-resolution loop exactly as a real
    call would, but performs none of the actual writes (`mkdir`, marker
    files, `context-config.yaml`, the pre-commit hook) - it exists so a
    caller can show "here's what init would do" before committing to it,
    reusing this function's own resolution logic instead of a second,
    driftable copy of it (same reuse-not-reimplement posture as every other
    resolver in this module). Messages say "Would <verb>" instead of the
    real past-tense verb so a preview can never be mistaken for a completed
    run if logged or displayed verbatim. An already-initialized repo still
    returns the same refusal in preview mode - there is nothing left to
    preview once `project_layout` is set.

    Returns (exit_code, messages) - 0/[...] on success, 1/[...] on
    refusal - identical shape whether or not `dry_run` is set."""
    repo_root = Path(repo_root).resolve()
    config_path = repo_root / "context-config.yaml"
    if not config_path.exists():
        return 1, [
            "context-config.yaml not found - generate it first "
            "(install.ps1/install.sh -InitProject, or copy "
            "starter_kits/context_engineering/context-config.yaml.template "
            "by hand). init only writes project_layout, not the rest of "
            "the config file.",
        ]

    config = load_yaml_file(config_path) or {}
    existing_project_layout = config.get("project_layout")
    if isinstance(existing_project_layout, dict) and existing_project_layout.get("initialized"):
        if ci_hook:
            # The pre-commit hook is opt-in, so an adopter who ran `init`
            # without --ci-hook and later wants the hook has no other way
            # to ask for it. Refusing here made --ci-hook unreachable
            # after the first run. _scaffold_pre_commit_hook is
            # self-contained and never overwrites an existing hook, so
            # honouring just that half of init is safe: nothing else in
            # this function runs, and project_layout is left exactly as
            # the first init wrote it.
            return 0, [
                "Already initialized - left project_layout untouched.",
                (
                    _preview_pre_commit_hook(repo_root)
                    if dry_run
                    else _scaffold_pre_commit_hook(repo_root)
                ),
            ]
        return 1, [
            "Already initialized. Run /ult-repo-layout reconcile to update "
            "the index, or discover to re-confirm slot locations. To add "
            "the opt-in pre-commit hook to an already-initialized repo "
            "without re-initializing, re-run this with --ci-hook - that "
            "scaffolds the hook alone and touches nothing else.",
        ]

    existing_wr = _normalize_workspace_root(config)
    if workspace_root is not None:
        if existing_wr:
            return 1, [
                f"layout.workspace_root is already set to '{existing_wr}' - "
                f"init never overwrites an existing value (the same "
                f"never-silently-reset rule reconcile follows). Omit "
                f"--workspace-root to keep it, or edit context-config.yaml "
                f"by hand to change it.",
            ]
        wr_clean = workspace_root.rstrip("/")
        if wr_clean in ("", "."):
            return 1, [
                f"--workspace-root = '{workspace_root}' is invalid - the "
                f"repo root cannot be the workspace root (S22). Use a "
                f"repo-relative subdirectory (e.g. 'docs/')."
            ]
        path_problems = check_path_wellformedness(Path(wr_clean))
        if path_problems:
            return 1, [f"--workspace-root '{workspace_root}' - {p}" for p in path_problems]

    effective_wr = workspace_root.rstrip("/") if workspace_root else existing_wr

    # Snapshot the What-L2/How-L2 "does the shipped default already have
    # content" checks *before* the scaffold loop below runs. Real-run
    # scaffolding (e.g. context_packages landing at
    # '{workspace_root}/contexts/') can mkdir(parents=True) the workspace
    # root itself as a side effect; checking existence after that loop would
    # then see that incidental directory and wrongly conclude there's
    # already content, silently skipping the disable. This also keeps
    # dry_run and real-run messages identical, since dry_run never runs the
    # loop's mkdir at all (ISSUES.md Round 2 finding 9, 2026-08-31).
    what_l2_default = None
    what_l2_existed_before_init = None
    if not resolve_what_l2_path_explicit(config):
        what_l2_default = resolve_what_l2_path_for_init(config, effective_wr)
        what_l2_existed_before_init = (repo_root / what_l2_default.rstrip("/")).exists()

    how_l2_default = None
    how_l2_existed_before_init = None
    if not resolve_how_l2_path_explicit(config):
        how_l2_default = resolve_how_l2_path(config)
        how_l2_existed_before_init = (repo_root / how_l2_default.rstrip("/")).exists()

    entries = {}
    messages = []
    for slot, spec in SLOT_REGISTRY.items():
        if not _owning_skill_installed(repo_root, spec["owning_skill"]):
            continue

        if effective_wr and spec.get("workspace_root_leaf"):
            default = f"{effective_wr}/{spec['workspace_root_leaf']}"
        else:
            default = resolve_pre_d21_default(slot, config)

        rel = Path(default.rstrip("/"))
        # Defensive, not the primary guard: `effective_wr` should already have
        # passed check_path_wellformedness above (or come from an
        # already-validated config value) by the time it reaches here, but
        # `repo_root / rel` silently discards `repo_root` and becomes `rel`
        # itself if `rel` is ever absolute - assert instead of writing outside
        # the affirmed root should that invariant ever be violated upstream.
        assert not rel.is_absolute(), f"slot '{slot}' resolved to an absolute path {rel!r}"
        kind = spec["kind"]
        target = repo_root / rel

        if kind == "directory":
            if not dry_run:
                target.mkdir(parents=True, exist_ok=True)
                _write_marker(target, slot, kind, None)
            resolved_display = rel.as_posix() + "/"
            verb = "Would scaffold" if dry_run else "Scaffolded"
            messages.append(f"{verb} '{slot}' at '{resolved_display}'.")
        else:
            # kind == "file": init only registers the marker + slot
            # location - it never creates the file itself. That's the
            # owning skill's job on its own first run. Say so explicitly;
            # claiming "Scaffolded" here would be a false positive (the
            # file doesn't exist yet) that --validate immediately
            # contradicts the next time it runs.
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                _write_marker(target.parent, slot, kind, target.name)
            resolved_display = rel.as_posix()
            verb = "Would register" if dry_run else "Registered"
            tense = "would be written" if dry_run else "is written"
            messages.append(
                f"{verb} '{slot}' at '{resolved_display}' - the file "
                f"itself {tense} by {spec['owning_skill']} on first run."
            )

        entries[slot] = (resolved_display, kind, spec["owning_skill"])

    if not entries:
        return 1, [
            "No registered slot's owning skill is installed under "
            ".github/skills/ - nothing to initialize.",
        ]

    config_lines = config_path.read_text(encoding="utf-8-sig").splitlines()

    if workspace_root is not None:
        # In dry_run, these two calls still mutate `config_lines`, but that
        # list is never written back to disk below - harmless scratch state,
        # kept unconditional so the resolution above (which already used
        # `effective_wr`, not `config_lines`) doesn't need a second,
        # dry_run-only branch just to compute the same values again.
        set_scalar(config_lines, ["layout", "workspace_root"], workspace_root.rstrip("/"))
        current_exclude = resolve_what_l2_exclude(config)
        for leaf in ("contexts/", "inputs/", "cache/"):
            if leaf not in current_exclude:
                append_list_item(config_lines, ["layers", "what_l2", "exclude"], leaf)
        verb = "Would set" if dry_run else "Set"
        tense = "would be pre-populated" if dry_run else "pre-populated"
        messages.append(
            f"{verb} layout.workspace_root = '{workspace_root.rstrip('/')}' and "
            f"layers.what_l2.exclude {tense} (§16.5 recommended triad)."
        )

    # S28 day-one silent-clean: What-L2/How-L2 ship enabled: true with no
    # documented opt-out, but a fresh repo almost never already has content
    # at either layer's shipped default path - check_layer_paths_populated
    # would immediately WARN about the very defaults this installer just
    # shipped. Only touch it when the path is still the shipped default
    # (never override a path the user explicitly configured, even if that
    # path doesn't exist yet) and it genuinely doesn't exist on disk.
    if what_l2_default is not None and not what_l2_existed_before_init:
        set_scalar(config_lines, ["layers", "what_l2", "enabled"], "false")
        verb = "Would set" if dry_run else "Set"
        messages.append(
            f"{verb} layers.what_l2.enabled = false - the shipped default "
            f"'{what_l2_default}' doesn't exist in this repo yet. Set it "
            f"back to true (and layers.what_l2.path, if different) once "
            f"there's content to index."
        )

    if how_l2_default is not None and not how_l2_existed_before_init:
        set_scalar(config_lines, ["how_dimension", "how_l2", "enabled"], "false")
        verb = "Would set" if dry_run else "Set"
        messages.append(
            f"{verb} how_dimension.how_l2.enabled = false - the shipped "
            f"default '{how_l2_default}' doesn't exist in this repo yet. "
            f"Set it back to true (and how_dimension.how_l2.path, if "
            f"different) once there's content to index."
        )

    if dry_run:
        messages.append(
            f"Would write project_layout with {len(entries)} slot(s) to "
            f"context-config.yaml."
        )
        if ci_hook:
            messages.append(_preview_pre_commit_hook(repo_root))
        return 0, messages

    _write_project_layout_section(config_lines, entries)
    config_path.write_text("\n".join(config_lines) + "\n", encoding="utf-8")
    messages.append(f"Wrote project_layout with {len(entries)} slot(s) to context-config.yaml.")

    if ci_hook:
        messages.append(_scaffold_pre_commit_hook(repo_root))

    return 0, messages


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
        elif kind != "file":
            # kind == "directory" slots are scaffolded eagerly by `init` (the
            # directory itself is created on the spot), so a missing one is
            # worth flagging. kind == "file" slots only ever get a marker at
            # init time - the file itself is written by the owning skill on
            # its own first run (see run_init) - so its absence here is the
            # normal, expected pre-first-run state, not something to report.
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

    # Layer path population check (D23 §17.8, S28) - non-blocking.
    for problem in check_layer_paths_populated(repo_root, config):
        report.append(f"WARN: {problem}")

    # Layer candidate path population check (D23 §17.8 per-candidate
    # extension, S40) - non-blocking.
    for problem in check_layer_candidate_paths_populated(repo_root, config):
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
    parser.add_argument(
        "--init", action="store_true",
        help="scaffold installed slots' directories/markers and write project_layout "
             "(mechanical half of SKILL.md's init mode - see module docstring)",
    )
    parser.add_argument(
        "--workspace-root", default=None, metavar="<path>",
        help="only with --init: set layout.workspace_root and pre-populate the "
             "what_l2.exclude triad (§16.5); errors if one is already set",
    )
    parser.add_argument(
        "--ci-hook", action="store_true",
        help="only with --init: scaffold the .git/hooks/pre-commit wrapper "
             "(opt-in - omitted unless explicitly requested)",
    )
    parser.add_argument(
        "--no-ci-hook", action="store_true",
        help=argparse.SUPPRESS,  # deprecated no-op - the hook is opt-in by default now
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="only with --init: preview what init would do (scaffolded paths, "
             "workspace_root/exclude/enabled changes) without writing anything "
             "(ISSUES.md Round 2 finding 9, 2026-08-31)",
    )
    args = parser.parse_args(argv)

    if args.init:
        if args.no_ci_hook:
            print(
                "--no-ci-hook is deprecated and is now a no-op - the "
                "pre-commit hook is opt-in by default; pass --ci-hook to "
                "scaffold it."
            )
        code, messages = run_init(
            args.repo_root, workspace_root=args.workspace_root, ci_hook=args.ci_hook,
            dry_run=args.dry_run,
        )
        for message in messages:
            print(message)
        return code

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
