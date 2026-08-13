#!/usr/bin/env python3
"""scaffold_state.py -- only code that reads/writes TRIAGE-STATE.json.

D24 Phase B (`ult-autoscaffold-content`): large-repo triage/tiering and
resume/checkpoint. See D24-WIZARD-REMAINING-WORK.md (design repo) for the
full phase sequence this belongs to -- this docstring covers CLI surface
only.

Python 3 stdlib only (argparse, json, os, re, sys, datetime, pathlib) --
vendorable, no pip install step, same posture as decision_ledger.py
(ult-institutional-memory-distill/scripts/).

Graph access pattern (flagged deliberately -- see ult-codegraph's
CONSUMING-CODE-GRAPH.md): `scan --graph-mode graphify` loads
graphify-out/graph.json ONCE per run for structural aggregation (per-module
fan-in), not the repeated scoped-query pattern that doc's step 2 recommends
for normal per-question consumption during a task. That guidance targets
repeated per-question use; a one-time full-graph load for module tiering is
a different, one-shot access pattern -- not a violation of it. Every write
subcommand still states which mode was used (graph vs. heuristic), per that
same doc's step 3 requirement, in both this script's output and the
render-index artifact.

Subcommands:
  scaffold_state.py scan <state.json> --repo-root <path>
      --graph-mode graphify|heuristic [--graph-path <graphify-out/graph.json>]
      [--rescan]
    Enumerates top-level module directories under --repo-root (a small
    local port of ult-repo-layout/discover_layers.py's pruning helpers, not
    an import -- skills vendor small filesystem-scanning helpers rather
    than cross-import each other's scripts; decision_ledger.py's own
    docstring states the same posture for content_hash.py/md_index.py).

    --graph-mode graphify cross-checks the graph's own module names against
    --repo-root's real directories before tiering (defends against the
    graphify cwd/path-relativity footgun -- see CONSUMING-CODE-GRAPH.md and
    this file's _check_graph_repo_root_alignment() docstring). ZERO overlap
    is treated as a hard failure (ERROR, exit 1, no state written): silently
    proceeding would tier every module Tier 3/in-degree 0 with no signal
    anything went wrong, which is exactly the bug this guards against.
    Partial overlap (<50% of on-disk modules found in the graph) is a
    non-fatal WARNING, but never a silent one -- printed to stderr
    immediately, persisted to repo_scan.graph_module_overlap_warning in
    state, and echoed in render-index's output, so it surfaces wherever an
    operator looks, not just in a scrollback line.

    Assigns each module a tier:
      Tier 0 (skip)  -- generated/vendor directory name or file-suffix
                        majority match. Auto-marked "skipped" immediately --
                        these are never presented for per-module generation.
      Tier 1         -- in_degree >= 10 (graph-mode) or file_count >= 50
                        (heuristic-mode)
      Tier 2         -- 1 <= in_degree <= 9 (graph-mode) or
                        1 <= file_count <= 49 (heuristic-mode)
      Tier 3 (leaf)  -- in_degree == 0 (graph-mode) or file_count == 0
                        (heuristic-mode), not generated

    graphify-out/graph.json is loaded once (see docstring above). in_degree
    is the count of DISTINCT OTHER modules with at least one
    imports_from/imports/calls edge landing in this module -- not raw edge
    count, so one caller with many call sites doesn't inflate rank
    (coplit_handoff.md's own worked example: common/utils/ at 482 LOC but
    58 dependents correctly lands Tier 1, which a size heuristic alone
    would misfile Tier 3).

    A module already "generated" or "skipped" is never touched, rescan or
    not -- prior work is never silently discarded. Without --rescan, a
    still-"pending" module from a prior scan is also left as-is (cheap
    repeat scans, e.g. just to pick up newly-added modules). With
    --rescan, every still-pending module's tier is recomputed against
    fresh input (e.g. after regenerating the graph mid-run).

  scaffold_state.py mark-generated <state.json> <module-id> --output <path>
    Marks one module "generated", records its output path and timestamp.
    Refuses (ERROR, exit 1) if the module is not currently "pending".

  scaffold_state.py mark-skipped <state.json> <module-id> --reason <text>
    Marks one module "skipped" with a human-supplied reason. Same
    already-settled refusal as mark-generated.

  scaffold_state.py render-index <state.json> --repo-name <name> [--out <path>]
    Deterministic render of current state to Markdown (mechanical
    formatting only, no judgment -- same shape as discover_layers.py's
    render_discovery_artifact). Printed to stdout if --out is omitted;
    this is CEP-INDEX.md's generator, never hand-edited.

  scaffold_state.py show <state.json>
    Prints schema_version, graph mode/source, and per-tier
    pending/generated/skipped counts -- the resume-detection input for
    SKILL.md's resume-check step, and the intended read surface for
    Phase 3's future `status` CLI (no second schema needed later).

Every write subcommand rewrites the whole file, stable key order, 2-space
indent -- decision_ledger.py's exact convention, so diffs in a write-gate
PR stay small and readable.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

_STATUSES = ("pending", "generated", "skipped")

# Mirrors ult-repo-layout/discover_layers.py's SCAN_IGNORED_DIR_NAMES +
# CEP_BUCKET_DIR_NAMES -- a small local duplicate, not an import (house
# convention: see module docstring). Adds "graphify-out" on top of that
# base set: it's ult-codegraph's own fixed, always-gitignored tool output
# location (SKILL.md: "graphify-out/ should be gitignored in the consuming
# project"), never a real module candidate -- without this exclusion a
# repo that has already run ult-codegraph would see its own graph output
# enumerated and tiered as if it were application code.
SCAN_IGNORED_DIR_NAMES = {
    ".git", "node_modules", "vendor", "dist", "build", "target",
    ".venv", "__pycache__", "graphify-out",
}
CEP_BUCKET_DIR_NAMES = {"contexts", "inputs", "cache"}

# Tier 0: directory-name signal for generated/vendor code, beyond the
# scan-ignored set above (which is pruned from enumeration entirely -- a
# GENERATED_DIR_NAME_RE match is still *seen* as a module, just assigned
# Tier 0 and auto-skipped, so "why isn't X covered" has a visible answer
# rather than the module silently never appearing at all).
GENERATED_DIR_NAME_RE = re.compile(r"^(generated|gen|__generated__)$", re.I)

# Tier 0: file-suffix signal -- a module is Tier 0 if generated-looking
# files make up a majority of its own files, not just a single stray one.
GENERATED_FILE_SUFFIXES = ("_pb2.py", "_pb2_grpc.py", ".pb.go", ".g.dart")
GENERATED_FILE_INFIXES = (".generated.",)
GENERATED_FILE_MAJORITY_THRESHOLD = 0.5

# Cross-module dependency edge relations counted toward in-degree
# (graphify graph.json's links[].relation field, empirically verified
# against a real graphify 0.9.11 run -- see this file's sibling test
# fixture in scripts/tests/test_scaffold_state.py). Deliberately excludes
# purely-structural relations ("contains": file->function/class, "method":
# class->method) that never cross module boundaries meaningfully here.
DEPENDENCY_RELATIONS = frozenset({"imports_from", "imports", "calls"})

# Tier thresholds -- flagged implementation defaults, no design-doc-cited
# number exists for this specific ranking (same posture as
# discover_layers.py's HIGH_CONFIDENCE_FILE_FLOOR/MEDIUM_CONFIDENCE_FILE_FLOOR).
TIER1_MIN_IN_DEGREE = 10
TIER1_MIN_FILE_COUNT = 50

# Below this fraction of on-disk modules found among the graph's own module
# names, --graph-mode graphify emits a non-fatal WARNING (see
# _check_graph_repo_root_alignment()). Flagged implementation default, same
# posture as the tier thresholds above -- no cited design-doc number.
GRAPH_MODULE_OVERLAP_WARN_THRESHOLD = 0.5


class GraphRepoRootMismatchError(ValueError):
    """Raised when a graphify-mode graph shares ZERO top-level module names
    with --repo-root's own directories -- the graphify cwd/path-relativity
    footgun's exact signature. A ValueError subclass so it flows through
    the existing `except (ValueError, FileNotFoundError)` -> ERROR/exit-1
    handling in _cmd_scan() without any new CLI wiring."""


# --------------------------------------------------------------------------- #
# time                                                                        #
# --------------------------------------------------------------------------- #

def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Filesystem scanning helpers (local port of discover_layers.py's shape)     #
# --------------------------------------------------------------------------- #

def _prune_ignored(dirnames):
    keep = []
    for d in dirnames:
        if d in SCAN_IGNORED_DIR_NAMES or d in CEP_BUCKET_DIR_NAMES:
            continue
        if d.startswith("."):
            continue
        keep.append(d)
    return keep


def _iter_files(dirpath):
    """Yield every file under dirpath, pruning SCAN_IGNORED_DIR_NAMES,
    CEP_BUCKET_DIR_NAMES, and dot-directories at every level."""
    for root, dirnames, filenames in os.walk(dirpath):
        dirnames[:] = _prune_ignored(dirnames)
        for fn in filenames:
            yield Path(root) / fn


def _top_level_candidate_dirs(repo_root):
    """Immediate subdirectories of repo_root, pruned of
    SCAN_IGNORED_DIR_NAMES/CEP_BUCKET_DIR_NAMES/dot-dirs. Each becomes one
    candidate module. Returns sorted names (not full paths)."""
    repo_root = Path(repo_root)
    if not repo_root.is_dir():
        return []
    names = _prune_ignored([p.name for p in repo_root.iterdir() if p.is_dir()])
    return sorted(names)


# --------------------------------------------------------------------------- #
# Tier 0: generated/vendor detection                                         #
# --------------------------------------------------------------------------- #

def _looks_generated(path):
    name = path.name
    if any(name.endswith(suf) for suf in GENERATED_FILE_SUFFIXES):
        return True
    if any(infix in name for infix in GENERATED_FILE_INFIXES):
        return True
    return False


def _is_generated_module(module_path, files):
    if GENERATED_DIR_NAME_RE.match(module_path.name):
        return True
    if not files:
        return False
    generated = sum(1 for f in files if _looks_generated(f))
    return (generated / len(files)) >= GENERATED_FILE_MAJORITY_THRESHOLD


# --------------------------------------------------------------------------- #
# graph.json consumption (one-time full load -- see module docstring)       #
# --------------------------------------------------------------------------- #

def _load_graph(graph_path):
    if not graph_path:
        raise ValueError("--graph-path is required when --graph-mode graphify")
    path = Path(graph_path)
    if not path.exists():
        raise FileNotFoundError(
            "graph not found at {} -- run `ult-codegraph` (graphify update .) "
            "first, or re-run with --graph-mode heuristic".format(path)
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _module_of(source_file):
    """Top-level directory a graph.json node's source_file lives under, or
    None if the file is at repo root (not inside any candidate module)."""
    if not source_file:
        return None
    source_file = source_file.replace("\\", "/")
    parts = source_file.split("/", 1)
    if len(parts) < 2:
        return None
    return parts[0]


def _graph_in_degrees(graph):
    """{module_name: in_degree}, in_degree = count of DISTINCT OTHER
    modules with >=1 DEPENDENCY_RELATIONS edge landing in this module."""
    node_module = {}
    for node in graph.get("nodes", []):
        module = _module_of(node.get("source_file"))
        if module is not None:
            node_module[node.get("id")] = module

    senders = {}
    for link in graph.get("links", []):
        if link.get("relation") not in DEPENDENCY_RELATIONS:
            continue
        src_module = node_module.get(link.get("source"))
        dst_module = node_module.get(link.get("target"))
        if not src_module or not dst_module or src_module == dst_module:
            continue
        senders.setdefault(dst_module, set()).add(src_module)

    return {module: len(s) for module, s in senders.items()}


def _graph_module_names(graph):
    """Set of every module name _module_of() extracts from the graph's own
    nodes -- used only to cross-check against --repo-root's real
    directories (see _check_graph_repo_root_alignment())."""
    names = set()
    for node in graph.get("nodes", []):
        module = _module_of(node.get("source_file"))
        if module is not None:
            names.add(module)
    return names


def _check_graph_repo_root_alignment(graph_modules, module_names, graph_path):
    """Defend against the graphify cwd/path-relativity footgun: if
    `graphify update` was run from a different working directory than
    --repo-root expects, every source_file in graph.json carries a
    different (wrong) leading path segment, so _module_of()'s naive
    first-`/`-segment split extracts the wrong module name for every node.

    Left unchecked, _graph_in_degrees()'s output shares no keys with the
    real on-disk module names, scan()'s `in_degrees.get(name, 0)` lookup
    silently defaults every module to in_degree 0, and every module lands
    Tier 3 -- a complete, plausible-looking, WRONG tiering with no error or
    warning anywhere (found and self-corrected the hard way during the
    robotframework-wizard-ui case study; this function exists so the next
    occurrence is loud instead of silent).

    Returns None if aligned. Returns a warning string (non-fatal --
    partial degradation, not total failure) if overlap is present but
    thin. Raises GraphRepoRootMismatchError (fatal -- caller must not
    proceed to tier or write state) if overlap is exactly zero.
    """
    if not graph_modules or not module_names:
        # Nothing to cross-check (empty graph, or no candidate module
        # directories on disk yet) -- not this footgun's signature.
        return None

    disk_set = set(module_names)
    overlap = graph_modules & disk_set

    def _sample(names, limit=8):
        names = sorted(names)
        shown = ", ".join(names[:limit])
        return shown + (", ..." if len(names) > limit else "")

    if not overlap:
        raise GraphRepoRootMismatchError(
            "graph at {graph_path} shares ZERO top-level module names with "
            "--repo-root's own directories -- this is the graphify cwd/"
            "path-relativity footgun.\n"
            "  --repo-root modules on disk : {disk}\n"
            "  modules seen in graph.json  : {graph}\n"
            "`graphify update` was very likely run from a different working "
            "directory than --repo-root, so every source_file in the graph "
            "carries a different (wrong) leading path segment. Proceeding "
            "would silently default every module to in_degree 0 and tier "
            "everything Tier 3 -- a plausible-looking but wrong result.\n"
            "Fix: re-run `graphify update` with cwd matching --repo-root, "
            "then re-run this scan. (No state was written.)".format(
                graph_path=graph_path,
                disk=_sample(disk_set),
                graph=_sample(graph_modules),
            )
        )

    ratio = len(overlap) / len(disk_set)
    if ratio < GRAPH_MODULE_OVERLAP_WARN_THRESHOLD:
        return (
            "only {pct:.0f}% of --repo-root's on-disk modules ({overlap_n}/"
            "{total_n}) also appear as module names in the graph at "
            "{graph_path} -- possible partial graphify cwd/path-relativity "
            "mismatch, or the graph is simply stale/incomplete for some "
            "modules. Affected modules' in_degree may under-count (fall "
            "back toward Tier 3) rather than reflect real dependency "
            "weight. Missing from graph: {missing}. Re-run `graphify "
            "update` with cwd matching --repo-root if this is unexpected.".format(
                pct=ratio * 100,
                overlap_n=len(overlap),
                total_n=len(disk_set),
                graph_path=graph_path,
                missing=_sample(disk_set - overlap),
            )
        )
    return None


# --------------------------------------------------------------------------- #
# Tier assignment                                                            #
# --------------------------------------------------------------------------- #

def _tier_for_graph(in_degree, generated):
    if generated:
        return 0, "generated"
    if in_degree >= TIER1_MIN_IN_DEGREE:
        return 1, "graph:in-degree"
    if in_degree >= 1:
        return 2, "graph:in-degree"
    return 3, "graph:in-degree"


def _tier_for_heuristic(file_count, generated):
    if generated:
        return 0, "generated"
    if file_count >= TIER1_MIN_FILE_COUNT:
        return 1, "heuristic:file-count"
    if file_count >= 1:
        return 2, "heuristic:file-count"
    return 3, "heuristic:file-count"


# --------------------------------------------------------------------------- #
# State load/save                                                            #
# --------------------------------------------------------------------------- #

def empty_state():
    return {
        "schema_version": SCHEMA_VERSION,
        "repo_scan": {"graph_source": None, "graph_path": None, "scanned_at": None},
        "modules": [],
    }


def load_state(path):
    """Load state from `path`, an empty skeleton if it doesn't exist yet.

    A missing file is not an error -- the project hasn't been scanned yet,
    which is a legitimate, fully-valid empty state."""
    path = Path(path)
    if not path.exists():
        return empty_state()
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return empty_state()
    state = json.loads(text)
    state.setdefault("schema_version", SCHEMA_VERSION)
    state.setdefault("repo_scan", {"graph_source": None, "graph_path": None, "scanned_at": None})
    state.setdefault("modules", [])
    return state


def save_state(path, state):
    """Write `state` to `path`, 2-space indent, stable field order.

    Creates parent directories as needed -- the state file is a derived,
    tool-owned artifact, not a project-authored drop-zone."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = {
        "schema_version": state.get("schema_version", SCHEMA_VERSION),
        "repo_scan": state.get("repo_scan", {}),
        "modules": state.get("modules", []),
    }
    path.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")


def _find_module(state, module_id):
    for m in state.get("modules", []):
        if m["id"] == module_id:
            return m
    raise ValueError("no module with id '{}' in state -- run `scan` first".format(module_id))


# --------------------------------------------------------------------------- #
# scan                                                                        #
# --------------------------------------------------------------------------- #

def scan(state, repo_root, graph_mode, graph_path=None, rescan=False):
    if graph_mode not in ("graphify", "heuristic"):
        raise ValueError("graph_mode must be 'graphify' or 'heuristic'")

    repo_root = Path(repo_root)
    existing = {m["id"]: m for m in state.get("modules", [])}
    module_names = _top_level_candidate_dirs(repo_root)

    in_degrees = {}
    alignment_warning = None
    if graph_mode == "graphify":
        graph = _load_graph(graph_path)
        # Cross-check BEFORE tiering, and before any state mutation below --
        # a zero-overlap mismatch must abort with no partial/corrupt state
        # written, same posture as _load_graph()'s own missing-file check.
        alignment_warning = _check_graph_repo_root_alignment(
            _graph_module_names(graph), module_names, graph_path
        )
        in_degrees = _graph_in_degrees(graph)

    new_modules = []
    seen_ids = set()
    for name in module_names:
        module_id = name + "/"
        seen_ids.add(module_id)
        prior = existing.get(module_id)

        if prior is not None and prior["status"] != "pending":
            # Settled -- never touched, rescan or not.
            new_modules.append(prior)
            continue
        if prior is not None and prior["status"] == "pending" and not rescan:
            # Still pending, no --rescan -- leave prior tier data as-is.
            new_modules.append(prior)
            continue

        module_path = repo_root / name
        files = list(_iter_files(module_path))
        generated = _is_generated_module(module_path, files)

        if graph_mode == "graphify":
            in_degree = in_degrees.get(name, 0)
            tier, basis = _tier_for_graph(in_degree, generated)
        else:
            in_degree = None
            tier, basis = _tier_for_heuristic(len(files), generated)

        entry = {
            "id": module_id,
            "tier": tier,
            "in_degree": in_degree,
            "file_count": len(files),
            "basis": basis,
            "status": "skipped" if tier == 0 else "pending",
            "generated_at": None,
            "output_path": None,
            "skip_reason": "generated/vendor code (auto-detected)" if tier == 0 else None,
        }
        new_modules.append(entry)

    # A module no longer present on disk keeps its history -- state is a
    # record of decisions made, not a live filesystem mirror.
    for module_id, entry in existing.items():
        if module_id not in seen_ids:
            new_modules.append(entry)

    state["modules"] = new_modules
    state["repo_scan"] = {
        "graph_source": graph_mode,
        "graph_path": str(graph_path) if graph_path else None,
        "scanned_at": _now_iso(),
        # Non-fatal graph/repo-root module-overlap degradation, if any --
        # None when aligned or when graph_mode == "heuristic". Persisted
        # (not just printed) so `show` and `render-index` still surface it
        # after the run that produced it has scrolled out of the terminal.
        "graph_module_overlap_warning": alignment_warning,
    }
    return state


def mark_generated(state, module_id, output_path):
    module = _find_module(state, module_id)
    if module["status"] != "pending":
        raise ValueError(
            "module '{}' is already '{}' -- not pending".format(module_id, module["status"])
        )
    module["status"] = "generated"
    module["output_path"] = output_path
    module["generated_at"] = _now_iso()
    return module


def mark_skipped(state, module_id, reason):
    module = _find_module(state, module_id)
    if module["status"] != "pending":
        raise ValueError(
            "module '{}' is already '{}' -- not pending".format(module_id, module["status"])
        )
    module["status"] = "skipped"
    module["skip_reason"] = reason
    return module


# --------------------------------------------------------------------------- #
# render-index                                                                #
# --------------------------------------------------------------------------- #

_TIER_TITLES = {
    1: "## Tier 1 -- high-importance modules",
    2: "## Tier 2 -- ordinary modules",
    3: "## Tier 3 -- leaf modules (no other module depends on these)",
    0: "## Tier 0 -- generated/vendor (auto-skipped)",
}


def render_index(state, repo_name):
    modules = state.get("modules", [])
    by_tier = {0: [], 1: [], 2: [], 3: []}
    for m in modules:
        by_tier.setdefault(m["tier"], []).append(m)

    graph_source = (state.get("repo_scan") or {}).get("graph_source") or "not yet scanned"

    lines = [
        "# CEP Index - {}".format(repo_name),
        "",
        "Generated by `ult-autoscaffold-content` (D24 Phase B). Regenerated on "
        "every `scaffold_state.py render-index` call -- never hand-edited.",
        "",
        "Graph mode used for tiering: **{}**.".format(graph_source),
    ]
    if graph_source == "heuristic":
        lines.append(
            "Heuristic (file-count) tiering is lower-confidence than "
            "graph-informed tiering -- treat tier assignments below as a "
            "starting point, not a verified dependency ranking."
        )
    overlap_warning = (state.get("repo_scan") or {}).get("graph_module_overlap_warning")
    if overlap_warning:
        lines.append("")
        lines.append("**WARNING:** {}".format(overlap_warning))
    lines.append("")

    for tier in (1, 2, 3, 0):
        entries = by_tier.get(tier, [])
        lines.append(_TIER_TITLES[tier])
        lines.append("")
        if not entries:
            lines.append("_none_")
            lines.append("")
            continue
        for m in sorted(entries, key=lambda e: e["id"]):
            if m.get("in_degree") is not None:
                detail = "in-degree {}".format(m["in_degree"])
            else:
                detail = "{} files".format(m.get("file_count"))
            path_note = " -> `{}`".format(m["output_path"]) if m.get("output_path") else ""
            lines.append(
                "- `{}` ({}, {}) -- **{}**{}".format(
                    m["id"], detail, m["basis"], m["status"], path_note
                )
            )
        lines.append("")

    generated_count = sum(1 for m in modules if m["status"] == "generated")
    pending_count = sum(1 for m in modules if m["status"] == "pending")
    skipped_count = sum(1 for m in modules if m["status"] == "skipped")
    lines.append(
        "**Progress:** {} generated, {} pending, {} skipped ({} modules total).".format(
            generated_count, pending_count, skipped_count, len(modules)
        )
    )
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# show                                                                        #
# --------------------------------------------------------------------------- #

def summarize(state):
    modules = state.get("modules", [])
    by_tier = {}
    for m in modules:
        counts = by_tier.setdefault(str(m["tier"]), {"pending": 0, "generated": 0, "skipped": 0})
        counts[m["status"]] = counts.get(m["status"], 0) + 1
    return {
        "schema_version": state.get("schema_version"),
        "repo_scan": state.get("repo_scan", {}),
        "total_modules": len(modules),
        "by_tier": by_tier,
        "generated": sum(1 for m in modules if m["status"] == "generated"),
        "pending": sum(1 for m in modules if m["status"] == "pending"),
        "skipped": sum(1 for m in modules if m["status"] == "skipped"),
    }


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #

def _cmd_scan(args):
    state = load_state(args.state)
    if args.graph_mode == "graphify" and not args.graph_path:
        print("ERROR: --graph-path is required when --graph-mode graphify", file=sys.stderr)
        return 1
    try:
        scan(state, args.repo_root, args.graph_mode, graph_path=args.graph_path, rescan=args.rescan)
    except (ValueError, FileNotFoundError) as e:
        # Covers GraphRepoRootMismatchError too (a ValueError subclass) --
        # the zero-overlap graphify cwd/path-relativity case. No state is
        # written: `state` here is whatever was loaded before scan() raised.
        print("ERROR: {}".format(e), file=sys.stderr)
        return 1
    overlap_warning = (state.get("repo_scan") or {}).get("graph_module_overlap_warning")
    if overlap_warning:
        # Non-fatal partial-overlap degradation -- printed immediately so
        # it's seen at scan time, not only later via `show`/render-index.
        print("WARNING: {}".format(overlap_warning), file=sys.stderr)
    save_state(args.state, state)
    print(json.dumps(summarize(state), indent=2))
    return 0


def _cmd_mark_generated(args):
    state = load_state(args.state)
    try:
        module = mark_generated(state, args.module_id, args.output)
    except ValueError as e:
        print("ERROR: {}".format(e), file=sys.stderr)
        return 1
    save_state(args.state, state)
    print(json.dumps(module, indent=2))
    return 0


def _cmd_mark_skipped(args):
    state = load_state(args.state)
    try:
        module = mark_skipped(state, args.module_id, args.reason)
    except ValueError as e:
        print("ERROR: {}".format(e), file=sys.stderr)
        return 1
    save_state(args.state, state)
    print(json.dumps(module, indent=2))
    return 0


def _cmd_render_index(args):
    state = load_state(args.state)
    text = render_index(state, args.repo_name)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print("wrote {}".format(out_path))
    else:
        print(text)
    return 0


def _cmd_show(args):
    state = load_state(args.state)
    print(json.dumps(summarize(state), indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="scaffold_state.py",
        description="Read/write the D24 Phase B triage/checkpoint state (TRIAGE-STATE.json).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Enumerate modules and assign tiers.")
    p_scan.add_argument("state")
    p_scan.add_argument("--repo-root", required=True)
    p_scan.add_argument("--graph-mode", required=True, choices=("graphify", "heuristic"))
    p_scan.add_argument(
        "--graph-path", default=None,
        help="Path to graphify-out/graph.json. Required for --graph-mode graphify.",
    )
    p_scan.add_argument(
        "--rescan", action="store_true",
        help="Recompute tier for still-pending modules. Never touches an "
             "already-generated/skipped entry, with or without this flag.",
    )
    p_scan.set_defaults(func=_cmd_scan)

    p_gen = sub.add_parser("mark-generated", help="Mark one module generated.")
    p_gen.add_argument("state")
    p_gen.add_argument("module_id")
    p_gen.add_argument("--output", required=True)
    p_gen.set_defaults(func=_cmd_mark_generated)

    p_skip = sub.add_parser("mark-skipped", help="Mark one module skipped.")
    p_skip.add_argument("state")
    p_skip.add_argument("module_id")
    p_skip.add_argument("--reason", required=True)
    p_skip.set_defaults(func=_cmd_mark_skipped)

    p_render = sub.add_parser("render-index", help="Render CEP-INDEX.md from current state.")
    p_render.add_argument("state")
    p_render.add_argument("--repo-name", required=True)
    p_render.add_argument("--out", default=None, help="Write to this path instead of stdout.")
    p_render.set_defaults(func=_cmd_render_index)

    p_show = sub.add_parser("show", help="Print schema_version, graph mode, and per-tier counts.")
    p_show.add_argument("state")
    p_show.set_defaults(func=_cmd_show)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
