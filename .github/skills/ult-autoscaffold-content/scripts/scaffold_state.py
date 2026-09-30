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
      [--with-sites --repo-root <path> --graph-path <graphify-out/graph.json>]
    Prints the interfaces list. --eligible-only filters to "pending" pairs
    whose both endpoint modules have settled in this same state -- either
    already "generated" (tier 1/2), or "skipped" AND tier 3 (a leaf module
    that by design never gets its own context_md packet, so "generated"
    would otherwise be permanently unreachable for it) -- the exact
    tier-gating rule SKILL.md Step 5d applies, exposed here so the agent
    doesn't hand-read/hand-cross-reference the JSON.

    --with-sites adds a "call_sites" key (list of "path:Lline" strings,
    sorted, empty when none found -- Sec 5.2's evidence_hints.call_sites
    shape) to every printed entry, derived entirely from --graph-path's
    already-loaded node/link data: for each node-level DEPENDENCY_RELATIONS
    edge crossing that specific pair, the edge's source node names which
    file to look in and its target node names which symbol to look for: a
    plain, deterministic text search of that one file (no re-running the
    graph indexer -- see _interface_call_sites()'s docstring for the exact
    honesty posture, matching _probe_tool_versions()'s "citation index, not
    a parsed call verification" framing). Requires --repo-root and
    --graph-path together; refuses otherwise. Absent any textual match,
    "call_sites" is an honest empty list, never a guess.

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
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import autoscaffold_atomic_write as aaw

SCHEMA_VERSION = 1

_STATUSES = ("pending", "generated", "skipped")

# Content-identical to ult-repo-layout/discover_layers.py's own
# SCAN_IGNORED_DIR_NAMES (plus that module's separate CEP_BUCKET_DIR_NAMES,
# also mirrored below) -- a small local duplicate, not a shared import
# (house convention: see module docstring). Keep the two sets equal.
#
# The equality is asserted from both sides: each skill's own test suite
# imports the sibling skill's module off sys.path and compares the two sets
# (test_scaffold_state.py's TestScanIgnoredDirNamesParity here,
# test_discover_layers.py's counterpart there), so an edit made from either
# side fails loudly in that side's own suite instead of silently diverging
# again. Either suite skips its own check when the sibling skill's
# directory isn't installed -- a partial checkout is not this test's
# failure to report.
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

# Precomputed casefolded mirror of SCAN_IGNORED_DIR_NAMES, matching
# discover_layers.py's own _SCAN_IGNORED_DIR_NAMES_CF - a real-world repo
# directory ("Vendor/", "Build/", "Node_Modules/") won't always match this
# module's lowercase-by-convention names, so _prune_ignored below compares
# case-insensitively rather than assuming callers casefold first.
_SCAN_IGNORED_DIR_NAMES_CF = {n.casefold() for n in SCAN_IGNORED_DIR_NAMES}

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

# Tier 0: orphaned-CEP-output signal, independent of the vendor/generated
# code detection above and independent of state entirely. Every doc this
# skill itself writes carries `generated_by: ult-autoscaffold-content` in
# its frontmatter (see REQUIRED_FRONTMATTER_KEYS below) -- a self-describing
# marker any content-mode template emits, regardless of which target repo
# it was run against. _settled_output_subtrees() below only recognizes a
# repo's own prior CEP output when it's recorded in the SAME state file
# doing the scanning; it has no way to know about output a *different* (or
# reset, or side/test) state file previously generated into the same
# repo_root. Without a state-independent fallback, such a directory reads
# as a brand-new real module full of real content on the very next scan --
# found the hard way running a fresh acceptance state against a repo that
# already carried a prior run's real output on disk. Reusing
# GENERATED_FILE_MAJORITY_THRESHOLD's same "majority, not one stray file"
# posture rather than inventing a second threshold with no cited rationale.
ORPHANED_CEP_OUTPUT_GENERATED_BY = "ult-autoscaffold-content"

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

# The evidence gate's fixed, conventional filename sets probe_size()'s
# `signals` dict below checks for -- each one is a piece of evidence a
# `grounded`/`augmented` doc can later cite (must_cite), e.g.
# a CODING-STANDARDS.md doc citing
# .clang-format/CPPLINT.cfg/format.sh/.github/workflows/cpp.yml.
# Deliberately closed sets, not a config key: a repo using an
# unlisted formatter just yields an empty formatter_config signal rather
# than a false claim, same as any other absent-evidence case below.
#
# "test.sh" sits in WRAPPER_SCRIPT_FILENAMES, not the test-config set below
# -- the evidence gate's own illustration groups it with format.sh as a generic
# wrapper script, distinct from a build system's own test-registration
# (its example: "CMakeLists.txt:enable_testing").
FORMATTER_CONFIG_FILENAMES = {
    ".clang-format", ".editorconfig", ".prettierrc", ".prettierrc.json",
    ".prettierrc.yaml", ".prettierrc.yml", "rustfmt.toml", ".style.yapf",
}
LINTER_CONFIG_FILENAMES = {
    "CPPLINT.cfg", ".eslintrc", ".eslintrc.json", ".eslintrc.js",
    ".eslintrc.yaml", ".eslintrc.yml", ".pylintrc", ".flake8", "ruff.toml",
}
WRAPPER_SCRIPT_FILENAMES = {"format.sh", "lint.sh", "build.sh", "test.sh"}
TEST_CONFIG_FILENAMES = {
    "pytest.ini", "tox.ini", "jest.config.js", "jest.config.ts", "karma.conf.js",
}
CI_CONFIG_FILENAMES = {".gitlab-ci.yml", "azure-pipelines.yml", "Jenkinsfile"}
CONTRIBUTING_FILENAMES = {"CONTRIBUTING.md", "CONTRIBUTING.rst", "CONTRIBUTING.txt"}

# Sec 4.3's tool_versions illustration maps a formatter/linter's own config
# file to a human tool name ({"clang-format": [...]}) -- only tools we can
# name this way get a tool_versions entry at all; a config file with no
# mapping here just contributes nothing to tool_versions (still shows up in
# formatter_config/linter_config either way). ".editorconfig" is
# deliberately absent: it isn't a single versioned tool.
TOOL_NAME_BY_CONFIG_FILENAME = {
    ".clang-format": "clang-format",
    ".prettierrc": "prettier", ".prettierrc.json": "prettier",
    ".prettierrc.yaml": "prettier", ".prettierrc.yml": "prettier",
    "rustfmt.toml": "rustfmt",
    ".style.yapf": "yapf",
    "CPPLINT.cfg": "cpplint",
    ".eslintrc": "eslint", ".eslintrc.json": "eslint", ".eslintrc.js": "eslint",
    ".eslintrc.yaml": "eslint", ".eslintrc.yml": "eslint",
    ".pylintrc": "pylint",
    ".flake8": "flake8",
    "ruff.toml": "ruff",
}

# The three document kinds Sec 4.3's grounded_viable illustration names
# (`{"coding_standards": ..., "testing_guidelines": ..., "requirements_overview": ...}`).
# The first two match REPO_DOC_KINDS below exactly; "requirements_overview"
# is the What-L2 overview/CONTEXT.md kind's grounding viability and isn't
# otherwise modeled as a constant yet, so it's named here verbatim from the
# proposal rather than invented.
GROUNDED_VIABLE_KINDS = ("coding_standards", "testing_guidelines", "requirements_overview")

# Repo-wide convention docs SKILL.md Step 5c can generate -- exactly these
# two kinds, both existence-gated (never overwrite a file that's already
# there). Fixed tuple, not user-extensible: a third kind needs its own
# references/*.md + templates/*.md pair and SKILL.md step, not a config
# flag here.
REPO_DOC_KINDS = ("coding_standards", "testing_guidelines")

# The work-packet layer/kind vocabulary, as consumed by
# `plan`/build_work_packets() below.
#
# P0a only ever plans How-L2 packets: context_md per pending module (Sec
# 1.1's "org/<module>/CONTEXT.md"), the two REPO_DOC_KINDS above, and
# interface_boundary per pending interface (SKILL.md's
# "<how_l2_path>/interfaces/<module-a>-to-<module-b>.md"). The existing
# D24 Phase B state model this file already reads/writes (modules,
# repo_docs, interfaces above) has no tracking at all for What-L2's
# overview/CONTEXT.md kinds or a separate How-L2 architecture_overview
# kind (Sec 4.2's other two cap-matrix rows) -- `plan` doesn't invent
# packets or new state sections for those here. Widening `plan` to those
# kinds is new scope TASK-0103/0104 never asked for; it's a gap to raise
# at the P0a phase-boundary report, not something to silently assume.
PACKET_LAYER = "how_l2"
PACKET_LAYER_SLUG = "how-l2"
PACKET_KIND_SLUG = {
    "context_md": "context",
    "coding_standards": "coding-standards",
    "testing_guidelines": "testing-guidelines",
    "interface_boundary": "interface",
}

# Sec 4's required_sections per kind -- each template file's own "##"
# headings (templates/*.md), minus its H1 title, minus
# context-md-template.md's own "State machine (if applicable)" section
# (explicitly conditional in the template itself, so not required for
# every module).
REQUIRED_SECTIONS_BY_KIND = {
    "context_md": [
        "Purpose", "Inputs", "Outputs", "Key abstractions", "Dependencies",
        "Design invariants", "Gotchas",
    ],
    "coding_standards": [
        "Detected tooling", "Formatting", "Naming conventions",
        "Error handling", "Logging", "Review expectations",
    ],
    "testing_guidelines": [
        "Detected tooling", "Test layout", "Structure",
        "Coverage expectations", "Naming convention",
    ],
    "interface_boundary": [
        "Relations observed", "Contract", "Versioning / deprecation policy",
        "Owners",
    ],
}

TEMPLATE_PATH_BY_KIND = {
    "context_md": "templates/context-md-template.md",
    "coding_standards": "templates/coding-standards-template.md",
    "testing_guidelines": "templates/testing-guidelines-template.md",
    "interface_boundary": "templates/interface-boundary-template.md",
}

# Sec 5.2's packet.probe_checklist_ref example points at
# "references/evidence-probes.md#context-md" -- that file doesn't exist in
# this skill; only the four per-kind reference docs already shipped
# (references/*.md) do. Packets point at the existing doc for their own
# kind instead of a dangling path. A dedicated evidence-probes.md, if ever
# authored, is a documentation task (W1), not something `plan` should
# assume into existence.
PROBE_CHECKLIST_REF_BY_KIND = {
    "context_md": "references/module-context-depth-by-tier.md",
    "coding_standards": "references/generate-coding-standards.md",
    "testing_guidelines": "references/generate-testing-guidelines.md",
    "interface_boundary": "references/generate-interface-docs.md",
}

# O4: per-packet soft read budget, prioritized order must_cite first then
# checklist order -- exceeding it is reported (budget_exceeded: true) but
# is never a validation failure (Sec 16, O4). Tier 3 isn't named in O4's
# own example ("40 files Tier 1, 20 Tier 2, 30 repo docs") -- flagged
# implementation default for tier 3, same posture as
# TIER1_MIN_IN_DEGREE/TIER1_MIN_FILE_COUNT above. In practice this value
# is inert today: PACKET_ELIGIBLE_MODULE_TIERS below never plans a
# context_md packet for a Tier 3 module in the first place.
READ_BUDGET_BY_TIER = {1: 40, 2: 20, 3: 10}
READ_BUDGET_REPO_DOC = 30
# O4 doesn't name interface docs at all -- flagged implementation default,
# same posture as the tier-3 entry above.
READ_BUDGET_INTERFACE = 20

# Sec 1.1's worked-example observation -- "Tier-3 modules were generated. The skill
# skips Tier 3 by default" -- stated as the general planning rule, not
# just that one incident. context_md packets are only planned for these
# tiers; a future task can add an explicit include-Tier-3 override flag,
# but `plan` doesn't invent one here.
PACKET_ELIGIBLE_MODULE_TIERS = (1, 2)

# O3: validation floor thresholds live here, keyed by (kind, tier) -- no
# config key (Sec 16: "read_budget is not a config key; it is set per
# packet by `plan` from the constants block" -- same posture applies to
# validation floors). The (context_md, 1) entry is Sec 5.2's own worked
# example, verbatim. Every other entry is a flagged implementation default
# (same posture as TIER1_MIN_IN_DEGREE above) pending TASK-0106's
# validator work against real fixture data. Repo docs and interface docs
# carry no module tier, hence the `None` tier key for both.
VALIDATION_FLOORS = {
    ("context_md", 1): {"min_distinct_cited_files": 5, "min_body_bytes": 1500},
    ("context_md", 2): {"min_distinct_cited_files": 3, "min_body_bytes": 800},
    ("coding_standards", None): {"min_distinct_cited_files": 3, "min_body_bytes": 800},
    ("testing_guidelines", None): {"min_distinct_cited_files": 3, "min_body_bytes": 800},
    ("interface_boundary", None): {"min_distinct_cited_files": 2, "min_body_bytes": 600},
}

# _probe_cmake_test_registration's test_config signal for a CMake project
# is the literal string "CMakeLists.txt:enable_testing" (Sec 4.3's own
# worked-example illustration), not a real filesystem path -- it flows
# into must_cite for testing_guidelines packets verbatim. Sec 6's
# "Must-cite" row requires this exact string appear in a [src:] citation;
# its separate "Citation resolution" row requires every [src:] path to
# exist on disk. Applied literally, no CMake-based repo could ever
# satisfy both rows for this one marker -- confirmed against a real
# CMake-based repo's CMakeLists.txt during the P0a evidence gate
# (TASK-0115). validate()
# excludes exactly this literal marker from the existence/line-range
# check below; it still must be cited to satisfy must_cite, and it still
# never counts toward min_distinct_cited_files (it names no real file).
_LITERAL_MUST_CITE_MARKERS = frozenset({"CMakeLists.txt:enable_testing"})

# Sec 5.2's evidence_hints shape when no graph is available at all
# (heuristic-mode runs, or `plan` invoked with no --graph-path) -- every
# packet still carries all four keys so the schema shape never varies by
# host/mode, only the content does.
_EMPTY_EVIDENCE_HINTS = {
    "top_symbols_by_in_degree": [], "depends_on": [], "depended_on_by": [],
    "call_sites": [],
}

# Filenames _directory_is_purely_settled_output() tolerates sitting
# directly at the top level of an already-recognized CEP output root even
# when their own output_path was never individually recorded in state.
# This can never apply to a directory with no tracked output at all --
# _directory_is_purely_settled_output() is only ever called for names
# already present in _settled_output_subtrees()'s result, i.e. names with
# at least one *other* genuinely tracked output_path underneath them -- so
# an unrelated top-level directory that happens to hold a file with one of
# these names is never at risk of being silently excluded.
#
# Two real gaps closed by this, both found by adversarial review of the
# original router-file-tracking fix:
#   - SKILL.md Step 5c's "already exists: skip it silently" branch for
#     CODING-STANDARDS.md/TESTING-GUIDELINES.md calls no mark-* command at
#     all, so a pre-existing repo doc's output_path is never recorded even
#     though every other generated file is.
#   - A TRIAGE-STATE.json written before the "index" key existed has no
#     record of CEP-INDEX.md even though the file is already on disk, and
#     a finished run never gets a second chance to record it: render-index
#     is only called during generation, not on a mere resumed scan.
_CONVENTIONAL_OUTPUT_FILENAMES = frozenset(
    {"CEP-INDEX.md", "CODING-STANDARDS.md", "TESTING-GUIDELINES.md"}
)


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
        if d.casefold() in _SCAN_IGNORED_DIR_NAMES_CF or d in CEP_BUCKET_DIR_NAMES:
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


def _settled_output_subtrees(repo_root, state):
    """Top-level directory names that are themselves the first path segment
    of some already-recorded generation output in `state`, mapped to
    {"dirs": {...}, "files": {...}} describing exactly what that output
    covers under that name. _settled_output_root_names() below is just
    this dict's key set; scan() needs the fuller shape too, to tell a
    top-level name that is PURELY settled output (nothing else lives
    there -- safe to exclude wholesale, same as always) apart from one
    that also holds real, unrelated content and merely happens to share
    its first path segment with some output -- see
    _directory_is_purely_settled_output(), which is what draws that line.
    Without either check, a resolved How-L2 output root that happens to
    sit at the repo's own top level gets enumerated by
    _top_level_candidate_dirs() on the very next scan and misfiled as a
    brand-new pending module: this tool's own generated output
    reclassified as unscanned application code.

    Two output_path shapes are tracked, deliberately NOT collapsed into
    one:

    - 3+ path components (e.g. "org/core/CONTEXT.md") have a genuine
      intermediate directory of their own ("org/core") that's narrower
      than the top-level name ("org") -- so "dirs" records that
      intermediate directory, and everything under it (even a file not
      individually named in state, like an asset generation dropped
      alongside CONTEXT.md) counts as covered.

    - EXACTLY 2 path components (e.g. "conventions/CODING-STANDARDS.md")
      have no such intermediate directory: the file sits directly inside
      the top-level directory, so "the directory it lives in" IS the
      top-level directory itself. Recording that as a "dirs" entry the
      way the 3+-component case does would make
      _directory_is_purely_settled_output() trivially true for ANY
      content under that top-level name, regardless of how much real,
      unrelated content also lives there -- an adversarial review caught
      exactly this: How-L2 candidates like "conventions/" are real,
      pre-existing, content-bearing directories that SKILL.md writes
      CODING-STANDARDS.md/TESTING-GUIDELINES.md straight into, not
      dedicated output roots, and the whole directory (not just the one
      generated file) was being silently swallowed. So a 2-component
      output_path instead goes into "files" as the exact resolved file --
      narrow enough that it can only ever cover that one known file,
      never a directory's other, unrelated content.

    A 1-component output_path (a bare top-level output file sitting at the
    repo's own root, outside any resolved How-L2 directory) still
    contributes nothing at all: nothing exists under a candidate top-level
    name for a later scan to mistake for a module.

    Every state section that can carry an `output_path` is checked --
    modules, repo_docs, interfaces, and the router index all persist one,
    and the same reclassification risk applies to all four, not just
    modules. The router index is the easiest of the four to miss: SKILL.md
    Step 5b writes CEP-INDEX.md straight to disk under the resolved How-L2
    root (e.g. "org/CEP-INDEX.md" -- a 2-component path exactly like a
    repo_doc written directly into a pre-existing top-level directory) on
    every single `render-index` call, not just once at the end, and that
    write has no pending/generated lifecycle of its own the way modules
    and repo_docs do. Skipping it here is exactly what let a resolved
    How-L2 root fail its purity check on the very next scan even after
    every module and repo_doc it contains was properly tracked -- the
    router file was the one piece of real content that check couldn't
    account for.

    A malformed, empty, or outside-repo_root output_path is skipped rather
    than raising -- this is a defensive read of persisted state, not a
    validating one; scan() should never abort over a stale or unexpected
    path recorded by an earlier run."""
    repo_root = Path(repo_root).resolve()
    dir_subtrees = {}
    file_subtrees = {}

    def _consider(output_path):
        if not output_path:
            return
        try:
            resolved = (repo_root / output_path).resolve()
            rel = resolved.relative_to(repo_root)
        except (ValueError, OSError):
            return
        if len(rel.parts) > 2:
            dir_subtrees.setdefault(rel.parts[0], set()).add(resolved.parent)
        elif len(rel.parts) == 2:
            file_subtrees.setdefault(rel.parts[0], set()).add(resolved)

    for module in state.get("modules", []):
        _consider(module.get("output_path"))
    for doc in (state.get("repo_docs") or {}).values():
        if isinstance(doc, dict):
            _consider(doc.get("output_path"))
    for interface in state.get("interfaces", []):
        _consider(interface.get("output_path"))
    _consider((state.get("index") or {}).get("output_path"))

    names = set(dir_subtrees) | set(file_subtrees)
    return {
        name: {"dirs": dir_subtrees.get(name, set()), "files": file_subtrees.get(name, set())}
        for name in names
    }


def _settled_output_root_names(repo_root, state):
    """The top-level names _settled_output_subtrees() knows about, with no
    purity distinction -- kept as its own function because it answers a
    genuinely different, narrower question ("does any recorded output live
    under this name at all") than scan() itself needs to act safely (see
    _directory_is_purely_settled_output(); scan() consults that, not this,
    before excluding or dropping anything)."""
    return set(_settled_output_subtrees(repo_root, state).keys())


def _directory_is_purely_settled_output(module_path, subtrees):
    """True when every file under module_path is covered by `subtrees`
    (the {"dirs": ..., "files": ...} value from
    _settled_output_subtrees() for this name) -- i.e. nothing besides
    CEP's own recorded generation output lives at this top level, so
    treating the whole directory as CEP-owned (excluded from
    module_names, and safe to drop a lingering "pending" entry for) loses
    nothing real. A file counts as covered if it lives under one of
    subtrees["dirs"], or if it IS one of subtrees["files"] exactly --
    membership in "files" does NOT extend to that file's sibling content,
    which is the whole point of tracking 2-component output_paths at
    file granularity instead of by directory (see
    _settled_output_subtrees()'s docstring).

    A directory containing even one file that's neither -- e.g. a
    pre-existing "docs/" that also happens to be where some module's
    output_path was resolved to, deep under
    "docs/style-guide/core/CONTEXT.md", or a pre-existing "conventions/"
    that a repo doc's output_path points straight into -- is NOT pure:
    it's a real, unrelated top-level directory that merely shares a first
    path segment with some output, and must stay a normal scan candidate.
    Silently excluding or deleting it on that coincidence alone would be
    exactly the kind of unrecoverable data loss this function exists to
    prevent (scan() still prunes the known output(s) from that module's
    own file list afterward, so the settled output itself doesn't
    pollute its tiering -- see scan()'s own use of `subtrees` for that
    part).

    A directory that doesn't exist on disk, or holds no files at all,
    counts as pure: there's no real content there for scan() to lose
    either way.

    Two narrow, defense-in-depth tolerances sit on top of the tracked-path
    check above, for files that were never individually recorded in state
    at all -- see _CONVENTIONAL_OUTPUT_FILENAMES for why these are safe
    even though nothing tracks them. Both are scoped to this directory's
    own top level (`resolved.parent == module_path`), not any nested
    subdirectory: a nested ".env"/".eslintrc"/etc. several levels down is
    real, human-authored project content (e.g. a config/ directory's own
    dotfiles), not an inert CEP-adjacent placeholder, and must still fail
    purity like any other untracked file would.

    - A dot-prefixed file directly at the top level (".gitkeep",
      ".gitignore", ...) is tolerated, mirroring _prune_ignored()'s
      existing precedent that dot-*directories* are already invisible to
      this whole mechanism. These are inert placeholders, essentially
      guaranteed to exist on any git-tracked repo, and never something
      scan() should treat as a reason to reclassify a resolved output
      root as pending.

    - A file whose name is in _CONVENTIONAL_OUTPUT_FILENAMES, also
      directly at the top level, is tolerated too. This is deliberately
      narrow: it does NOT extend to arbitrary untracked content like a
      stray "README.md", which stays a real reason to fail purity,
      consistent with this function's whole point of never silently
      swallowing unrelated content."""
    dirs = subtrees.get("dirs", set())
    files = subtrees.get("files", set())
    module_path = Path(module_path).resolve()
    for f in _iter_files(module_path):
        resolved = f.resolve()
        if resolved in files:
            continue
        if any(d in resolved.parents for d in dirs):
            continue
        if resolved.parent == module_path and (
            resolved.name.startswith(".") or resolved.name in _CONVENTIONAL_OUTPUT_FILENAMES
        ):
            continue
        return False
    return True


# --------------------------------------------------------------------------- #
# SKILL.md Step 4's small/large repo-size gate                               #
# --------------------------------------------------------------------------- #

def _read_first_line(path):
    """First non-blank line of a small text file, or None if unreadable/
    empty. Used for the one-line-of-content convention files below
    (.nvmrc, .python-version) -- never raises on a binary/garbled file."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return None


def _existing_top_level_names(repo_root, names):
    """Sorted repo-root-relative names, from `names`, that exist as a FILE
    directly at repo_root's top level (a same-named directory does not
    count). Deterministic order regardless of `names`'s own iteration
    order (it's a set)."""
    found = []
    for name in sorted(names):
        if (repo_root / name).is_file():
            found.append(name)
    return found


def _probe_ci_config(repo_root):
    """CI_CONFIG_FILENAMES hits at repo_root's top level, plus every file
    directly under .github/workflows/ (GitHub Actions' fixed convention,
    common enough to warrant its own check rather than a closed filename
    set). Sorted lexicographically. Populates signals["ci"]."""
    found = list(_existing_top_level_names(repo_root, CI_CONFIG_FILENAMES))
    workflows_dir = repo_root / ".github" / "workflows"
    if workflows_dir.is_dir():
        for entry in workflows_dir.iterdir():
            if entry.is_file():
                found.append(".github/workflows/" + entry.name)
    return sorted(found)


def _probe_cmake_test_registration(repo_root):
    """A CMakeLists.txt at repo_root containing an `enable_testing(` call
    is this test_config evidence (Sec 4.3's illustration cites it
    literally as "CMakeLists.txt:enable_testing"). Returns that exact
    citation string in a single-element list, or [] if absent/not a CMake
    project -- this is one specific, well-known build-system convention,
    not a general parser."""
    cmake_path = repo_root / "CMakeLists.txt"
    if not cmake_path.is_file():
        return []
    try:
        text = cmake_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    if "enable_testing(" in text:
        return ["CMakeLists.txt:enable_testing"]
    return []


def _probe_tool_versions(repo_root, signals):
    """Citation index, not a parsed version number: for each tool whose
    config file was found in formatter_config/linter_config
    (TOOL_NAME_BY_CONFIG_FILENAME), records every "path:Lline" location
    among the wrapper_scripts/ci/contributing evidence files that mentions
    the tool's name (case-insensitive substring). Matches Sec 4.3's
    illustration ({"clang-format": ["format.sh:17", "cpp.yml:17",
    "CONTRIBUTING.md:>=8.0.0"]}) in spirit; this implementation
    standardizes on the "path:Lline" form used consistently elsewhere in
    the packet schema (Sec 5.2's evidence_hints.call_sites, e.g.
    "orm_lib/src/DbClient.cc:L96") rather than that illustration's second,
    inconsistent "path:>=version" form -- reconciling the one legible
    internal inconsistency in an otherwise-corrupted section. Actual
    version-conflict comparison across citations is a later
    worker/validator concern (Sec 6); this function only ever points at
    where to look, deterministically, never guessing a version value."""
    tool_names = set()
    for filename in signals["formatter_config"] + signals["linter_config"]:
        tool_name = TOOL_NAME_BY_CONFIG_FILENAME.get(filename)
        if tool_name:
            tool_names.add(tool_name)
    if not tool_names:
        return {}
    candidate_paths = signals["wrapper_scripts"] + signals["ci"] + signals["contributing"]
    result = {}
    for tool_name in sorted(tool_names):
        needle = tool_name.lower()
        citations = []
        for rel_path in candidate_paths:
            try:
                text = (repo_root / rel_path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if needle in line.lower():
                    citations.append("{}:L{}".format(rel_path, line_no))
        if citations:
            result[tool_name] = citations
    return result


def _any_real_file_exists(repo_root):
    """True iff repo_root has at least one non-dot-prefixed file anywhere
    under it: a loose top-level file, or any file inside a directory
    _top_level_candidate_dirs() keeps (already pruned of ignored/CEP-bucket/
    manifest-owned/dot dirs; files inside a kept dir count even if they are
    themselves dot-prefixed -- they're inside real project structure
    already). Dot-prefixed LOOSE top-level files (tooling config like
    .clang-format, or CEP's own .cep-install.json) are deliberately
    excluded here even though they still surface in `signals` above: a
    repo holding only tooling scaffolding and no real project content yet
    is exactly what "greenfield" means below, mirroring _prune_ignored()'s
    existing dot-directory exclusion for the same reason. Used only for
    the greenfield/grounded_viable signal -- a plain existence check, never
    a count."""
    repo_root = Path(repo_root)
    if not repo_root.is_dir():
        return False
    for entry in repo_root.iterdir():
        if entry.is_file() and not entry.name.startswith("."):
            return True
    for name in _top_level_candidate_dirs(repo_root):
        for _ in _iter_files(repo_root / name):
            return True
    return False


def probe_size(repo_root):
    """Cheap, read-only repo-size signal for SKILL.md Step 4's small/large
    gate, plus the evidence gate that populates `signals` below. Counts
    top-level candidate directories under repo_root
    (_top_level_candidate_dirs()'s pruning) that clear
    MIN_FILES_FOR_SIZE_GATE files each (_iter_files()'s own recursive
    pruning) -- a conventionally near-empty structural directory (docs/
    with one README) doesn't inflate the count. No state file, no writes.

    Returns {"substantive_modules": [...names...], "count": N,
    "classification": "small"|"ambiguous"|"large", "signals": {...},
    "grounded_viable": {...}, "greenfield": bool} -- field names and
    shapes match Sec 4.3's evidence-gate illustration exactly. See
    SMALL_REPO_MAX_MODULES/LARGE_REPO_MIN_MODULES above for the size-gate
    thresholds; the ambiguous band has no safe default on purpose.

    `signals` is evidence a grounded/augmented doc can cite (must_cite):
    formatter_config, linter_config, wrapper_scripts, test_config, ci,
    contributing (each a sorted list of repo-relative paths, or bare
    citation strings for test_config's build-system markers) and
    tool_versions (a dict of tool name -> citation-site list, never a
    parsed version). `greenfield` is True iff the repo has no real project
    content at all yet (see _any_real_file_exists). `grounded_viable` is a
    dict keyed by GROUNDED_VIABLE_KINDS: each value depends only on
    whether that kind's own signals are present -- deliberately no count
    threshold, independent of count/classification above, per the
    proposal's evidence-gate design ("depends only on whether signals are
    present; there are no count thresholds")."""
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
    signals = {
        "formatter_config": _existing_top_level_names(repo_root, FORMATTER_CONFIG_FILENAMES),
        "linter_config": _existing_top_level_names(repo_root, LINTER_CONFIG_FILENAMES),
        "wrapper_scripts": _existing_top_level_names(repo_root, WRAPPER_SCRIPT_FILENAMES),
        "test_config": (
            _existing_top_level_names(repo_root, TEST_CONFIG_FILENAMES)
            + _probe_cmake_test_registration(repo_root)
        ),
        "ci": _probe_ci_config(repo_root),
        "contributing": _existing_top_level_names(repo_root, CONTRIBUTING_FILENAMES),
    }
    signals["tool_versions"] = _probe_tool_versions(repo_root, signals)
    greenfield = not _any_real_file_exists(repo_root)
    grounded_viable = {
        "coding_standards": bool(
            signals["formatter_config"] or signals["linter_config"] or signals["wrapper_scripts"]
        ),
        "testing_guidelines": bool(signals["test_config"]),
        "requirements_overview": not greenfield,
    }
    return {
        "substantive_modules": substantive,
        "count": count,
        "classification": classification,
        "signals": signals,
        "grounded_viable": grounded_viable,
        "greenfield": greenfield,
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
# Tier 0: orphaned CEP output detection (state-independent -- see            #
# ORPHANED_CEP_OUTPUT_GENERATED_BY's own comment for why this exists         #
# alongside, not instead of, _settled_output_subtrees()'s state-based check) #
# --------------------------------------------------------------------------- #

def _looks_like_orphaned_cep_output(path):
    """True if `path` is a text file whose frontmatter's `generated_by` key
    is exactly ORPHANED_CEP_OUTPUT_GENERATED_BY -- i.e. this skill wrote it,
    in any run, against any repo, tracked by any state file or none at all.
    Defensive like _read_first_line(): unreadable/binary/missing files are
    simply not a match, never a raised error, since this runs against
    arbitrary candidate-module files during scan()."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    frontmatter, _body = _parse_frontmatter(text)
    return frontmatter.get("generated_by") == ORPHANED_CEP_OUTPUT_GENERATED_BY


def _is_orphaned_cep_output_module(files):
    """Same "majority, not one stray file" shape as _is_generated_module()'s
    own file-suffix check, but content-sniffed rather than name-sniffed, and
    with no directory-name shortcut (a CEP output directory's name is
    whatever How-L2 resolved it to for that run -- e.g. "org", "docs",
    anything -- never a fixed, guessable pattern the way "generated"/"gen"
    is for vendor code)."""
    if not files:
        return False
    marked = sum(1 for f in files if _looks_like_orphaned_cep_output(f))
    return (marked / len(files)) >= GENERATED_FILE_MAJORITY_THRESHOLD


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


def _node_level_crossing_edges(graph, module_a, module_b):
    """Every node-level DEPENDENCY_RELATIONS edge whose two endpoints fall
    one in module_a and one in module_b (either direction), as (src_node,
    dst_node) node-dict pairs straight from the already-loaded graph -- no
    additional graph work, just a second pass over the same links list
    _graph_crossing_edges() already walked, this time keeping node identity
    instead of collapsing to the module-pair aggregate. On its own this is
    NOT a call-site citation -- see _interface_call_sites(), which uses this
    only to know which specific (file, symbol name) pairs are even worth a
    text search."""
    node_module = _node_module_map(graph)
    node_by_id = {n.get("id"): n for n in graph.get("nodes", [])}
    pair = frozenset((module_a, module_b))
    edges = []
    for link in graph.get("links", []):
        if link.get("relation") not in DEPENDENCY_RELATIONS:
            continue
        src_id, dst_id = link.get("source"), link.get("target")
        src_module, dst_module = node_module.get(src_id), node_module.get(dst_id)
        if not src_module or not dst_module or src_module == dst_module:
            continue
        if frozenset((src_module, dst_module)) != pair:
            continue
        src_node, dst_node = node_by_id.get(src_id), node_by_id.get(dst_id)
        if src_node is not None and dst_node is not None:
            edges.append((src_node, dst_node))
    return edges


def _interface_call_sites(repo_root, graph, module_a, module_b):
    """Best-effort "path:Lline" call-site citations for one interface
    pair, derived entirely from the already-loaded graph -- closes F18
    (Sec 1.2 R7) without re-running the graph indexer: graph.json's own
    links carry no reliable per-edge line number (every real consumer in
    this file already treats that as absent, see
    _compute_module_graph_evidence()'s docstring), so instead of trusting
    an unpopulated field this walks _node_level_crossing_edges() for the
    pair, and for each edge does a plain, deterministic text search of the
    edge's own SOURCE node's source_file for its TARGET node's own name --
    exactly _probe_tool_versions()'s established "citation index, not a
    parsed/verified match" posture (a needle found at a real line, never a
    guessed one, never a claim that the match IS the call expression itself
    rather than a textual mention of the target's name on that line).

    Returns a sorted, deduplicated list of "path:Lline" strings -- empty,
    honestly, when no crossing edge's target name is ever textually found
    in its source edge's file (e.g. a name too generic to have been
    written, or a source file this call can't read). Never raises on a
    missing/unreadable file -- that file is just skipped, same tolerance
    _probe_tool_versions() already applies."""
    repo_root = Path(repo_root)
    sites = set()
    file_lines_cache = {}
    for src_node, dst_node in _node_level_crossing_edges(graph, module_a, module_b):
        # Same "name" field with an id fallback that
        # _compute_module_graph_evidence()'s top_symbols_by_in_degree
        # already relies on (real graphify output doesn't always populate
        # "name" -- see that function's node.get("name") or node_id line).
        target_name = dst_node.get("name") or dst_node.get("id")
        source_file = src_node.get("source_file")
        if not target_name or not source_file:
            continue
        rel_path = source_file.replace("\\", "/")
        if rel_path not in file_lines_cache:
            try:
                text = (repo_root / rel_path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                file_lines_cache[rel_path] = None
            else:
                file_lines_cache[rel_path] = text.splitlines()
        lines = file_lines_cache[rel_path]
        if not lines:
            continue
        for line_no, line in enumerate(lines, start=1):
            if target_name in line:
                sites.add("{}:L{}".format(rel_path, line_no))
    return sorted(sites)


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


def _compute_module_graph_evidence(graph):
    """Per-module evidence derived once from a loaded graph.json, for
    `plan`/build_work_packets()'s evidence_hints and must_cite fields:

    - `depends_on` / `depended_on_by`: which OTHER modules this module's
      own nodes send/receive a DEPENDENCY_RELATIONS edge to/from.
      Direction-preserving, unlike _graph_crossing_edges()'s unordered
      module-PAIR aggregation that feeds state["interfaces"] -- that one
      deliberately loses direction (sorted(module_a, module_b)), so it
      can't answer "does lib/ depend on trantor/, or the reverse" on its
      own; this function re-walks the same links once more, per module,
      to keep that direction.
    - `top_symbols_by_in_degree` / `must_cite`: the module's own highest
      in-degree node(s) (by node-level, not module-level, in-degree),
      ranked, tie-broken by node id for determinism. `must_cite` is that
      single top node's own source_file (Sec 5.2's worked example:
      "lib/inc/example_pkg/TopLevelClass.h") when its in-degree is > 0,
      else empty -- never a guess when the graph shows no real fan-in.

    Returns {module_name: {"depends_on": [...], "depended_on_by": [...],
    "top_symbols_by_in_degree": [...], "must_cite": [...]}}. Every list is
    sorted/deterministic. Module names carry scan()'s own trailing "/"
    convention (Sec 5.2's "trantor/", "orm_lib/").

    Scope note -- Sec 5.2's evidence_hints.call_sites (a file:line citation
    of one specific cross-module call, e.g. "orm_lib/src/DbClient.cc:L96")
    is NOT produced here: this function only ever aggregates per-module
    fan-in/fan-out, it doesn't walk individual crossing edges. Populating
    call_sites for a specific interface PAIR is `list-interfaces
    --with-sites`'s job (see _interface_call_sites()), which this codebase
    treats as a distinct, later step -- Step 5d only reaches an interface
    pair once both endpoint modules already have a CONTEXT.md, so
    call-site evidence for it is naturally gathered then, not during this
    earlier per-module pass. Every packet still gets a `"call_sites": []`
    key here so the schema shape stays stable across hosts even when this
    function is the only evidence source consulted (e.g. a context_md
    packet, which has no interface pair to look sites up for at all).
    """
    node_module = _node_module_map(graph)
    node_by_id = {n.get("id"): n for n in graph.get("nodes", [])}

    node_in_degree = {}
    depends_on = {}
    depended_on_by = {}
    for link in graph.get("links", []):
        if link.get("relation") not in DEPENDENCY_RELATIONS:
            continue
        src_id, dst_id = link.get("source"), link.get("target")
        node_in_degree[dst_id] = node_in_degree.get(dst_id, 0) + 1
        src_module, dst_module = node_module.get(src_id), node_module.get(dst_id)
        if not src_module or not dst_module or src_module == dst_module:
            continue
        depends_on.setdefault(src_module, set()).add(dst_module)
        depended_on_by.setdefault(dst_module, set()).add(src_module)

    module_node_ids = {}
    for node_id, module_name in node_module.items():
        module_node_ids.setdefault(module_name, []).append(node_id)

    result = {}
    for module_name, node_ids in module_node_ids.items():
        ranked = sorted(node_ids, key=lambda nid: (-node_in_degree.get(nid, 0), nid))
        top_symbols = []
        for node_id in ranked[:3]:
            if node_in_degree.get(node_id, 0) <= 0:
                break
            node = node_by_id.get(node_id) or {}
            top_symbols.append(node.get("name") or node_id)

        must_cite = []
        if ranked and node_in_degree.get(ranked[0], 0) > 0:
            top_node = node_by_id.get(ranked[0]) or {}
            source_file = top_node.get("source_file")
            if source_file:
                must_cite = [source_file.replace("\\", "/")]

        result[module_name] = {
            "depends_on": sorted(m + "/" for m in depends_on.get(module_name, ())),
            "depended_on_by": sorted(m + "/" for m in depended_on_by.get(module_name, ())),
            "top_symbols_by_in_degree": top_symbols,
            "must_cite": must_cite,
        }
    return result


def _git_head_commit(repo_root):
    """HEAD commit sha for --repo-root, or None if it isn't a git repo, git
    itself isn't on PATH, or the call otherwise fails -- advisory
    provenance only (Sec 5.6's stale-packet table: "each packet records
    the HEAD commit"), never a hard requirement for `plan` to run at all.
    Same non-fatal-on-absence posture as this file's other environment
    probes (e.g. _probe_ci_config never requires CI to exist)."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def _normalize_posix_segments(path):
    """Lexically resolve `path` into a list of "/"-segments, collapsing
    "." and ".." the way a filesystem would -- WITHOUT touching the
    filesystem (output_path is a planned path that may not exist on disk
    yet, so there's nothing real to os.path.realpath()). A ".." that has
    nothing left to pop is kept as a literal segment (rather than
    silently dropped), so a path that tries to climb above its root still
    fails containment instead of being lexically erased into a false
    match."""
    parts = []
    for segment in path.replace("\\", "/").split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if parts and parts[-1] != "..":
                parts.pop()
            else:
                parts.append("..")
            continue
        parts.append(segment)
    return parts


def _path_is_contained(candidate, root):
    """True if "/"-joined relative path string `candidate` lexically
    resolves to somewhere at or under `root` (same convention). Segment-
    aware, not a plain string-prefix test -- a naive
    `candidate.startswith(root + "/")` would wrongly call
    "org/../evil/CONTEXT.md" contained under "org" (it IS that prefix,
    character for character) even though it actually escapes to
    "evil/CONTEXT.md". Resolving both sides into segments first closes
    that hole without needing the path to exist on disk."""
    candidate_parts = _normalize_posix_segments(candidate)
    root_parts = _normalize_posix_segments(root)
    return candidate_parts[:len(root_parts)] == root_parts


# --------------------------------------------------------------------------- #
# TASK-0303 (AutoScaffold_Mode_Plan.md Phase 3 / P1): content-mode           #
# resolution -- REQ-001's precedence chain, Sec 4.4's (layer, kind) cap      #
# matrix (F4/F15-corrected), and Sec 6.2's evidence gate. See TASK-0301's    #
# test classes (ContentModePrecedenceTests, DefaultModeByLayerTests,        #
# ContentModeCapMatrixTests, ContentModeEvidenceGateTests) for the full     #
# behavioral contract this implements.                                      #
# --------------------------------------------------------------------------- #

CONTENT_MODES = ("skeleton", "grounded", "augmented")
CONTENT_MODE_RANK = {mode: rank for rank, mode in enumerate(CONTENT_MODES)}

# Precedence level 4 (REQ-001): the per-kind default when no
# prompt/config/global value applies. Deliberately per-LAYER, not one flat
# constant -- TASK-0303's own wording ("Default What-L2 overview to
# skeleton") only makes sense that way. how_l2 (today's only implemented
# packet layer) keeps continuing pre-P1 behaviour (every how_l2 packet
# already shipped grounded content unconditionally); what_l2 has no
# packet-generation path in this release, so it defaults low rather than
# volunteering content for a layer that isn't built yet. Looked up with
# `.get(layer, "skeleton")` -- any future, not-yet-listed layer fails safe
# to the same conservative default as what_l2.
DEFAULT_MODE_BY_LAYER = {"how_l2": "grounded", "what_l2": "skeleton"}

# Sec 4.4's ceiling matrix, corrected by adversarial-review F4 (keyed on
# (layer, kind), not kind alone -- context_md means something different
# under how_l2 vs. what_l2) and F15 (the original proposal's "augmented,
# restricted" carve-out for CONTEXT.md/architecture-overview can't be
# linted/enforced, so v1 ships only these two pairs able to reach
# "augmented" at all). Any (layer, kind) pair not listed here -- including
# every what_l2 pair, whatever its kind -- caps at "grounded" via
# `_mode_cap()`'s `.get(..., "grounded")` default: v1 has no uncapped pair.
MODE_CAP_BY_LAYER_KIND = {
    ("how_l2", "coding_standards"): "augmented",
    ("how_l2", "testing_guidelines"): "augmented",
}


def _mode_cap(layer, kind):
    return MODE_CAP_BY_LAYER_KIND.get((layer, kind), "grounded")


def _kind_grounded_viable(kind, evidence):
    """True if `kind` has grounded-mode evidence, per probe_size()'s own
    `evidence` shape (`greenfield`, `grounded_viable` keyed by
    GROUNDED_VIABLE_KINDS) -- no adapter needed at the call site. Greenfield
    always wins (Sec 6.2: "greenfield downgrades every kind to skeleton"),
    even for a kind whose own `grounded_viable` entry happens to read True.
    A kind outside GROUNDED_VIABLE_KINDS (context_md, interface_boundary,
    architecture_overview) has no independent signal of its own -- it's
    evidenced by the module/interface's own existence, so it's viable
    whenever the repo isn't greenfield."""
    if evidence.get("greenfield"):
        return False
    per_kind = evidence.get("grounded_viable") or {}
    if kind in GROUNDED_VIABLE_KINDS:
        return bool(per_kind.get(kind))
    return True


def resolve_content_mode(kind, layer=PACKET_LAYER, *, prompt_override=None,
                          config_overrides=None, global_mode=None, evidence=None):
    """REQ-001's precedence chain for one (layer, kind) pair: explicit
    prompt override > per-(layer, kind) config override > the config's
    global `content_mode` > the per-layer default (DEFAULT_MODE_BY_LAYER).
    The winning value is then capped by Sec 4.4's (layer, kind) ceiling
    (MODE_CAP_BY_LAYER_KIND / `_mode_cap()`) and, unless `evidence` is
    omitted entirely (pre-P1 callers that haven't run probe_size() get no
    gate at all), collapsed to "skeleton" when Sec 6.2's evidence gate
    finds the kind isn't grounded-viable.

    Returns {"content_mode_requested": ..., "content_mode": ...,
    "mode_reason": str or None} -- `mode_reason` is set exactly when the
    cap or the evidence gate changed the requested value, explaining why.

    Raises ValueError if any of prompt_override, config_overrides[kind], or
    global_mode is given but isn't one of CONTENT_MODES -- validated before
    precedence is resolved, and scoped to only the entries relevant to this
    (layer, kind) call: an invalid value under a *different* kind's config
    override must not raise here."""
    config_overrides = config_overrides or {}
    kind_override = config_overrides.get(kind)
    for label, value in (
        ("prompt_override", prompt_override),
        ("config_overrides[{!r}]".format(kind), kind_override),
        ("global_mode", global_mode),
    ):
        if value is not None and value not in CONTENT_MODE_RANK:
            raise ValueError(
                "invalid content mode {!r} for {} -- must be one of {}".format(
                    value, label, CONTENT_MODES
                )
            )

    if prompt_override is not None:
        requested = prompt_override
    elif kind_override is not None:
        requested = kind_override
    elif global_mode is not None:
        requested = global_mode
    else:
        requested = DEFAULT_MODE_BY_LAYER.get(layer, "skeleton")

    effective = requested
    reason = None

    cap = _mode_cap(layer, kind)
    if CONTENT_MODE_RANK[effective] > CONTENT_MODE_RANK[cap]:
        effective = cap
        reason = "capped at {} ({}/{} ceiling, Sec 4.4)".format(cap, layer, kind)

    if evidence is not None and effective != "skeleton" and not _kind_grounded_viable(kind, evidence):
        effective = "skeleton"
        if evidence.get("greenfield"):
            reason = "downgraded to skeleton: repo is greenfield (Sec 6.2)"
        else:
            reason = (
                "downgraded to skeleton: no grounded-mode evidence for {} "
                "(Sec 6.2)".format(kind)
            )

    return {
        "content_mode_requested": requested,
        "content_mode": effective,
        "mode_reason": reason,
    }


def _make_packet(kind, packet_id, module_id, tier, output_path, must_cite,
                  evidence_hints, read_budget, head_commit, *,
                  prompt_override=None, config_overrides=None,
                  global_mode=None, evidence=None):
    """Assemble one Sec 5.2 work-packet dict from already-resolved,
    kind-specific inputs. Every schema field always present. `content_mode`
    (and `content_mode_requested`/`mode_reason` alongside it) comes from
    `resolve_content_mode()` (TASK-0303) -- callers that pass none of
    prompt_override/config_overrides/global_mode/evidence get exactly
    that function's own no-input default for `layer` (PACKET_LAYER here),
    which for how_l2 is "grounded", matching pre-P1 behaviour."""
    mode = resolve_content_mode(
        kind, PACKET_LAYER, prompt_override=prompt_override,
        config_overrides=config_overrides, global_mode=global_mode,
        evidence=evidence,
    )
    return {
        "packet_id": packet_id,
        "layer": PACKET_LAYER,
        "kind": kind,
        "module_id": module_id,
        "tier": tier,
        "output_path": output_path,
        "template": TEMPLATE_PATH_BY_KIND[kind],
        "content_mode_requested": mode["content_mode_requested"],
        "content_mode": mode["content_mode"],
        "mode_reason": mode["mode_reason"],
        "required_sections": list(REQUIRED_SECTIONS_BY_KIND[kind]),
        "probe_checklist_ref": PROBE_CHECKLIST_REF_BY_KIND[kind],
        "must_cite": list(must_cite),
        "evidence_hints": evidence_hints,
        "domain_pack": None,
        "validation_floor": dict(VALIDATION_FLOORS[(kind, tier)]),
        "read_budget": read_budget,
        "head_commit": head_commit,
    }


def build_work_packets(state, repo_root, how_l2_path, graph_path=None, *,
                        content_mode_prompt_override=None,
                        content_mode_config_overrides=None,
                        content_mode_global=None):
    """Sec 5.2: one work packet per pending How-L2 document `scan`/the
    repo-doc and interface trackers already selected (module status ==
    "pending" and tier in PACKET_ELIGIBLE_MODULE_TIERS; repo_docs[kind]
    status == "pending"; interface status == "pending").

    Read-only against `state` -- never mutates or saves it. `plan` is not
    a state-writing subcommand; the orchestrator remains state's only
    writer (Sec 5's core invariant) whether or not a `plan` run ever
    happens. Read-only against the filesystem too, except for the one-time
    graph.json load when `graph_path` is given -- this function never
    writes a packet file itself; that's `_cmd_plan`'s job, so this stays
    unit-testable with no disk I/O of its own beyond the graph read.

    Deterministic: same `state` + same `repo_root` + same `how_l2_path` +
    same `graph_path` always produces the same packet list in the same
    order (sorted by packet_id) -- Sec 5's "worker input is the same on
    every host" requirement starts here. The one input this can't control
    is `head_commit` (the live git HEAD) and, when `graph_path` differs in
    content between two calls, the evidence it carries -- both are meant
    to vary run-over-run; nothing else is.

    `graph_path` is optional: pass None for a heuristic-mode run (or a
    graphify run where the caller chooses not to feed the graph in) --
    every packet still gets a full evidence_hints shape via
    _EMPTY_EVIDENCE_HINTS and an empty must_cite for context_md packets in
    that case, never a guess.

    Raises ValueError if two packets would compute the same output_path,
    or if any output_path would resolve outside `how_l2_path` -- TASK-0104
    and Sec 5.6's containment/uniqueness refusal enforced here at build
    time, in addition to (never instead of) mark-*'s own later runtime
    check on the actual written file.

    TASK-0303: every packet's `content_mode`/`content_mode_requested`/
    `mode_reason` comes from `resolve_content_mode()`, fed this call's own
    `content_mode_prompt_override`/`content_mode_config_overrides`/
    `content_mode_global` (all optional; a caller passing none of them
    gets exactly resolve_content_mode()'s own how_l2 default, i.e. today's
    pre-P1 "grounded" behaviour) plus a fresh `probe_size(repo_root)`
    evidence read for the Sec 6.2 evidence gate -- greenfield or a kind
    lacking grounded-mode signals collapses that packet to "skeleton"
    regardless of what was requested.
    """
    repo_root = Path(repo_root)
    how_l2_path = how_l2_path.replace("\\", "/").rstrip("/")
    head_commit = _git_head_commit(repo_root)

    graph_evidence = {}
    if graph_path:
        graph_evidence = _compute_module_graph_evidence(_load_graph(graph_path))

    probe = probe_size(repo_root)
    signals = probe["signals"]
    content_mode_evidence = {
        "greenfield": probe["greenfield"],
        "grounded_viable": probe["grounded_viable"],
    }

    def _resolved_mode_kwargs():
        return dict(
            prompt_override=content_mode_prompt_override,
            config_overrides=content_mode_config_overrides,
            global_mode=content_mode_global,
            evidence=content_mode_evidence,
        )
    repo_doc_must_cite = {
        "coding_standards": sorted(set(
            signals["formatter_config"] + signals["linter_config"]
            + signals["wrapper_scripts"] + signals["ci"]
        )),
        "testing_guidelines": sorted(set(signals["test_config"])),
    }

    packets = []

    for module in state.get("modules", []):
        if module.get("status") != "pending":
            continue
        tier = module.get("tier")
        if tier not in PACKET_ELIGIBLE_MODULE_TIERS:
            continue
        module_name = module["id"].rstrip("/")
        evidence = graph_evidence.get(module_name, {})
        packets.append(_make_packet(
            kind="context_md",
            packet_id="{}--{}--{}".format(
                PACKET_LAYER_SLUG, module_name.replace("/", "-"),
                PACKET_KIND_SLUG["context_md"],
            ),
            module_id=module["id"],
            tier=tier,
            output_path="{}/{}/CONTEXT.md".format(how_l2_path, module_name),
            must_cite=evidence.get("must_cite", []),
            evidence_hints={
                "top_symbols_by_in_degree": evidence.get("top_symbols_by_in_degree", []),
                "depends_on": evidence.get("depends_on", []),
                "depended_on_by": evidence.get("depended_on_by", []),
                "call_sites": [],
            },
            read_budget=READ_BUDGET_BY_TIER[tier],
            head_commit=head_commit,
            **_resolved_mode_kwargs()
        ))

    repo_docs = state.get("repo_docs") or {}
    repo_doc_filename = {
        "coding_standards": "CODING-STANDARDS.md",
        "testing_guidelines": "TESTING-GUIDELINES.md",
    }
    for kind in REPO_DOC_KINDS:
        doc = repo_docs.get(kind) or {}
        if doc.get("status") != "pending":
            continue
        packets.append(_make_packet(
            kind=kind,
            packet_id="{}--{}".format(PACKET_LAYER_SLUG, PACKET_KIND_SLUG[kind]),
            module_id=None,
            tier=None,
            output_path="{}/{}".format(how_l2_path, repo_doc_filename[kind]),
            must_cite=repo_doc_must_cite[kind],
            evidence_hints=dict(_EMPTY_EVIDENCE_HINTS),
            read_budget=READ_BUDGET_REPO_DOC,
            head_commit=head_commit,
            **_resolved_mode_kwargs()
        ))

    for interface in state.get("interfaces", []):
        if interface.get("status") != "pending":
            continue
        module_a = interface["module_a"].rstrip("/")
        module_b = interface["module_b"].rstrip("/")
        packets.append(_make_packet(
            kind="interface_boundary",
            packet_id="{}--{}-to-{}--{}".format(
                PACKET_LAYER_SLUG, module_a.replace("/", "-"),
                module_b.replace("/", "-"), PACKET_KIND_SLUG["interface_boundary"],
            ),
            module_id=interface["id"],
            tier=None,
            output_path="{}/interfaces/{}-to-{}.md".format(
                how_l2_path, module_a, module_b
            ),
            must_cite=[],
            evidence_hints=dict(_EMPTY_EVIDENCE_HINTS),
            read_budget=READ_BUDGET_INTERFACE,
            head_commit=head_commit,
            **_resolved_mode_kwargs()
        ))

    packets.sort(key=lambda p: p["packet_id"])

    seen_output_paths = {}
    for packet in packets:
        prior_id = seen_output_paths.get(packet["output_path"])
        if prior_id is not None:
            raise ValueError(
                "duplicate output_path {!r} planned by both {!r} and {!r}".format(
                    packet["output_path"], prior_id, packet["packet_id"]
                )
            )
        seen_output_paths[packet["output_path"]] = packet["packet_id"]
        if not _path_is_contained(packet["output_path"], how_l2_path):
            raise ValueError(
                "packet {!r} output_path {!r} lies outside how_l2_path {!r}".format(
                    packet["packet_id"], packet["output_path"], how_l2_path
                )
            )

    return packets


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

def _tier_for_graph(in_degree, generated, node_count, file_count):
    if generated:
        return 0, "generated"
    # A module with zero graph nodes is not a real leaf (tier 3) -- graphify
    # found nothing under it to index at all. in_degree alone can't tell the
    # two apart: a genuine tier-3 leaf with plenty of its own nodes also has
    # in_degree 0, since nothing else imports it. node_count is the
    # distinguishing signal (see _graph_module_node_counts()). Checked
    # before the thresholds below so it never gets miscounted as a normal,
    # selectable tier-3 module.
    #
    # Zero graph nodes does NOT by itself mean the directory is empty,
    # though -- a directory of non-code assets graphify doesn't traverse, or
    # one graphify simply never walked, still has real files under it and is
    # still a legitimate module candidate. Fall back to heuristic mode's own
    # file_count signal there rather than dropping the module from the
    # list entirely, tagged with its own basis string so the state file
    # records that this tier came from a graph-mode fallback rather than
    # from a real graphify signal or from a full heuristic-mode run. Only
    # zero nodes AND zero files is genuinely empty.
    if node_count == 0:
        if file_count == 0:
            return None, "empty"
        tier, _heuristic_basis = _tier_for_heuristic(file_count, generated)
        return tier, "heuristic:file-count (no graph nodes)"
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
        "index": {"output_path": None, "rendered_at": None},
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
    state.setdefault("index", {"output_path": None, "rendered_at": None})
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
        "index": state.get("index") or {"output_path": None, "rendered_at": None},
    }
    aaw.write_text_atomic(path, json.dumps(ordered, indent=2) + "\n")


class StateLockError(Exception):
    """Raised by `state_lock()` when the lock is already held by another
    writer. Sec 9.3's defense-in-depth against the single-writer rule ever
    being violated -- the orchestrator is the only intended caller of any
    mutating command, but a lock file (`TRIAGE-STATE.json.lock`, created with
    O_EXCL) catches it in practice if that rule is ever broken (two
    orchestrator processes, a hung retry, etc.)."""


def _lock_path_for(state_path):
    return Path(str(state_path) + ".lock")


def _is_stale(lock_path, stale_after_seconds):
    try:
        age = time.time() - lock_path.stat().st_mtime
    except OSError:
        # Lock disappeared between the caller checking existence and this
        # stat -- treat as "not stale", the retry loop in state_lock() will
        # just try to create it fresh next.
        return False
    return age > stale_after_seconds


@contextlib.contextmanager
def state_lock(state_path, stale_after_seconds=120):
    """Exclusive file lock guarding a load-mutate-save cycle against
    `TRIAGE-STATE.json`, per Sec 9.3: "A file lock (`TRIAGE-STATE.json.lock`,
    created with `O_EXCL` and cleaned up if stale) protects the whole-file
    rewrite in case an orchestrator ever violates the single-writer rule."

    A lock older than `stale_after_seconds` is assumed abandoned (a crashed
    process never cleaned up after itself) and is removed before a single
    retry; a live concurrent holder within that window raises
    `StateLockError` rather than blocking, since this is meant to catch a
    single-writer-rule violation, not to serialize legitimate concurrent
    writers with a wait queue."""
    lock_path = _lock_path_for(state_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = None
    for attempt in range(2):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if attempt == 0 and _is_stale(lock_path, stale_after_seconds):
                try:
                    lock_path.unlink()
                except OSError:
                    pass
                continue
            raise StateLockError(
                "state lock '{}' is already held -- another writer is "
                "mid-write, or a prior run crashed without cleaning up "
                "(lock is not yet stale by the {}s threshold)".format(
                    lock_path, stale_after_seconds
                )
            )
    try:
        os.close(fd)
        yield
    finally:
        try:
            lock_path.unlink()
        except OSError:
            pass


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
    settled_output_subtrees = _settled_output_subtrees(repo_root, state)
    # Purity-filtered, NOT the raw _settled_output_root_names() key set: a
    # name only gets excluded/dropped wholesale below when its top-level
    # directory holds nothing but known settled output. A name that also
    # holds real, unrelated content stays a normal scan candidate -- see
    # _directory_is_purely_settled_output()'s own docstring for why.
    settled_output_roots = {
        name
        for name, subtrees in settled_output_subtrees.items()
        if _directory_is_purely_settled_output(repo_root / name, subtrees)
    }
    module_names = [
        n for n in _top_level_candidate_dirs(repo_root) if n not in settled_output_roots
    ]

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
        # name only reaches settled_output_subtrees when it wasn't pure
        # enough to be excluded outright above -- prune the specific known
        # settled-output subtree(s)/file(s) here instead, so this module's
        # own tiering is based on its real content, not inflated or
        # otherwise skewed by CEP's own generated files sitting inside it.
        known = settled_output_subtrees.get(name)
        if known:
            known_dirs = known.get("dirs", set())
            known_files = known.get("files", set())
            files = [
                f for f in files
                if f.resolve() not in known_files
                and not any(d in f.resolve().parents for d in known_dirs)
            ]
        generated = _is_generated_module(module_path, files)
        # Only worth the content-read cost when the cheaper name/suffix
        # check above didn't already decide tier 0 -- and only meaningful
        # to distinguish in skip_reason wording, since both bases feed the
        # same tier-0/auto-skip outcome below.
        orphaned_cep_output = False if generated else _is_orphaned_cep_output_module(files)

        if graph_mode == "graphify":
            in_degree = in_degrees.get(name, 0)
            node_count = node_counts.get(name, 0)
            tier, basis = _tier_for_graph(
                in_degree, generated or orphaned_cep_output, node_count, len(files)
            )
        else:
            in_degree = None
            tier, basis = _tier_for_heuristic(len(files), generated or orphaned_cep_output)

        if tier == 0 and orphaned_cep_output:
            skip_reason = (
                "orphaned CEP-generated output from a prior run, not tracked "
                "by this state file (auto-detected via generated_by "
                "frontmatter)"
            )
        elif tier == 0:
            skip_reason = "generated/vendor code (auto-detected)"
        elif tier is None:
            # Distinct wording from the tier-0 case above so "why was this
            # skipped" stays answerable at a glance -- generated/vendor and
            # empty are different reasons a module never became selectable.
            skip_reason = (
                "empty directory (no files and no graph nodes found under it)"
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
    # record of decisions made, not a live filesystem mirror. The one
    # exception: a still-"pending" entry whose name is itself a settled
    # output root (this exact reclassification bug, if it already ran once
    # against an older build of this file before this fix existed) carries
    # no real decision to preserve -- a "generated"/"skipped" entry always
    # is preserved, but a lingering mistaken "pending" one is dropped here
    # instead of being carried forward forever.
    for module_id, entry in existing.items():
        if module_id in seen_ids:
            continue
        name = module_id[:-1] if module_id.endswith("/") else module_id
        if entry.get("status") == "pending" and name in settled_output_roots:
            continue
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


# --------------------------------------------------------------------------- #
# TASK-0106: validate() -- Sec 6's P0a validator table.                      #
#                                                                             #
# Read-only: takes a path a worker claims to have written plus the packet    #
# that requested it, and returns {"valid": bool, "failures": [str, ...]}.    #
# Never mutates state or the file. This is the shared function `validate`    #
# (the CLI dry run) and every `mark_*_generated` path (TASK-0106's second    #
# half, still pending) call before flipping status to "generated" -- the     #
# check that would have caught Sec 1.1's incident (Tier-3 modules            #
# and a one-sentence CODING-STANDARDS.md both marked generated with nothing  #
# behind them).                                                              #
#                                                                             #
# Explicitly OUT of scope here (a deliberate, already-recorded scoping        #
# decision): external-block validation (augmented mode, P2) and               #
# skeleton byte-identity validation (P1) -- both added when those content     #
# modes' contracts actually land.                                           #
# --------------------------------------------------------------------------- #

REQUIRED_FRONTMATTER_KEYS = (
    "generated_by", "generated_at", "status", "content_mode", "doc_kind",
    "skill_version",
)

# "[src: path#Lx-Ly]" or the single-line form "[src: path#Lx]" -- Sec 7's
# worked example uses both. Path is everything up to the "#", trimmed.
_CITATION_RE = re.compile(r"\[src:\s*([^\]#]+?)#L(\d+)(?:-L(\d+))?\]")

# "Not evidenced. Searched: <items>" -- Sec 4.1's grounded-mode gap
# language. Items are comma-separated; each ends "(absent)" per the same
# section's convention. Only the "(absent)"-tagged items are a checkable
# absence claim; free text around them is not parsed further.
_GAP_LINE_RE = re.compile(r"Not evidenced\.\s*Searched:\s*(.+)")
_GAP_ITEM_RE = re.compile(r"^\s*(.+?)\s*\(absent\)\.?\s*$")

_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")


def _parse_frontmatter(text):
    """Split a "---"-delimited key: value frontmatter block off the front
    of `text`. Returns (frontmatter_dict, body_text). frontmatter_dict is
    {} (not None) when there's no opening "---" on line 1 or no closing
    "---" -- callers treat a missing/malformed block as "every required
    key absent", which is exactly what the Frontmatter check should report
    rather than raising."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    frontmatter = {}
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
        if ":" in lines[i]:
            key, _, value = lines[i].partition(":")
            frontmatter[key.strip()] = value.strip()
    if end is None:
        return {}, text
    body = "\n".join(lines[end + 1:])
    return frontmatter, body


def _extract_sections(body):
    """Map heading text -> body text (everything up to the next "##"
    heading or end of document) for every level-2 "## Heading" block."""
    lines = body.split("\n")
    headings = []
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m:
            headings.append((i, m.group(1)))
    sections = {}
    for idx, (line_no, heading) in enumerate(headings):
        start = line_no + 1
        stop = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
        sections[heading] = "\n".join(lines[start:stop]).strip()
    return sections


# TASK-0304 (P1): Sec 4.1's `skeleton` contract -- a deterministic,
# no-LLM rendering of a kind's own template, with every required_sections
# heading and its guidance comment kept verbatim and only one visible
# placeholder line substituted per section. No claim about the repo
# beyond the mechanical facts the packet itself already states (module
# path/name, or the two module names of an interface_boundary packet).
_SKELETON_NOT_WRITTEN_LINE = "_Not written yet — see guidance in source._"
_LEADING_COMMENT_RE = re.compile(r"\A(<!--.*?-->)", re.DOTALL)


def _skill_root():
    """Directory one level above this file (scripts/) -- this skill's own
    installation root, where templates/ and SKILL.md live. Used only to
    read this skill's own template files; everything about the *target*
    repo comes from `packet`, never from here."""
    return Path(__file__).resolve().parent.parent


def _read_skill_version():
    """This skill's own `version:` frontmatter field from SKILL.md, read
    fresh every call rather than hardcoded, so emit_skeleton()'s default
    never drifts from a bumped SKILL.md version the way a copy-pasted
    constant would. Falls back to "unknown" if SKILL.md is missing or has
    no version key -- never raises."""
    skill_md = _skill_root() / "SKILL.md"
    if not skill_md.is_file():
        return "unknown"
    frontmatter, _body = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    return frontmatter.get("version") or "unknown"


def _split_interface_module_id(module_id):
    """Inverse of build_work_packets()'s "{module_a}--{module_b}" join for
    an interface_boundary packet's module_id -- left-split on the first
    "--", the same "module names never contain --" assumption that join
    itself already makes silently. There is no separate module_a/module_b
    field on the packet, only this combined id."""
    module_a, _sep, module_b = module_id.partition("--")
    return module_a, module_b


def emit_skeleton(packet, *, generated_at=None, skill_version=None):
    """Sec 4.1's `skeleton` contract, produced deterministically with no
    LLM: this skill's own template for `packet["kind"]`, every
    required_sections heading kept together with its own guidance comment
    verbatim (sections outside required_sections, e.g. context_md's
    conditional "State machine (if applicable)", are omitted entirely --
    skeleton mode has no evidence to decide whether a conditional section
    even applies), each section's placeholder body replaced by one visible
    "_Not written yet -- see guidance in source._" line, and only
    mechanical facts already present on `packet` substituted into the
    header (module path/name, or both module names for an
    interface_boundary packet). Raises ValueError if the template is
    missing a heading `packet["required_sections"]` names -- a template/
    packet mismatch bug, not a runtime data problem."""
    if generated_at is None:
        generated_at = _now_iso()
    if skill_version is None:
        skill_version = _read_skill_version()

    template_path = _skill_root() / packet["template"]
    text = template_path.read_text(encoding="utf-8")

    replacements = {
        "<YYYY-MM-DD>": generated_at,
        "<content-mode>": "skeleton",
        "<skill-version>": skill_version,
    }
    if packet["kind"] == "interface_boundary":
        module_a, module_b = _split_interface_module_id(packet["module_id"])
        replacements["<module-a>"] = module_a
        replacements["<module-b>"] = module_b
    elif packet.get("module_id"):
        module_path = packet["module_id"].rstrip("/")
        replacements["<module-path>"] = module_path
        replacements["<module-name>"] = module_path.rsplit("/", 1)[-1]
    for token, value in replacements.items():
        text = text.replace(token, value)

    frontmatter, body = _parse_frontmatter(text)
    frontmatter_block = "\n".join(
        ["---"] + ["{}: {}".format(k, v) for k, v in frontmatter.items()] + ["---"]
    )

    body_lines = body.split("\n")
    first_heading_idx = len(body_lines)
    for i, line in enumerate(body_lines):
        if _HEADING_RE.match(line):
            first_heading_idx = i
            break
    header_block = "\n".join(body_lines[:first_heading_idx]).strip("\n")

    sections = _extract_sections(body)
    required = packet["required_sections"]
    missing = [h for h in required if h not in sections]
    if missing:
        raise ValueError(
            "template {} is missing required section(s) {!r} named by "
            "REQUIRED_SECTIONS_BY_KIND[{!r}]".format(
                packet["template"], missing, packet["kind"]
            )
        )

    blocks = [header_block]
    for heading, raw in sections.items():
        if heading not in required:
            continue
        comment_match = _LEADING_COMMENT_RE.match(raw)
        section_lines = ["## " + heading]
        if comment_match:
            section_lines.append("")
            section_lines.append(comment_match.group(1))
        section_lines.append("")
        section_lines.append(_SKELETON_NOT_WRITTEN_LINE)
        blocks.append("\n".join(section_lines))

    body_text = "\n\n".join(blocks).rstrip("\n") + "\n"
    return frontmatter_block + "\n\n" + body_text


def _stale_head_warnings(repo_root, packet):
    """Sec 6 risk-table's advisory-only "packet HEAD differs from repo
    HEAD" warning (proposal: "Packets go stale mid-run (the code changes)
    | Each packet records the HEAD commit. mark-* warns if HEAD has
    changed since the packet was created."), shared by both validate()'s
    normal path and its skeleton-mode early return."""
    warnings = []
    packet_head = packet.get("head_commit")
    if packet_head:
        current_head = _git_head_commit(repo_root)
        if current_head and current_head != packet_head:
            warnings.append(
                "packet HEAD '{}' differs from current HEAD '{}' -- repo "
                "changed since this packet was created".format(packet_head, current_head)
            )
    return warnings


def validate(repo_root, path, packet):
    """Sec 6's P0a validator table, run against the file at `repo_root /
    path` for the given work packet. Returns
    {"valid": bool, "failures": [str, ...]} and never touches the
    filesystem beyond reading."""
    repo_root = Path(repo_root)
    failures = []

    if path != packet["output_path"]:
        failures.append(
            "output_path mismatch: validated path '{}' does not match "
            "packet output_path '{}'".format(path, packet["output_path"])
        )

    full_path = repo_root / path
    if not full_path.is_file():
        failures.append("file does not exist: {}".format(path))
        return {"valid": False, "failures": failures, "warnings": []}

    text = full_path.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(text)

    for key in REQUIRED_FRONTMATTER_KEYS:
        if not frontmatter.get(key):
            failures.append("frontmatter missing or empty required key: {}".format(key))

    if frontmatter.get("status") not in (None, "") and frontmatter.get("status") != "draft":
        failures.append(
            "frontmatter status must be 'draft', got '{}'".format(frontmatter.get("status"))
        )

    content_mode = frontmatter.get("content_mode")
    if content_mode and content_mode != packet["content_mode"]:
        failures.append(
            "frontmatter content_mode '{}' does not match packet content_mode "
            "'{}'".format(content_mode, packet["content_mode"])
        )

    doc_kind = frontmatter.get("doc_kind")
    if doc_kind and doc_kind != packet["kind"]:
        failures.append(
            "frontmatter doc_kind '{}' does not match packet kind '{}'".format(
                doc_kind, packet["kind"]
            )
        )

    # TASK-0304 (P1): Sec 6's "Skeleton" row -- for content_mode: skeleton,
    # byte identity with emit_skeleton()'s own output (generated_at pinned
    # to this file's own value, the one field the contract allows to vary)
    # is the sole content-correctness gate. The evidence-shaped checks
    # below (Sections/Must-cite/Citation resolution/Gap honesty/Floor/
    # Conflicts) are built around citations and gap lines a mechanically-
    # generated skeleton document can never contain -- applying them here
    # would fail every skeleton document unconditionally, so they don't
    # run for this mode. Existence and the frontmatter checks above still
    # run first, for better diagnostics on a badly mangled file.
    if packet["content_mode"] == "skeleton":
        try:
            expected = emit_skeleton(packet, generated_at=frontmatter.get("generated_at"))
        except (OSError, ValueError) as e:
            failures.append("could not compute expected skeleton output: {}".format(e))
            expected = None
        if expected is not None:
            # \r\n -> \n only (cross-platform line-ending tolerance,
            # matching this codebase's existing posture elsewhere) --
            # deliberately NOT also stripping trailing whitespace per line
            # the way _normalized_body_hash() does, since exact content
            # fidelity is the actual point of a byte-identity check.
            actual_norm = text.replace("\r\n", "\n")
            expected_norm = expected.replace("\r\n", "\n")
            if actual_norm != expected_norm:
                failures.append(
                    "content_mode is 'skeleton' but the file is not "
                    "byte-identical to the deterministic emit-skeleton "
                    "output for this packet (excluding generated_at)"
                )
        return {
            "valid": len(failures) == 0,
            "failures": failures,
            "warnings": _stale_head_warnings(repo_root, packet),
        }

    sections = _extract_sections(body)
    for heading in packet["required_sections"]:
        section_body = sections.get(heading)
        if section_body is None:
            failures.append("missing required section: {}".format(heading))
            continue
        has_citation = bool(_CITATION_RE.search(section_body))
        has_gap = bool(_GAP_LINE_RE.search(section_body))
        if not section_body or (not has_citation and not has_gap):
            failures.append(
                "section '{}' has no evidenced content or gap line".format(heading)
            )

    citations = []  # (path, line_start, line_end)
    for m in _CITATION_RE.finditer(body):
        cite_path = m.group(1).strip()
        line_start = int(m.group(2))
        line_end = int(m.group(3)) if m.group(3) else line_start
        citations.append((cite_path, line_start, line_end))

    cited_paths = {c[0] for c in citations}
    for must in packet["must_cite"]:
        if must not in cited_paths:
            failures.append("must_cite path not cited: {}".format(must))

    resolved_files = set()
    for cite_path, line_start, line_end in citations:
        if cite_path in _LITERAL_MUST_CITE_MARKERS:
            # A literal marker string, not a real path -- must_cite's
            # presence check above already covers it; it names no file to
            # resolve and contributes nothing to min_distinct_cited_files.
            continue
        cite_full = repo_root / cite_path
        if not cite_full.is_file():
            failures.append(
                "citation path does not exist: {} (cited as [src: {}#L{}-L{}])".format(
                    cite_path, cite_path, line_start, line_end
                )
            )
            continue
        n_lines = len(cite_full.read_text(encoding="utf-8").splitlines())
        if line_start < 1 or line_end < line_start or line_end > n_lines:
            failures.append(
                "citation line range out of bounds: {}#L{}-L{} (file has {} "
                "lines)".format(cite_path, line_start, line_end, n_lines)
            )
            continue
        resolved_files.add(cite_path)

    for gap_match in _GAP_LINE_RE.finditer(body):
        for item in gap_match.group(1).split(","):
            item_match = _GAP_ITEM_RE.match(item)
            if not item_match:
                continue
            claimed_path = item_match.group(1).strip()
            if (repo_root / claimed_path).exists():
                failures.append(
                    "gap claims absence but file exists: {}".format(claimed_path)
                )

    floor = packet.get("validation_floor") or {}
    min_files = floor.get("min_distinct_cited_files")
    if min_files is not None and len(resolved_files) < min_files:
        failures.append(
            "fewer than {} distinct cited files ({})".format(min_files, len(resolved_files))
        )
    min_bytes = floor.get("min_body_bytes")
    body_bytes = len(body.encode("utf-8"))
    if min_bytes is not None and body_bytes < min_bytes:
        failures.append(
            "body is smaller than {} bytes ({})".format(min_bytes, body_bytes)
        )

    # Conflicts: coding_standards packets only -- _probe_tool_versions()
    # indexes WHERE a tool is discussed, never a parsed version value, so
    # true semantic disagreement isn't computable from probe data. The
    # conservative, documented proxy: a tool cited from 2+ distinct source
    # files requires an explicit "Conflicting evidence:" line somewhere in
    # the doc (Sec 7's exact marker string). Over-inclusive by design --
    # floors are a floor, not proof of quality.
    if packet["kind"] == "coding_standards":
        signals = probe_size(repo_root)["signals"]
        for tool, sites in signals.get("tool_versions", {}).items():
            distinct_sources = {site.split(":L")[0] for site in sites}
            if len(distinct_sources) > 1 and "Conflicting evidence:" not in body:
                failures.append(
                    "possible {} disagreement across {} but no 'Conflicting "
                    "evidence:' line found".format(tool, sorted(distinct_sources))
                )

    return {
        "valid": len(failures) == 0,
        "failures": failures,
        "warnings": _stale_head_warnings(repo_root, packet),
    }


def _normalized_body_hash(full_path):
    """sha256 of the document BODY only (frontmatter stripped), with line
    endings normalized to "\\n" and trailing whitespace stripped per line
    (Sec 9.3's "normalized LF/trailing-whitespace/body-only hashing") --
    so a re-render that only changes the frontmatter timestamp or line
    endings doesn't look like new content to output_sha256/previous_sha256
    comparisons (TASK-0108's staleness check)."""
    text = full_path.read_text(encoding="utf-8")
    _frontmatter, body = _parse_frontmatter(text)
    normalized = "\n".join(
        line.rstrip() for line in body.replace("\r\n", "\n").split("\n")
    ).strip("\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _record_validation_or_raise(record, validation_result, accept_validation_failure,
                                 packet, subject_label, final=False):
    """Shared by every mark_*_generated function once a packet was
    supplied: stamp `record` with the v2 validation/provenance fields
    (Sec 9.3) and enforce Sec 5.4's worker result contract. Returns the
    outcome string (`"passed"` / `"bypassed"` / `"failed"`) so the caller
    knows whether to still transition to `generated`.

    `final` distinguishes the two failure cases Sec 5.4 describes: a first
    failed attempt (final=False, the default) blocks outright and persists
    nothing, leaving the record `pending` for the orchestrator's one retry;
    a failure on that retry (final=True) is instead persisted as
    `status: "failed"` -- never silently promoted to `generated`. A bypass
    reason always wins over `final` either way. `subject_label` only
    appears in the raised message."""
    if not validation_result["valid"] and not accept_validation_failure and not final:
        raise ValueError(
            "{} failed validation and no --accept-validation-failure reason "
            "was given: {}".format(
                subject_label, "; ".join(validation_result["failures"])
            )
        )
    record["packet_id"] = packet["packet_id"]
    warnings = validation_result.get("warnings") or []
    if validation_result["valid"]:
        record["validation"] = {"status": "passed", "reasons": []}
        outcome = "passed"
    elif accept_validation_failure:
        record["validation"] = {
            "status": "bypassed",
            "reasons": validation_result["failures"],
            "bypass_reason": accept_validation_failure,
        }
        outcome = "bypassed"
    else:
        # final=True, no bypass reason: retry exhausted -- persist the
        # failure rather than raising, per Sec 5.4's third outcome.
        record["validation"] = {"status": "failed", "reasons": validation_result["failures"]}
        outcome = "failed"
    if warnings:
        record["validation"]["warnings"] = warnings
    return outcome


def mark_generated(state, module_id, output_path, packet=None, repo_root=None,
                    accept_validation_failure=None, final=False):
    """`packet`/`repo_root` are optional at the function level (existing
    direct callers/tests that predate the v2 work-packet model keep
    working unvalidated), but the CLI's `mark-generated` command -- the
    actual path the orchestrator uses -- makes both required, so every
    real mark-generated call is validated per the standing "every mark-*
    path must validate" instruction.

    `final=True` is the orchestrator's one retry: a failure there is
    persisted as `status: "failed"` instead of raising (Sec 5.4's third
    outcome), never silently promoted to `generated`."""
    module = _find_module(state, module_id)
    if module["status"] != "pending":
        raise ValueError(
            "module '{}' is already '{}' -- not pending".format(module_id, module["status"])
        )
    if packet is not None:
        result = validate(repo_root, output_path, packet)
        outcome = _record_validation_or_raise(
            module, result, accept_validation_failure, packet,
            "module '{}'".format(module_id), final=final,
        )
        if outcome == "failed":
            module["status"] = "failed"
            module["output_path"] = output_path
            module["generated_at"] = _now_iso()
            return module
        module["previous_sha256"] = module.get("output_sha256")
        module["output_sha256"] = _normalized_body_hash(Path(repo_root) / output_path)
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


def mark_repo_doc_generated(state, kind, output_path, packet=None, repo_root=None,
                             accept_validation_failure=None, final=False):
    doc = _find_repo_doc(state, kind)
    if doc["status"] != "pending":
        raise ValueError(
            "repo doc '{}' is already '{}' -- not pending".format(kind, doc["status"])
        )
    if packet is not None:
        result = validate(repo_root, output_path, packet)
        outcome = _record_validation_or_raise(
            doc, result, accept_validation_failure, packet,
            "repo doc '{}'".format(kind), final=final,
        )
        if outcome == "failed":
            doc["status"] = "failed"
            doc["output_path"] = output_path
            doc["generated_at"] = _now_iso()
            return doc
        doc["previous_sha256"] = doc.get("output_sha256")
        doc["output_sha256"] = _normalized_body_hash(Path(repo_root) / output_path)
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


def mark_index_rendered(state, output_path):
    """Record where `render-index` last wrote CEP-INDEX.md.

    Unlike a module or repo doc, the router file has no pending/generated
    lifecycle to gate -- SKILL.md Step 5b calls `render-index` again after
    every single module, deliberately overwriting the same path each time
    so the checkpoint stays current mid-run. So this just always records
    the latest path, with no "already generated" guard. Without recording
    it at all, the settled-output-root purity check in `scan()` never
    learns that CEP-INDEX.md exists on disk under a resolved How-L2 output
    root, and reports that root as impure (real, unaccounted-for content)
    on the very next scan -- reclassifying CEP's own router file as if it
    were unscanned application code."""
    state["index"] = {"output_path": output_path, "rendered_at": _now_iso()}
    return state["index"]


def mark_interface_generated(state, interface_id, output_path, packet=None, repo_root=None,
                              accept_validation_failure=None, final=False):
    interface = _find_interface(state, interface_id)
    if interface["status"] != "pending":
        raise ValueError(
            "interface '{}' is already '{}' -- not pending".format(
                interface_id, interface["status"]
            )
        )
    if packet is not None:
        result = validate(repo_root, output_path, packet)
        outcome = _record_validation_or_raise(
            interface, result, accept_validation_failure, packet,
            "interface '{}'".format(interface_id), final=final,
        )
        if outcome == "failed":
            interface["status"] = "failed"
            interface["output_path"] = output_path
            interface["generated_at"] = _now_iso()
            return interface
        interface["previous_sha256"] = interface.get("output_sha256")
        interface["output_sha256"] = _normalized_body_hash(Path(repo_root) / output_path)
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


def list_interfaces(state, eligible_only=False, generated_module_ids=None,
                     with_sites=False, repo_root=None, graph=None):
    """Return the interfaces list, optionally filtered to SKILL.md Step 5d's
    eligibility rule: status == "pending" AND both endpoint modules have
    reached a SETTLED state in this same state -- "generated" (tier 1/2,
    a context_md packet was actually produced), OR "skipped" AND tier == 3
    (a tier-3 leaf, which by design at PACKET_ELIGIBLE_MODULE_TIERS never
    gets a context_md packet at all and goes straight from "pending" to
    "skipped" -- see plan()'s own tier filter). Without the tier-3 case, a
    crossing edge touching ANY tier-3 endpoint could never become eligible
    under a clean run: the endpoint would never reach "generated", full
    stop, no matter how long the run went on -- a structural deadlock, not
    a "not yet" state. A tier-3 leaf is real, tiered application code (scan()
    already distinguished it from the genuinely-empty and
    generated/vendor-code cases, which also end at "skipped" but are
    deliberately EXCLUDED here by the explicit tier == 3 check -- neither
    of those ever has a meaningful interface to document, and this must not
    accidentally start treating them as eligible endpoints too); it is only
    "skipped" as in "no per-module doc was ever planned for it", not as in
    "there was nothing here". This is a widening of what "settled" means
    for interface-eligibility purposes only -- it changes no module's own
    tier, status, or packet eligibility.

    generated_module_ids defaults to computing itself from state["modules"]
    when not supplied -- callers that already have the module list handy
    (e.g. a single CLI invocation that just loaded state once) may pass it
    to avoid a second pass; the CLI entry point relies on the default. The
    parameter name predates the tier-3 widening above and is kept for
    backward compatibility, but it now means "settled enough to count as an
    interface endpoint", not literally "status == generated".

    with_sites=True adds a "call_sites" key (Sec 5.2's
    evidence_hints.call_sites shape) to every returned entry, via
    _interface_call_sites() against the already-loaded graph -- no
    additional graph work beyond what the caller already loaded. Requires
    repo_root and graph both given; the CLI entry point enforces that
    pairing before calling in with with_sites=True -- this function itself
    just needs both present to do the lookup, and returns entries with no
    "call_sites" key at all when with_sites is False, so callers that never
    asked for sites see the exact same shape as before this flag existed."""
    interfaces = state.get("interfaces", [])
    if not eligible_only:
        result = interfaces
    else:
        if generated_module_ids is None:
            generated_module_ids = {
                m["id"] for m in state.get("modules", [])
                if m["status"] == "generated"
                or (m["status"] == "skipped" and m.get("tier") == 3)
            }
        result = [
            i
            for i in interfaces
            if i["status"] == "pending"
            and (i["module_a"] + "/") in generated_module_ids
            and (i["module_b"] + "/") in generated_module_ids
        ]

    if not with_sites:
        return result

    with_sites_result = []
    for i in result:
        entry = dict(i)
        entry["call_sites"] = _interface_call_sites(
            repo_root, graph, i["module_a"], i["module_b"]
        )
        with_sites_result.append(entry)
    return with_sites_result


# --------------------------------------------------------------------------- #
# Layout slot resolution for render-index's --out (TASK-0110/0111)           #
# --------------------------------------------------------------------------- #
#
# render-index's --out must land at the *resolved* ult-repo-layout slot for
# `autoscaffold_content_index` -- writing CEP-INDEX.md anywhere else would let
# the router file drift out of the one location ult-repo-layout and every
# other skill know to look for it. The algorithm below is a deliberately
# minimal, scoped duplicate of ult-repo-layout's `validate_layout.py`
# (marker lookup via `.layout-slots.yaml`, else `context-config.yaml`'s
# `layout.workspace_root`-relative default, else the hardcoded pre-D21
# default) -- duplicated rather than cross-imported, per this codebase's
# established precedent (see autoscaffold_atomic_write.py's module docstring
# for the same rationale): ult-autoscaffold-content must stay usable
# standalone, without a hard dependency on ult-repo-layout being installed.
#
# Scoped to exactly the one slot this skill owns
# (`autoscaffold_content_index`, SLOT_REGISTRY's entry in
# ult-repo-layout/scripts/validate_layout.py) -- this is NOT a general-purpose
# slot resolver and must never grow into one; a real general resolver belongs
# in ult-repo-layout, not here. If either file's real on-disk schema (the
# block-YAML subset, the marker `slots:` list shape) ever changes, this copy
# and validate_layout.py's must be updated together, or the two skills will
# silently resolve the same slot to different paths -- exactly the class of
# bug this enforcement exists to prevent.

_CONTENT_INDEX_SLOT = "autoscaffold_content_index"
_CONTENT_INDEX_DEFAULT = "starter_kit/autoscaffold-content/CEP-INDEX.md"
_CONTENT_INDEX_WORKSPACE_ROOT_LEAF = "cache/autoscaffold-content/CEP-INDEX.md"
_LAYOUT_IGNORED_DIR_NAMES = {".git", "__pycache__", "node_modules", ".venv"}


class ContentIndexSlotError(ValueError):
    """Raised by `_resolve_content_index_slot_path` when the slot cannot be
    unambiguously resolved -- more than one `.layout-slots.yaml` marker
    claims `autoscaffold_content_index` (a bijectivity violation
    ult-repo-layout's own `validate_layout.py validate` is the authority on).
    render-index refuses to guess rather than pick one silently."""


def _layout_parse_scalar(s):
    """Same scalar coercion as validate_layout.py's `_parse_scalar` --
    quoted strings, `#`-comment stripping, null/bool/int/float, else the raw
    string."""
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


def _layout_peek_child_kind(lines, i, indent):
    """Decide whether the line after `i` opens a nested list, dict, or
    null -- same as validate_layout.py's `_peek_child_kind`."""
    if i + 1 < len(lines):
        next_indent, next_content = lines[i + 1]
        if next_indent > indent:
            return [] if next_content.startswith("- ") else {}
    return None


def _layout_load_yaml_lite(text):
    """Parse a restricted block-style YAML subset into nested
    dict/list/scalars -- byte-for-byte the same algorithm as
    validate_layout.py's `load_yaml_lite`, duplicated (see section docstring
    above) so both skills parse `context-config.yaml`/`.layout-slots.yaml`
    identically."""
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
                raise ValueError("expected sequence at indent {}: {!r}".format(indent, content))
            if ":" in item and not (item.startswith('"') or item.startswith("'")):
                key, _, val = item.partition(":")
                key = key.strip()
                val = val.strip()
                new_item = {}
                parent.append(new_item)
                if val == "":
                    child = _layout_peek_child_kind(lines, i, indent)
                    new_item[key] = child
                    stack.append((indent, new_item))
                    if child is not None:
                        stack.append((indent, child))
                else:
                    new_item[key] = _layout_parse_scalar(val)
                    stack.append((indent, new_item))
            else:
                parent.append(_layout_parse_scalar(item))
            i += 1
            continue

        if ":" not in content:
            raise ValueError("cannot parse line: {!r}".format(content))
        key, _, val = content.partition(":")
        key = key.strip().strip('"').strip("'")
        val = val.strip()
        if not isinstance(parent, dict):
            raise ValueError("expected mapping at indent {}: {!r}".format(indent, content))
        if val == "":
            child = _layout_peek_child_kind(lines, i, indent)
            parent[key] = child
            if child is not None:
                stack.append((indent, child))
        else:
            parent[key] = _layout_parse_scalar(val)
        i += 1

    return root


def _layout_load_yaml_file(path):
    path = Path(path)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8-sig")
    return _layout_load_yaml_lite(text)


def _layout_stable_sort_key(marker_path, repo_root):
    rel = marker_path.relative_to(repo_root)
    return (len(rel.parts), rel.as_posix())


def _find_layout_markers(repo_root):
    """Every `.layout-slots.yaml` under repo_root, pruning
    `_LAYOUT_IGNORED_DIR_NAMES`, in the same stable (depth, lexical) order as
    validate_layout.py's `find_markers`."""
    repo_root = Path(repo_root)
    markers = []
    for marker_path in repo_root.rglob(".layout-slots.yaml"):
        if any(part in _LAYOUT_IGNORED_DIR_NAMES for part in marker_path.parts):
            continue
        data = _layout_load_yaml_file(marker_path) or {}
        markers.append((marker_path, data.get("slots") or []))
    markers.sort(key=lambda m: _layout_stable_sort_key(m[0], repo_root))
    return markers


def _find_content_index_slot_markers(markers):
    """[(marker_path, entry)] pairs declaring `slot: autoscaffold_content_index`."""
    found = []
    for marker_path, entries in markers:
        for entry in entries:
            if entry.get("slot") == _CONTENT_INDEX_SLOT:
                found.append((marker_path, entry))
    return found


def _resolve_content_index_default(config):
    """Steps 3/4 of §16.2's resolution order, scoped to this one slot: the
    workspace_root-relative default if `layout.workspace_root` is set and
    well-formed, else the hardcoded pre-D21 default -- mirrors
    validate_layout.py's `resolve_default`/`resolve_workspace_root_default`/
    `resolve_pre_d21_default` (this slot has no `default_from` config key, so
    its pre-D21 default is always the plain hardcoded path)."""
    layout = config.get("layout")
    wr = layout.get("workspace_root") if isinstance(layout, dict) else None
    if isinstance(wr, str) and wr.rstrip("/") not in ("", "."):
        return "{}/{}".format(wr.rstrip("/"), _CONTENT_INDEX_WORKSPACE_ROOT_LEAF)
    return _CONTENT_INDEX_DEFAULT


def _resolve_content_index_slot_path(repo_root):
    """Resolve the on-disk path `render-index --out` must match, in exactly
    the order validate_layout.py's `validate()` uses for any slot: an
    explicit `.layout-slots.yaml` marker if exactly one exists, else the
    resolved default (workspace_root-relative, else the pre-D21 hardcoded
    path). Returns a Path relative to `repo_root`. Raises
    `ContentIndexSlotError` if more than one marker claims this slot."""
    repo_root = Path(repo_root).resolve()
    config = _layout_load_yaml_file(repo_root / "context-config.yaml") or {}
    markers = _find_layout_markers(repo_root)
    matches = _find_content_index_slot_markers(markers)

    if len(matches) > 1:
        locs = ", ".join(
            (m.parent.relative_to(repo_root).as_posix() or ".") for m, _ in matches
        )
        raise ContentIndexSlotError(
            "slot '{}' has markers at multiple locations ({}) -- bijectivity "
            "violation; run ult-repo-layout's `validate_layout.py reconcile` "
            "before render-index can resolve a single target".format(
                _CONTENT_INDEX_SLOT, locs
            )
        )

    if matches:
        marker_path, entry = matches[0]
        slot_dir = marker_path.parent
        target = slot_dir / entry.get("file", "CEP-INDEX.md")
        return target.resolve().relative_to(repo_root)

    return Path(_resolve_content_index_default(config))


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


def _validation_bypass_note(record):
    """TASK-0107: a generated module/repo-doc/interface whose validation
    was force-accepted despite failing (mark-* --accept-validation-failure)
    must stay visibly flagged in the rendered index, not look identical to
    a clean pass -- " -- VALIDATION-BYPASSED: <reason>" appended to its
    line, or "" for anything that passed or was never validated."""
    validation = record.get("validation")
    if not validation or validation.get("status") != "bypassed":
        return ""
    return " -- VALIDATION-BYPASSED: {}".format(validation.get("bypass_reason"))


def _validation_failed_note(record):
    """TASK-0108: a module/repo-doc/interface that exhausted its one retry
    (mark-* --final with no bypass) is persisted as `status: "failed"`
    rather than `generated` -- see `_record_validation_or_raise`'s
    docstring. That status string alone already renders via the normal
    `**{status}**` slot, but the validator's reasons still need to be
    visible, the same way a bypass's reason is -- " -- VALIDATION-FAILED:
    <reasons>" appended to the line, or "" for anything else."""
    validation = record.get("validation")
    if not validation or validation.get("status") != "failed":
        return ""
    return " -- VALIDATION-FAILED: {}".format("; ".join(validation.get("reasons") or []))


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
                "- `{}` ({}, {}) -- **{}**{}{}{}".format(
                    m["id"], detail, m["basis"], m["status"], path_note,
                    _validation_bypass_note(m), _validation_failed_note(m),
                )
            )
        lines.append("")

    generated_count = sum(1 for m in modules if m["status"] == "generated")
    pending_count = sum(1 for m in modules if m["status"] == "pending")
    skipped_count = sum(1 for m in modules if m["status"] == "skipped")
    failed_count = sum(1 for m in modules if m["status"] == "failed")
    lines.append(
        "**Progress:** {} generated, {} pending, {} skipped, {} failed "
        "({} modules total).".format(
            generated_count, pending_count, skipped_count, failed_count, len(modules)
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
        lines.append("- {} -- **{}**{}{}{}".format(
            label, doc["status"], path_note,
            _validation_bypass_note(doc), _validation_failed_note(doc),
        ))
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
                "- `{}` <-> `{}` ({}, weight {}) -- **{}**{}{}{}".format(
                    i["module_a"], i["module_b"], ",".join(i["relations"]), i["weight"],
                    i["status"], path_note,
                    _validation_bypass_note(i), _validation_failed_note(i),
                )
            )
        lines.append("")
        i_generated = sum(1 for i in interfaces if i["status"] == "generated")
        i_pending = sum(1 for i in interfaces if i["status"] == "pending")
        i_deferred = sum(1 for i in interfaces if i["status"] == "deferred")
        i_failed = sum(1 for i in interfaces if i["status"] == "failed")
        lines.append(
            "**Progress:** {} generated, {} pending, {} deferred, {} failed "
            "({} interfaces total).".format(
                i_generated, i_pending, i_deferred, i_failed, len(interfaces)
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


def _cmd_plan(args):
    state = load_state(args.state)
    try:
        packets = build_work_packets(
            state, args.repo_root, args.how_l2_path, graph_path=args.graph_path,
        )
    except (ValueError, FileNotFoundError) as e:
        # Covers the duplicate/out-of-layer output_path refusal
        # (build_work_packets' own ValueError) and a missing --graph-path
        # file (_load_graph's FileNotFoundError) -- no packet files are
        # written either way.
        print("ERROR: {}".format(e), file=sys.stderr)
        return 1
    out_dir = (
        Path(args.out_dir) if args.out_dir
        else Path(args.repo_root) / "cache" / "autoscaffold-content" / "packets"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    for packet in packets:
        packet_path = out_dir / "{}.json".format(packet["packet_id"])
        packet_path.write_text(
            json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(
        {"packets_written": len(packets), "out_dir": str(out_dir)}, indent=2
    ))
    return 0


def _cmd_scan(args):
    with state_lock(args.state):
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


def _load_packet_arg(packet_path):
    return json.loads(Path(packet_path).read_text(encoding="utf-8"))


def _cmd_validate(args):
    """Read-only dry run of Sec 6's validator -- touches neither the file
    nor any state. Exit 0 on pass, 1 on failure (script-friendly)."""
    packet = _load_packet_arg(args.packet)
    result = validate(args.repo_root, args.path, packet)
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


def _cmd_emit_skeleton(args):
    """TASK-0304: deterministically render the content_mode: skeleton
    document for a packet -- no LLM, no repo_root, no state. Prints to
    stdout by default; --out writes it (atomically) instead."""
    packet = _load_packet_arg(args.packet)
    text = emit_skeleton(
        packet, generated_at=args.generated_at, skill_version=args.skill_version,
    )
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        aaw.write_text_atomic(out_path, text)
        print("wrote {}".format(args.out))
    else:
        print(text, end="")
    return 0


def _print_validation_warnings(record):
    # Mirrors _cmd_scan's "print non-fatal warnings immediately, not just
    # persisted" posture, for the stale-packet-HEAD warning (validate()'s
    # "warnings" key -- advisory only, never affects the mark-* outcome).
    for w in (record.get("validation") or {}).get("warnings") or []:
        print("WARNING: {}".format(w), file=sys.stderr)


def _cmd_mark_generated(args):
    with state_lock(args.state):
        state = load_state(args.state)
        packet = _load_packet_arg(args.packet)
        try:
            module = mark_generated(
                state, args.module_id, args.output, packet=packet,
                repo_root=args.repo_root,
                accept_validation_failure=args.accept_validation_failure,
                final=args.final,
            )
        except ValueError as e:
            print("ERROR: {}".format(e), file=sys.stderr)
            return 1
        save_state(args.state, state)
        _print_validation_warnings(module)
        print(json.dumps(module, indent=2))
        return 0


def _cmd_mark_skipped(args):
    with state_lock(args.state):
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
    if args.out:
        # TASK-0111: --out must match the resolved autoscaffold_content_index
        # layout slot -- refuse rather than let CEP-INDEX.md drift to a
        # second location ult-repo-layout and other skills don't resolve to.
        repo_root_arg = getattr(args, "repo_root", None)
        if not repo_root_arg:
            print(
                "ERROR: --repo-root is required together with --out, to "
                "resolve the autoscaffold_content_index layout slot "
                "render-index must write to.",
                file=sys.stderr,
            )
            return 1
        repo_root = Path(repo_root_arg).resolve()
        try:
            resolved_rel = _resolve_content_index_slot_path(repo_root)
        except ContentIndexSlotError as e:
            print("ERROR: {}".format(e), file=sys.stderr)
            return 1
        out_path = Path(args.out)
        out_abs = (out_path if out_path.is_absolute() else repo_root / out_path).resolve()
        resolved_abs = (repo_root / resolved_rel).resolve()
        if out_abs != resolved_abs:
            print(
                "ERROR: --out '{}' does not match the resolved "
                "autoscaffold_content_index layout slot ('{}'). render-index "
                "refuses to write CEP-INDEX.md anywhere else, so the router "
                "file never drifts from the one location ult-repo-layout and "
                "every other skill expect it at. Pass --out '{}', or fix the "
                "slot's `.layout-slots.yaml` marker / context-config.yaml if "
                "the resolved location itself is wrong.".format(
                    args.out, resolved_rel.as_posix(), resolved_abs
                ),
                file=sys.stderr,
            )
            return 1
        with state_lock(args.state):
            state = load_state(args.state)
            text = render_index(state, args.repo_name)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            aaw.write_text_atomic(out_path, text)
            mark_index_rendered(state, args.out)
            save_state(args.state, state)
            print("wrote {}".format(out_path))
        return 0
    state = load_state(args.state)
    text = render_index(state, args.repo_name)
    print(text)
    return 0


def _cmd_show(args):
    state = load_state(args.state)
    print(json.dumps(summarize(state), indent=2))
    return 0


def _cmd_mark_repo_doc_generated(args):
    with state_lock(args.state):
        state = load_state(args.state)
        packet = _load_packet_arg(args.packet)
        try:
            doc = mark_repo_doc_generated(
                state, args.kind, args.output, packet=packet,
                repo_root=args.repo_root,
                accept_validation_failure=args.accept_validation_failure,
                final=args.final,
            )
        except ValueError as e:
            print("ERROR: {}".format(e), file=sys.stderr)
            return 1
        save_state(args.state, state)
        _print_validation_warnings(doc)
        print(json.dumps(doc, indent=2))
        return 0


def _cmd_mark_repo_doc_skipped(args):
    with state_lock(args.state):
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
    with state_lock(args.state):
        state = load_state(args.state)
        packet = _load_packet_arg(args.packet)
        try:
            interface = mark_interface_generated(
                state, args.interface_id, args.output, packet=packet,
                repo_root=args.repo_root,
                accept_validation_failure=args.accept_validation_failure,
                final=args.final,
            )
        except ValueError as e:
            print("ERROR: {}".format(e), file=sys.stderr)
            return 1
        save_state(args.state, state)
        _print_validation_warnings(interface)
        print(json.dumps(interface, indent=2))
        return 0


def _cmd_mark_interface_deferred(args):
    with state_lock(args.state):
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
    if args.with_sites and not (args.repo_root and args.graph_path):
        print(
            "ERROR: --with-sites requires --repo-root and --graph-path together",
            file=sys.stderr,
        )
        return 1

    state = load_state(args.state)
    graph = None
    if args.with_sites:
        try:
            graph = _load_graph(args.graph_path)
        except (ValueError, FileNotFoundError) as e:
            print("ERROR: {}".format(e), file=sys.stderr)
            return 1
    result = list_interfaces(
        state, eligible_only=args.eligible_only, with_sites=args.with_sites,
        repo_root=args.repo_root, graph=graph,
    )
    print(json.dumps(result, indent=2))
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

    p_plan = sub.add_parser(
        "plan", help="Build work packets for pending How-L2 documents (Sec 5.2)."
    )
    p_plan.add_argument("state")
    p_plan.add_argument("--repo-root", required=True)
    p_plan.add_argument(
        "--how-l2-path", required=True,
        help="Resolved How-L2 directory (ult-repo-layout output), relative "
             "to --repo-root, e.g. 'org'.",
    )
    p_plan.add_argument(
        "--graph-path", default=None,
        help="graphify-out/graph.json, for module dependency/must-cite "
             "evidence hints. Optional -- omit for a heuristic-mode run.",
    )
    p_plan.add_argument(
        "--out-dir", default=None,
        help="Where to write packet JSON files (default: "
             "cache/autoscaffold-content/packets under --repo-root).",
    )
    p_plan.set_defaults(func=_cmd_plan)

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

    p_validate = sub.add_parser(
        "validate", help="Dry-run Sec 6's validator against an already-written file."
    )
    p_validate.add_argument("path", help="Path to validate, relative to --repo-root.")
    p_validate.add_argument("--repo-root", required=True)
    p_validate.add_argument("--packet", required=True, help="Path to the packet JSON file.")
    p_validate.set_defaults(func=_cmd_validate)

    p_skel = sub.add_parser(
        "emit-skeleton",
        help="Deterministically render the content_mode: skeleton document "
             "for a packet (Sec 4.1), no LLM.",
    )
    p_skel.add_argument("--packet", required=True, help="Path to packet JSON file.")
    p_skel.add_argument(
        "--out", default=None, help="Write rendered skeleton here instead of stdout."
    )
    p_skel.add_argument(
        "--generated-at", default=None, help="Override the frontmatter generated_at value."
    )
    p_skel.add_argument(
        "--skill-version", default=None, help="Override the frontmatter skill_version value."
    )
    p_skel.set_defaults(func=_cmd_emit_skeleton)

    p_gen = sub.add_parser("mark-generated", help="Mark one module generated.")
    p_gen.add_argument("state")
    p_gen.add_argument("module_id")
    p_gen.add_argument("--output", required=True)
    p_gen.add_argument("--repo-root", required=True)
    p_gen.add_argument("--packet", required=True, help="Path to the packet JSON file.")
    p_gen.add_argument(
        "--accept-validation-failure", default=None, metavar="REASON",
        help="Record the output as generated despite failed validation, with this reason.",
    )
    p_gen.add_argument(
        "--final", action="store_true",
        help="This is the orchestrator's last retry for this module: a failed "
        "validation (with no --accept-validation-failure) is persisted as "
        "status 'failed' instead of raising and leaving the module pending.",
    )
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
    p_render.add_argument(
        "--repo-root", default=None,
        help="Required together with --out: --out is refused unless it matches "
        "the resolved autoscaffold_content_index layout slot for this repo root.",
    )
    p_render.set_defaults(func=_cmd_render_index)

    p_show = sub.add_parser("show", help="Print schema_version, graph mode, and per-tier counts.")
    p_show.add_argument("state")
    p_show.set_defaults(func=_cmd_show)

    p_rdgen = sub.add_parser("mark-repo-doc-generated", help="Mark one repo-wide doc generated.")
    p_rdgen.add_argument("state")
    p_rdgen.add_argument("kind", choices=REPO_DOC_KINDS)
    p_rdgen.add_argument("--output", required=True)
    p_rdgen.add_argument("--repo-root", required=True)
    p_rdgen.add_argument("--packet", required=True, help="Path to the packet JSON file.")
    p_rdgen.add_argument(
        "--accept-validation-failure", default=None, metavar="REASON",
        help="Record the output as generated despite failed validation, with this reason.",
    )
    p_rdgen.add_argument(
        "--final", action="store_true",
        help="This is the orchestrator's last retry for this doc: a failed "
        "validation (with no --accept-validation-failure) is persisted as "
        "status 'failed' instead of raising and leaving the doc pending.",
    )
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
    p_ifgen.add_argument("--repo-root", required=True)
    p_ifgen.add_argument("--packet", required=True, help="Path to the packet JSON file.")
    p_ifgen.add_argument(
        "--accept-validation-failure", default=None, metavar="REASON",
        help="Record the output as generated despite failed validation, with this reason.",
    )
    p_ifgen.add_argument(
        "--final", action="store_true",
        help="This is the orchestrator's last retry for this interface: a failed "
        "validation (with no --accept-validation-failure) is persisted as "
        "status 'failed' instead of raising and leaving the interface pending.",
    )
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
        help=(
            "Filter to pending pairs whose both endpoint modules have settled "
            "(generated, or skipped tier-3 leaf)."
        ),
    )
    p_iflist.add_argument(
        "--with-sites", action="store_true",
        help="Add a 'call_sites' key (evidence_hints.call_sites shape) to each "
             "entry, derived from --graph-path. Requires --repo-root and "
             "--graph-path together.",
    )
    p_iflist.add_argument(
        "--repo-root", default=None,
        help="Repo root call sites are searched relative to. Required with --with-sites.",
    )
    p_iflist.add_argument(
        "--graph-path", default=None,
        help="graphify-out/graph.json. Required with --with-sites.",
    )
    p_iflist.set_defaults(func=_cmd_list_interfaces)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
