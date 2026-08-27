#!/usr/bin/env python3
"""scaffold_state.py -- only code that reads/writes TRIAGE-STATE.json.

Large-repo triage/tiering and resume/checkpoint for
`ult-autoscaffold-content`. This docstring covers CLI surface only -- see
the skill's SKILL.md for the full workflow this belongs to.

Python 3 stdlib only (argparse, json, os, re, sys, datetime, pathlib) --
vendorable, no pip install step, same posture as decision_ledger.py
(ult-institutional-memory-distill/scripts/).

Graph access pattern: `scan --graph-mode graphify` loads
graphify-out/graph.json ONCE per run for structural aggregation (per-module
fan-in) -- a deliberate one-time full-graph load, not the repeated
scoped-query pattern ult-codegraph's CONSUMING-CODE-GRAPH.md recommends for
normal per-question consumption; see the skill's SKILL.md Step 3.5 for why
that's not a violation of that guidance. Every write subcommand still
states which mode was used (graph vs. heuristic), per that same doc's step
3 requirement, in both this script's output and the render-index artifact.

Subcommands:
  scaffold_state.py probe-size --repo-root <path>
    Read-only count of top-level candidate directories that clear
    MIN_FILES_FOR_SIZE_GATE files each (same pruning _top_level_candidate_
    dirs()/_iter_files() already apply, no state file, no writes) --
    SKILL.md Step 4's small/large repo-size gate reads this before
    choosing a Phase A/Phase B path. See SMALL_REPO_MAX_MODULES/
    LARGE_REPO_MIN_MODULES below for the default thresholds; the band
    between the two is deliberately left with no default at all.

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

    A separate, thinner check runs alongside this one: even when the graph
    points at the right repo, it may never have had CEP's own installed
    footprint excluded from the scan (see
    _check_graph_cep_contamination()). Same non-fatal, never-silent
    posture -- stderr, repo_scan.graph_cep_contamination_warning, and
    render-index -- just a different footgun and a much lower trigger
    threshold, since CEP's own footprint should be a thin sliver of any
    real target repo's graph.

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
    count, so one caller with many call sites doesn't inflate rank (e.g. a
    482-LOC utils/ module with 58 distinct dependents correctly lands
    Tier 1, which a size heuristic alone would misfile Tier 3).

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
    this is CEP-INDEX.md's generator, never hand-edited. Includes the
    per-tier module sections above, plus a "Repo-wide docs" section
    (coding-standards/testing-guidelines status) and an "Interface
    boundaries" section (see below).

  scaffold_state.py show <state.json>
    Prints schema_version, graph mode/source, and per-tier
    pending/generated/skipped counts -- the resume-detection input for
    SKILL.md's resume-check step, and the intended read surface for
    Phase 3's future `status` CLI (no second schema needed later).

  scaffold_state.py mark-repo-doc-generated <state.json> <coding_standards|testing_guidelines> --output <path>
    Marks one repo-wide doc kind "generated", records its output path and
    timestamp. Refuses (ERROR, exit 1) if not currently "pending" -- same
    refusal discipline as mark-generated.

  scaffold_state.py mark-repo-doc-skipped <state.json> <coding_standards|testing_guidelines> --reason <text>
    Marks one repo-wide doc kind "skipped" with a human-supplied reason.

  scaffold_state.py mark-interface-generated <state.json> <interface-id> --output <path>
    Marks one interface-boundary pair "generated", records its output path
    and timestamp. Refuses (ERROR, exit 1) if not currently "pending".

  scaffold_state.py mark-interface-deferred <state.json> <interface-id> --reason <text>
    Marks one interface-boundary pair "deferred" with a human-supplied
    reason (SKILL.md Step 5d: typically "endpoint <x> not yet generated
    this run").

  scaffold_state.py list-interfaces <state.json> [--eligible-only]
    Prints the interfaces list. --eligible-only filters to "pending" pairs
    whose both endpoint modules are already "generated" in this same
    state -- the exact tier-gating rule SKILL.md Step 5d applies, exposed
    here so the agent doesn't hand-read/hand-cross-reference the JSON.

Interfaces (populated only when --graph-mode graphify; scan()'s one-time
graph.json load, same access pattern as in-degree above): one entry per
distinct crossing-module-boundary pair, deduplicated and stored in a
stable sorted (module_a, module_b) order regardless of which direction the
underlying graph edges point -- see _graph_crossing_edges()'s docstring.
Like modules, a settled ("generated"/"deferred") interface entry is never
silently touched by a later scan -- same "state is a record of decisions
made" posture. In heuristic mode the interfaces list is left exactly as it
was (empty if never scanned in graphify mode) -- there's no crossing-edge
data to compute it from.

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

# Content-identical to ult-repo-layout/discover_layers.py's own
# SCAN_IGNORED_DIR_NAMES (plus that module's separate CEP_BUCKET_DIR_NAMES,
# also mirrored below) -- a small local duplicate, not a shared import
# (house convention: see module docstring). Keep the two sets equal; both
# skills' test suites assert this so a future edit to one that forgets the
# other fails loudly instead of silently diverging again.
#
# "graphify-out" is ult-codegraph's own fixed, always-gitignored tool
# output location (SKILL.md: "graphify-out/ should be gitignored in the
# consuming project"), never a real module candidate -- without this
# exclusion a repo that has already run ult-codegraph would see its own
# graph output enumerated and tiered as if it were application code.
#
# The second line below is a name-based stopgap, deliberately kept even
# though _top_level_candidate_dirs also drops manifest `owned_paths` (see
# _manifest_owned_top_level_names): the manifest only knows about paths
# CEP itself installed, and "starter_kit"/"output_docs" are exactly that,
# so a manifest-unaware repo (manually installed, or predating the
# manifest) still needs a name-based fallback for them. "third_party",
# "extern", "external", "deps", and "submodules" are a different, wider
# problem the manifest can never solve either way -- a project's own
# vendored/third-party code, conventionally named one of these, is not
# CEP's to know about at all. None of these seven is a name a real
# first-party application module is likely to use.
SCAN_IGNORED_DIR_NAMES = {
    ".git", "node_modules", "vendor", "dist", "build", "target",
    ".venv", "__pycache__", "graphify-out",
    "third_party", "starter_kit", "output_docs", "extern", "external",
    "deps", "submodules",
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

# Above this fraction of graph.json's own nodes living under a path this
# repo's .cep-install.json manifest marks as CEP-owned, --graph-mode
# graphify emits a non-fatal WARNING (see _check_graph_cep_contamination()).
# Deliberately much lower than GRAPH_MODULE_OVERLAP_WARN_THRESHOLD above --
# CEP's own installed footprint should be a thin sliver of any real target
# repo's graph, so even a small fraction is a meaningful signal that
# graphify walked CEP's own installed skills/docs rather than being scoped
# away from them. Flagged implementation default, same posture as the tier
# thresholds above -- no cited design-doc number.
GRAPH_CEP_CONTAMINATION_WARN_THRESHOLD = 0.05

# SKILL.md Step 4's small/large repo-size gate -- flagged implementation
# defaults, same posture as the tier thresholds above (no design-doc-cited
# number). A top-level candidate directory only counts toward this gate
# once it clears MIN_FILES_FOR_SIZE_GATE files (recursively, same pruning
# _iter_files() already applies) -- this filters out conventionally
# near-empty structural directories (a docs/ folder holding one README, a
# scripts/ folder holding one file) from inflating the count; it does not
# try to distinguish "real subsystem" from "conventional project
# scaffolding" by name, since scan()'s own module enumeration doesn't
# either -- whatever this probe counts, a real Phase B scan would enumerate
# the same way.
#
# <= SMALL_REPO_MAX_MODULES substantive directories classifies as small by
# default; >= LARGE_REPO_MIN_MODULES classifies as large by default. The
# band between the two has no safe default on purpose -- SKILL.md Step 4
# asks the user directly rather than guessing.
MIN_FILES_FOR_SIZE_GATE = 5
SMALL_REPO_MAX_MODULES = 2
LARGE_REPO_MIN_MODULES = 8

# Repo-wide convention docs SKILL.md Step 5c can generate -- exactly these
# two kinds, both existence-gated (never overwrite a file that's already
# there). Fixed tuple, not user-extensible: a third kind needs its own
# references/*.md + templates/*.md pair and SKILL.md step, not a config
# flag here.
REPO_DOC_KINDS = ("coding_standards", "testing_guidelines")


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


def _read_cep_manifest(repo_root):
    """Reads `.cep-install.json` at `repo_root` (written by install.ps1/
    install.sh) and returns its `owned_paths` as a set of resolved absolute
    Paths, or None if no manifest exists or it can't be parsed. Deliberately
    duplicated per-consumer rather than factored into a shared module (house
    convention: see this module's own docstring). Callers must treat None as
    "no signal available" and fall back to pre-manifest behavior -- never an
    error for an unmanifested repo."""
    manifest_path = Path(repo_root) / ".cep-install.json"
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
            result.add((Path(repo_root) / item).resolve())
    return result


def _manifest_owned_top_level_names(repo_root, manifest_owned):
    """Top-level (direct child of repo_root) names that are themselves a
    manifest `owned_paths` entry, or contain one as a descendant -- e.g.
    "starter_kit" when `starter_kit/project_guidelines` is CEP-owned. Most
    of CEP's own trees (.github/, .cursor/) are already dropped by the
    dot-prefix rule in _prune_ignored, but starter_kit/ has no dot prefix,
    so without this it would otherwise be walked and tiered like a real
    application module -- the exact false-positive this closes."""
    if not manifest_owned:
        return set()
    repo_root = Path(repo_root).resolve()
    names = set()
    for owned in manifest_owned:
        try:
            rel = owned.relative_to(repo_root)
        except ValueError:
            continue
        if rel.parts:
            names.add(rel.parts[0])
    return names


def _top_level_candidate_dirs(repo_root):
    """Immediate subdirectories of repo_root, pruned of
    SCAN_IGNORED_DIR_NAMES/CEP_BUCKET_DIR_NAMES/dot-dirs, plus any manifest
    `owned_paths` top-level name (see _manifest_owned_top_level_names).
    Each surviving name becomes one candidate module. Returns sorted names
    (not full paths)."""
    repo_root = Path(repo_root)
    if not repo_root.is_dir():
        return []
    manifest_owned = _read_cep_manifest(repo_root)
    manifest_names = _manifest_owned_top_level_names(repo_root, manifest_owned)
    names = _prune_ignored([p.name for p in repo_root.iterdir() if p.is_dir()])
    names = [n for n in names if n not in manifest_names]
    return sorted(names)


# --------------------------------------------------------------------------- #
# SKILL.md Step 4's small/large repo-size gate                               #
# --------------------------------------------------------------------------- #

def probe_size(repo_root):
    """Cheap, read-only repo-size signal for SKILL.md Step 4's small/large
    gate. Counts top-level candidate directories under repo_root
    (_top_level_candidate_dirs()'s pruning) that clear
    MIN_FILES_FOR_SIZE_GATE files each (_iter_files()'s own recursive
    pruning) -- a conventionally near-empty structural directory (docs/
    with one README) doesn't inflate the count. No state file, no writes.

    Returns {"substantive_modules": [...names...], "count": N,
    "classification": "small"|"ambiguous"|"large"}. See
    SMALL_REPO_MAX_MODULES/LARGE_REPO_MIN_MODULES above for the default
    thresholds; the ambiguous band has no safe default on purpose."""
    repo_root = Path(repo_root)
    substantive = [
        name for name in _top_level_candidate_dirs(repo_root)
        if sum(1 for _ in _iter_files(repo_root / name)) >= MIN_FILES_FOR_SIZE_GATE
    ]
    count = len(substantive)
    if count <= SMALL_REPO_MAX_MODULES:
        classification = "small"
    elif count >= LARGE_REPO_MIN_MODULES:
        classification = "large"
    else:
        classification = "ambiguous"
    return {
        "substantive_modules": substantive,
        "count": count,
        "classification": classification,
    }


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


def _node_module_map(graph):
    """{node_id: module_name} for every graph node whose source_file maps to
    a module (see _module_of()). Shared by every graph-aggregation function
    below so each one loads the graph's nodes exactly once per call site."""
    node_module = {}
    for node in graph.get("nodes", []):
        module = _module_of(node.get("source_file"))
        if module is not None:
            node_module[node.get("id")] = module
    return node_module


def _graph_in_degrees(graph):
    """{module_name: in_degree}, in_degree = count of DISTINCT OTHER
    modules with >=1 DEPENDENCY_RELATIONS edge landing in this module."""
    node_module = _node_module_map(graph)

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


def _graph_module_node_counts(graph):
    """{module_name: node_count} for every graph node whose source_file maps
    to a module (see _module_of()). Distinct from _graph_in_degrees(): a
    module can legitimately have in_degree 0 (a real leaf, tier 3 -- other
    code just never imports it) while still containing plenty of its own
    nodes. This counts total nodes per module instead, so a module with
    ZERO nodes -- graphify found nothing to index there at all -- can be
    told apart from a real leaf. Used by _tier_for_graph()'s empty-module
    check."""
    node_module = _node_module_map(graph)
    counts = {}
    for module in node_module.values():
        counts[module] = counts.get(module, 0) + 1
    return counts


def _interface_id(module_a, module_b):
    """Stable id for an unordered module pair -- callers must already have
    sorted (module_a, module_b), this just joins them."""
    return "{}--{}".format(module_a, module_b)


def _graph_crossing_edges(graph):
    """One entry per distinct pair of modules connected by >=1
    DEPENDENCY_RELATIONS edge crossing the module boundary, deduplicated and
    stored in a stable sorted (module_a, module_b) order regardless of which
    direction the underlying graph edge points -- an interface boundary is
    the pair, not the direction. `weight` is the number of qualifying edges
    observed for that pair (both directions combined); `relations` is the
    sorted set of distinct relation values seen.

    Returns a list of {"module_a", "module_b", "relations": [...],
    "weight": N} dicts, sorted by (module_a, module_b) for a stable diff."""
    node_module = _node_module_map(graph)

    pairs = {}
    for link in graph.get("links", []):
        relation = link.get("relation")
        if relation not in DEPENDENCY_RELATIONS:
            continue
        src_module = node_module.get(link.get("source"))
        dst_module = node_module.get(link.get("target"))
        if not src_module or not dst_module or src_module == dst_module:
            continue
        module_a, module_b = sorted((src_module, dst_module))
        entry = pairs.setdefault(
            (module_a, module_b), {"weight": 0, "relations": set()}
        )
        entry["weight"] += 1
        entry["relations"].add(relation)

    return [
        {
            "module_a": module_a,
            "module_b": module_b,
            "relations": sorted(data["relations"]),
            "weight": data["weight"],
        }
        for (module_a, module_b), data in sorted(pairs.items())
    ]


def _merge_interfaces(existing_interfaces, crossing_edges):
    """Merge a fresh _graph_crossing_edges() result into the prior
    `interfaces` list, same "state is a record of decisions made" posture
    scan()'s module-merge loop already applies:

    - A pair already settled ("generated"/"deferred") is never touched,
      even if this scan's weight/relations differ from what was recorded.
    - A pair still "pending" is refreshed with the latest weight/relations
      (cheap repeat scans should reflect current graph state until a
      decision is made).
    - A previously-unseen pair is added as a new "pending" entry.
    - A pair no longer present in this scan's crossing_edges keeps its
      history -- not silently dropped, mirroring the module-merge loop's
      same rule for modules no longer present on disk.
    """
    existing_by_id = {e["id"]: e for e in existing_interfaces}
    seen_ids = set()
    merged = []

    for edge in crossing_edges:
        interface_id = _interface_id(edge["module_a"], edge["module_b"])
        seen_ids.add(interface_id)
        prior = existing_by_id.get(interface_id)
        if prior is not None and prior["status"] != "pending":
            merged.append(prior)
            continue
        merged.append({
            "id": interface_id,
            "module_a": edge["module_a"],
            "module_b": edge["module_b"],
            "relations": edge["relations"],
            "weight": edge["weight"],
            "status": "pending",
            "output_path": None,
            "generated_at": None,
            "defer_reason": None,
        })

    for interface_id, entry in existing_by_id.items():
        if interface_id not in seen_ids:
            merged.append(entry)

    return merged


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


def _check_graph_cep_contamination(repo_root, graph):
    """Defend against a different graphify footgun than
    _check_graph_repo_root_alignment() above: instead of pointing at the
    wrong repo entirely, graphify walked the RIGHT repo but never had CEP's
    own installed footprint (skills/, docs, wizard scripts -- everything
    this repo's own .cep-install.json manifest lists under `owned_paths`)
    excluded from the scan. The graph still looks plausible -- real module
    names, real in-degrees -- but a meaningful slice of its nodes are CEP's
    own internal wiring, not the target repo's code, which quietly inflates
    in-degree/tier numbers for whatever modules happen to sit near CEP's
    installed paths.

    Returns None if there's nothing to check (no manifest, or the manifest
    has no owned_paths -- _read_cep_manifest()'s own "no signal available"
    convention) or if the graph is empty. Returns a warning string (never
    raises -- this is a much thinner signal than the repo-root mismatch
    above, so it stays advisory) once the contaminated fraction exceeds
    GRAPH_CEP_CONTAMINATION_WARN_THRESHOLD.
    """
    manifest_owned = _read_cep_manifest(repo_root)
    if not manifest_owned:
        return None

    repo_root = Path(repo_root)
    total = 0
    contaminated = 0
    for node in graph.get("nodes", []):
        source_file = node.get("source_file")
        if not source_file:
            continue
        total += 1
        node_path = (repo_root / source_file.replace("\\", "/")).resolve()
        for owned in manifest_owned:
            try:
                node_path.relative_to(owned)
            except ValueError:
                continue
            contaminated += 1
            break

    if total == 0:
        return None

    ratio = contaminated / total
    if ratio <= GRAPH_CEP_CONTAMINATION_WARN_THRESHOLD:
        return None

    return (
        "{pct:.0f}% of graph.json's nodes ({contaminated_n}/{total_n}) live "
        "under paths this repo's own .cep-install.json manifest marks as "
        "CEP-owned -- graphify most likely walked CEP's own installed "
        "skills/docs rather than being scoped away from them, which "
        "inflates in-degree/tier numbers with CEP's own internal wiring "
        "instead of the target repo's real code. Fix: generate a "
        ".graphifyignore from .cep-install.json's owned_paths (see "
        "ult-codegraph/SKILL.md Step 0), then re-run `graphify update` and "
        "this scan.".format(
            pct=ratio * 100,
            contaminated_n=contaminated,
            total_n=total,
        )
    )


# --------------------------------------------------------------------------- #
# Tier assignment                                                            #
# --------------------------------------------------------------------------- #

def _tier_for_graph(in_degree, generated, node_count):
    if generated:
        return 0, "generated"
    # A module with zero graph nodes is not a real leaf (tier 3) -- it's
    # empty: graphify found nothing under it to index at all (e.g. a
    # directory graphify never walked, or one with no parseable files).
    # in_degree alone can't tell these apart -- a genuine tier-3 leaf with
    # plenty of its own nodes also has in_degree 0, since nothing else
    # imports it. node_count is the distinguishing signal (see
    # _graph_module_node_counts()). Checked before the thresholds below so
    # it never gets miscounted as a normal, selectable tier-3 module.
    if node_count == 0:
        return None, "empty"
    if in_degree >= TIER1_MIN_IN_DEGREE:
        return 1, "graph:in-degree"
    if in_degree >= 1:
        return 2, "graph:in-degree"
    return 3, "graph:in-degree"


def _tier_for_heuristic(file_count, generated):
    if generated:
        return 0, "generated"
    # Same empty-vs-leaf distinction as _tier_for_graph()'s node_count
    # check, but heuristic mode's own existing signal (file_count) already
    # carries it directly -- no separate lookup needed.
    if file_count == 0:
        return None, "empty"
    if file_count >= TIER1_MIN_FILE_COUNT:
        return 1, "heuristic:file-count"
    if file_count >= 1:
        return 2, "heuristic:file-count"
    return 3, "heuristic:file-count"


# --------------------------------------------------------------------------- #
# State load/save                                                            #
# --------------------------------------------------------------------------- #

def _ensure_repo_docs(repo_docs):
    """Return a repo_docs dict guaranteed to have every REPO_DOC_KINDS key,
    filling in a fresh "pending" entry for any kind missing (new schema
    field on an older state file, or a from-scratch empty_state()). Never
    overwrites a kind already present -- same "don't touch settled state"
    posture as _merge_interfaces()."""
    repo_docs = dict(repo_docs or {})
    for kind in REPO_DOC_KINDS:
        repo_docs.setdefault(kind, {
            "status": "pending",
            "output_path": None,
            "generated_at": None,
            "skip_reason": None,
        })
    return repo_docs


def empty_state():
    return {
        "schema_version": SCHEMA_VERSION,
        "repo_scan": {"graph_source": None, "graph_path": None, "scanned_at": None},
        "modules": [],
        "interfaces": [],
        "repo_docs": _ensure_repo_docs({}),
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
    state.setdefault("interfaces", [])
    state["repo_docs"] = _ensure_repo_docs(state.get("repo_docs"))
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
        "interfaces": state.get("interfaces", []),
        "repo_docs": _ensure_repo_docs(state.get("repo_docs")),
    }
    path.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")


def _find_module(state, module_id):
    for m in state.get("modules", []):
        if m["id"] == module_id:
            return m
    raise ValueError("no module with id '{}' in state -- run `scan` first".format(module_id))


def _find_repo_doc(state, kind):
    if kind not in REPO_DOC_KINDS:
        raise ValueError(
            "unknown repo-doc kind '{}' -- must be one of {}".format(kind, REPO_DOC_KINDS)
        )
    return state["repo_docs"][kind]


def _find_interface(state, interface_id):
    for i in state.get("interfaces", []):
        if i["id"] == interface_id:
            return i
    raise ValueError(
        "no interface with id '{}' in state -- run `scan --graph-mode graphify` first".format(
            interface_id
        )
    )


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
    node_counts = {}
    alignment_warning = None
    contamination_warning = None
    if graph_mode == "graphify":
        graph = _load_graph(graph_path)
        # Cross-check BEFORE tiering, and before any state mutation below --
        # a zero-overlap mismatch must abort with no partial/corrupt state
        # written, same posture as _load_graph()'s own missing-file check.
        alignment_warning = _check_graph_repo_root_alignment(
            _graph_module_names(graph), module_names, graph_path
        )
        # A different, thinner signal than the alignment check above -- this
        # one stays advisory even at its own trigger threshold, so it's a
        # plain warning lookup rather than something that can abort the scan.
        contamination_warning = _check_graph_cep_contamination(repo_root, graph)
        in_degrees = _graph_in_degrees(graph)
        node_counts = _graph_module_node_counts(graph)
        # Same one-time graph load, same access pattern as in_degrees above
        # -- see _graph_crossing_edges()'s docstring for why this is the
        # pair, not the direction.
        state["interfaces"] = _merge_interfaces(
            state.get("interfaces", []), _graph_crossing_edges(graph)
        )
    # Heuristic mode: leave state["interfaces"] exactly as it was (empty if
    # never scanned in graphify mode) -- there's no crossing-edge data to
    # compute it from in this mode.

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
            node_count = node_counts.get(name, 0)
            tier, basis = _tier_for_graph(in_degree, generated, node_count)
        else:
            in_degree = None
            tier, basis = _tier_for_heuristic(len(files), generated)

        if tier == 0:
            skip_reason = "generated/vendor code (auto-detected)"
        elif tier is None:
            # Distinct wording from the tier-0 case above so "why was this
            # skipped" stays answerable at a glance -- generated/vendor and
            # empty are different reasons a module never became selectable.
            skip_reason = (
                "empty directory (no graph nodes found under it)"
                if graph_mode == "graphify"
                else "empty directory (no files found)"
            )
        else:
            skip_reason = None

        entry = {
            "id": module_id,
            "tier": tier,
            "in_degree": in_degree,
            "file_count": len(files),
            "basis": basis,
            "status": "pending" if tier not in (0, None) else "skipped",
            "generated_at": None,
            "output_path": None,
            "skip_reason": skip_reason,
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
        # Non-fatal CEP-own-footprint contamination warning, if any -- None
        # when clean, when there's no manifest to check against, or when
        # graph_mode == "heuristic". Same "persist it, don't just print it"
        # reasoning as graph_module_overlap_warning above.
        "graph_cep_contamination_warning": contamination_warning,
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


def mark_repo_doc_generated(state, kind, output_path):
    doc = _find_repo_doc(state, kind)
    if doc["status"] != "pending":
        raise ValueError(
            "repo doc '{}' is already '{}' -- not pending".format(kind, doc["status"])
        )
    doc["status"] = "generated"
    doc["output_path"] = output_path
    doc["generated_at"] = _now_iso()
    return doc


def mark_repo_doc_skipped(state, kind, reason):
    doc = _find_repo_doc(state, kind)
    if doc["status"] != "pending":
        raise ValueError(
            "repo doc '{}' is already '{}' -- not pending".format(kind, doc["status"])
        )
    doc["status"] = "skipped"
    doc["skip_reason"] = reason
    return doc


def mark_interface_generated(state, interface_id, output_path):
    interface = _find_interface(state, interface_id)
    if interface["status"] != "pending":
        raise ValueError(
            "interface '{}' is already '{}' -- not pending".format(
                interface_id, interface["status"]
            )
        )
    interface["status"] = "generated"
    interface["output_path"] = output_path
    interface["generated_at"] = _now_iso()
    return interface


def mark_interface_deferred(state, interface_id, reason):
    interface = _find_interface(state, interface_id)
    if interface["status"] != "pending":
        raise ValueError(
            "interface '{}' is already '{}' -- not pending".format(
                interface_id, interface["status"]
            )
        )
    interface["status"] = "deferred"
    interface["defer_reason"] = reason
    return interface


def list_interfaces(state, eligible_only=False, generated_module_ids=None):
    """Return the interfaces list, optionally filtered to SKILL.md Step 5d's
    exact eligibility rule: status == "pending" AND both endpoint modules
    are already "generated" in this same state.

    generated_module_ids defaults to computing itself from state["modules"]
    when not supplied -- callers that already have the module list handy
    (e.g. a single CLI invocation that just loaded state once) may pass it
    to avoid a second pass; the CLI entry point relies on the default."""
    interfaces = state.get("interfaces", [])
    if not eligible_only:
        return interfaces

    if generated_module_ids is None:
        generated_module_ids = {
            m["id"] for m in state.get("modules", []) if m["status"] == "generated"
        }
    return [
        i
        for i in interfaces
        if i["status"] == "pending"
        and (i["module_a"] + "/") in generated_module_ids
        and (i["module_b"] + "/") in generated_module_ids
    ]


# --------------------------------------------------------------------------- #
# render-index                                                                #
# --------------------------------------------------------------------------- #

_TIER_TITLES = {
    1: "## Tier 1 -- high-importance modules",
    2: "## Tier 2 -- ordinary modules",
    3: "## Tier 3 -- leaf modules (no other module depends on these)",
    0: "## Tier 0 -- generated/vendor (auto-skipped)",
    None: "## Empty (auto-skipped, no files/nodes found)",
}


def render_index(state, repo_name):
    modules = state.get("modules", [])
    by_tier = {0: [], 1: [], 2: [], 3: [], None: []}
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
    contamination_warning = (state.get("repo_scan") or {}).get(
        "graph_cep_contamination_warning"
    )
    if contamination_warning:
        lines.append("")
        lines.append("**WARNING:** {}".format(contamination_warning))
    lines.append("")

    for tier in (1, 2, 3, 0, None):
        entries = by_tier.get(tier, [])
        lines.append(_TIER_TITLES[tier])
        lines.append("")
        if not entries:
            lines.append("_none_")
            lines.append("")
            continue
        for m in sorted(entries, key=lambda e: e["id"]):
            if tier is None:
                # Empty modules: file_count is always 0 here, and in_degree
                # (graph mode) is trivially 0 too -- neither is informative,
                # so skip the usual in-degree/file-count detail entirely.
                detail = "empty"
            elif m.get("in_degree") is not None:
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

    repo_docs = _ensure_repo_docs(state.get("repo_docs"))
    lines.append("## Repo-wide docs")
    lines.append("")
    for kind in REPO_DOC_KINDS:
        doc = repo_docs[kind]
        label = kind.replace("_", " ").title()
        path_note = " -> `{}`".format(doc["output_path"]) if doc.get("output_path") else ""
        lines.append("- {} -- **{}**{}".format(label, doc["status"], path_note))
    lines.append("")

    interfaces = state.get("interfaces", [])
    lines.append("## Interface boundaries")
    lines.append("")
    if not interfaces:
        lines.append("_none -- graph mode not yet scanned, or no crossing-module edges found._")
        lines.append("")
    else:
        for i in sorted(interfaces, key=lambda e: e["id"]):
            path_note = " -> `{}`".format(i["output_path"]) if i.get("output_path") else ""
            lines.append(
                "- `{}` <-> `{}` ({}, weight {}) -- **{}**{}".format(
                    i["module_a"], i["module_b"], ",".join(i["relations"]), i["weight"],
                    i["status"], path_note,
                )
            )
        lines.append("")
        i_generated = sum(1 for i in interfaces if i["status"] == "generated")
        i_pending = sum(1 for i in interfaces if i["status"] == "pending")
        i_deferred = sum(1 for i in interfaces if i["status"] == "deferred")
        lines.append(
            "**Progress:** {} generated, {} pending, {} deferred ({} interfaces total).".format(
                i_generated, i_pending, i_deferred, len(interfaces)
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

    repo_docs = _ensure_repo_docs(state.get("repo_docs"))
    interfaces = state.get("interfaces", [])
    return {
        "schema_version": state.get("schema_version"),
        "repo_scan": state.get("repo_scan", {}),
        "total_modules": len(modules),
        "by_tier": by_tier,
        "generated": sum(1 for m in modules if m["status"] == "generated"),
        "pending": sum(1 for m in modules if m["status"] == "pending"),
        "skipped": sum(1 for m in modules if m["status"] == "skipped"),
        "repo_docs": {kind: doc["status"] for kind, doc in repo_docs.items()},
        "interfaces": {
            "total": len(interfaces),
            "generated": sum(1 for i in interfaces if i["status"] == "generated"),
            "pending": sum(1 for i in interfaces if i["status"] == "pending"),
            "deferred": sum(1 for i in interfaces if i["status"] == "deferred"),
        },
    }


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #

def _cmd_probe_size(args):
    print(json.dumps(probe_size(args.repo_root), indent=2))
    return 0


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
    contamination_warning = (state.get("repo_scan") or {}).get(
        "graph_cep_contamination_warning"
    )
    if contamination_warning:
        # Same "printed immediately, not just persisted" posture as the
        # overlap warning above.
        print("WARNING: {}".format(contamination_warning), file=sys.stderr)
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


def _cmd_mark_repo_doc_generated(args):
    state = load_state(args.state)
    try:
        doc = mark_repo_doc_generated(state, args.kind, args.output)
    except ValueError as e:
        print("ERROR: {}".format(e), file=sys.stderr)
        return 1
    save_state(args.state, state)
    print(json.dumps(doc, indent=2))
    return 0


def _cmd_mark_repo_doc_skipped(args):
    state = load_state(args.state)
    try:
        doc = mark_repo_doc_skipped(state, args.kind, args.reason)
    except ValueError as e:
        print("ERROR: {}".format(e), file=sys.stderr)
        return 1
    save_state(args.state, state)
    print(json.dumps(doc, indent=2))
    return 0


def _cmd_mark_interface_generated(args):
    state = load_state(args.state)
    try:
        interface = mark_interface_generated(state, args.interface_id, args.output)
    except ValueError as e:
        print("ERROR: {}".format(e), file=sys.stderr)
        return 1
    save_state(args.state, state)
    print(json.dumps(interface, indent=2))
    return 0


def _cmd_mark_interface_deferred(args):
    state = load_state(args.state)
    try:
        interface = mark_interface_deferred(state, args.interface_id, args.reason)
    except ValueError as e:
        print("ERROR: {}".format(e), file=sys.stderr)
        return 1
    save_state(args.state, state)
    print(json.dumps(interface, indent=2))
    return 0


def _cmd_list_interfaces(args):
    state = load_state(args.state)
    print(json.dumps(list_interfaces(state, eligible_only=args.eligible_only), indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="scaffold_state.py",
        description="Read/write the D24 Phase B triage/checkpoint state (TRIAGE-STATE.json).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_probe = sub.add_parser(
        "probe-size",
        help="Count substantive top-level directories (Step 4's small/large gate).",
    )
    p_probe.add_argument("--repo-root", required=True)
    p_probe.set_defaults(func=_cmd_probe_size)

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

    p_rdgen = sub.add_parser("mark-repo-doc-generated", help="Mark one repo-wide doc generated.")
    p_rdgen.add_argument("state")
    p_rdgen.add_argument("kind", choices=REPO_DOC_KINDS)
    p_rdgen.add_argument("--output", required=True)
    p_rdgen.set_defaults(func=_cmd_mark_repo_doc_generated)

    p_rdskip = sub.add_parser("mark-repo-doc-skipped", help="Mark one repo-wide doc skipped.")
    p_rdskip.add_argument("state")
    p_rdskip.add_argument("kind", choices=REPO_DOC_KINDS)
    p_rdskip.add_argument("--reason", required=True)
    p_rdskip.set_defaults(func=_cmd_mark_repo_doc_skipped)

    p_ifgen = sub.add_parser(
        "mark-interface-generated", help="Mark one interface-boundary pair generated."
    )
    p_ifgen.add_argument("state")
    p_ifgen.add_argument("interface_id")
    p_ifgen.add_argument("--output", required=True)
    p_ifgen.set_defaults(func=_cmd_mark_interface_generated)

    p_ifdef = sub.add_parser(
        "mark-interface-deferred", help="Mark one interface-boundary pair deferred."
    )
    p_ifdef.add_argument("state")
    p_ifdef.add_argument("interface_id")
    p_ifdef.add_argument("--reason", required=True)
    p_ifdef.set_defaults(func=_cmd_mark_interface_deferred)

    p_iflist = sub.add_parser("list-interfaces", help="Print the interfaces list.")
    p_iflist.add_argument("state")
    p_iflist.add_argument(
        "--eligible-only", action="store_true",
        help="Filter to pending pairs whose both endpoint modules are already generated.",
    )
    p_iflist.set_defaults(func=_cmd_list_interfaces)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
