#!/usr/bin/env python3
"""discover_layers.py - layer-path discovery for brownfield adoption
(D23 CONTEXT-ENGINEERING-DESIGN.md §17.2-17.4, CEP-DP-001H Stage 3 PR 1).

Adds the second `discover` phase §17.2 describes: after the existing 8-slot
resolution (`validate_layout.py`'s SLOT_REGISTRY, unaffected by this module),
scan for candidates for the four layer paths (`layers.what_l2`,
`layers.what_l1`, `how_dimension.how_l2`, `how_dimension.how_l1`) and render
`context-layout-discovery.md` - a proposal artifact, never written back to
`context-config.yaml` directly (that is `confirm-layers`'s job, §17.5,
CEP-DP-001H PR 2, not this module).

Reuses `validate_layout.py`'s YAML-lite parser and layer-path resolvers
rather than reimplementing them - this module's own resolver-precedence
logic (`_precedence_check`, `_default_path_check`) is additive on top of
those, not a replacement.

Per-layer discovery runs three checks in a fixed order (§17.4):
1. Hand-configured-path precedence (resolves H4) - a path a human already
   set, that exists and has content, is never re-scored (shape 2b NOTICE).
2. Default-path check (What-L2/How-L2 only) - the CEP-promised default,
   if it exists and has content, stops here too (shape 2a NOTICE).
3. Scan and score - deterministic, stdlib-only (no LLM in scoring itself,
   same posture as `validate_layout.py`).

Escalation (fixes C-1, generalizes to all four layers): if none of the three
checks resolves a layer, it never falls through to a passive shape-3 notice
unless it is What-L1/How-L1 while `enabled: false`. Always-on layers
(What-L2/How-L2) get `CUSTOM: <path> | ACKNOWLEDGE`; an enabled-but-unresolved
opt-in layer gets `CUSTOM: <path> | DISABLE`.

Cross-layer collision/nesting check (§17.4 "known limitation", stress
scenario S30, open question 6) is pulled into this package's own scope per
decision log D-017/D-018 - NOT specified in `CONTEXT-ENGINEERING-DESIGN.md`
beyond naming the gap. Its artifact syntax (`collision_decision: PENDING #
ACKNOWLEDGE | CUSTOM: <layer> -> <path>`) is this module's own
implementation-shape choice, built by extending the same PENDING-decision-
field pattern §17.3 already uses for every other escalation case (consistent
CEP terminology, per the Implementation Order's Stage 3 instructions) - it is
not a literal design-doc quote. Flagged for Founder review in the PR 1
report, same as every other artifact-syntax choice this module had to make
where §17.3's worked example didn't show one (e.g. the "Requirements
category empty, multiple other categories tie" sub-case, H-2).

Python 3 stdlib only (re, os, pathlib) - vendorable alongside
validate_layout.py / md_index.py / content_hash.py.

CLI:
    python discover_layers.py [<repo-root>]
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_layout as vl  # noqa: E402

# ---------------------------------------------------------------------------
# §17.4 constants
# ---------------------------------------------------------------------------

# "never outputs/" (§16.5) - CEP_BUCKET_DIR_NAMES is deliberately NOT the
# same set as validate_layout.IGNORED_DIR_NAMES (that set is about marker
# discovery, not corpus scoring, and does not include the CEP buckets).
CEP_BUCKET_DIR_NAMES = {"contexts", "inputs", "cache"}

# §17.4's What-L2/How-L2 sibling-scan exclusion list, applied in addition to
# CEP_BUCKET_DIR_NAMES.
SCAN_IGNORED_DIR_NAMES = {
    ".git", "node_modules", "vendor", "dist", "build", "target",
    ".venv", "__pycache__",
}

DOC_EXTENSIONS = (".md", ".rst", ".adoc")
DIAGRAM_EXTENSIONS = (".drawio", ".puml")
API_SPEC_FILENAMES = {"openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json"}
API_SPEC_EXTENSIONS = (".proto", ".graphql", ".gql")

REQUIREMENTS_NAME_RE = re.compile(r"docs|documentation|spec|specs|specification|requirements", re.I)
DESIGN_NAME_RE = re.compile(r"design|architecture|adr|rfc|decisions?", re.I)
API_NAME_RE = re.compile(r"api|proto|graphql|schema", re.I)
ADR_FILENAME_RE = re.compile(r"^\d{4}-.*\.md$", re.I)

HOW_L2_CANDIDATE_DIRS = ["docs/style-guide/", "conventions/", ".github/"]
WHAT_L1_CANDIDATE_DIRS = ["specs/external/", "standards/", "vendor/docs/", "third_party/docs/"]
HOW_L1_CANDIDATE_DIRS = ["org/process-standards/", "standards/", "process/", "compliance/standards/"]

HOW_L2_ROOT_SIGNAL_GLOBS = ["CONTRIBUTING.md", "STYLE_GUIDE*.md", ".eslintrc*", ".prettierrc*", ".flake8"]
HOW_L2_ROOT_SIGNAL_FILES = [".editorconfig"]

# High confidence's file-count floor (§17.4: "High = name matches and file
# count >= 10"). Medium's "enough files without a name match" floor is not
# quantified in the design doc - this module picks 3 as a conservative
# implementation default; flagged in the PR 1 report as a judgment call.
HIGH_CONFIDENCE_FILE_FLOOR = 10
MEDIUM_CONFIDENCE_FILE_FLOOR = 3

# Not in §17.4 - an additional, explicitly-flagged noise-reduction floor.
# A directory with no name match still needs at least this many matching
# files to become a candidate at all; a single incidental file (a stray
# README a tool dropped, an unrelated one-off doc) is not evidence of an
# authored corpus and would otherwise surface as a "Low confidence" row on
# every scan. Purely additive: raising this floor can only remove noise
# candidates, never suppress a name-matched one (name_match alone still
# qualifies regardless of file count) or a genuinely well-populated one.
MIN_DOC_COUNT_FOR_UNNAMED_MATCH = 2


# ---------------------------------------------------------------------------
# Filesystem scanning helpers
# ---------------------------------------------------------------------------

def _prune_ignored(dirnames, extra_ignored=frozenset()):
    """Prune scan-ignored, CEP-bucket, caller-supplied, and dot-prefixed
    directory names. Dot-directories (.pytest_cache, .venv, .idea, ...) are
    excluded generically rather than by an ever-growing named blocklist -
    hidden directories are virtually always tooling/cache artifacts, never an
    intentionally-authored corpus. This does not affect the fixed-candidate-
    list checks for How-L2/What-L1/How-L1 (e.g. .github/), which probe exact
    paths via _has_content() rather than walking through this pruning."""
    keep = []
    for d in dirnames:
        if d in SCAN_IGNORED_DIR_NAMES or d in CEP_BUCKET_DIR_NAMES or d in extra_ignored:
            continue
        if d.startswith("."):
            continue
        keep.append(d)
    return keep


def _iter_files(dirpath, extra_ignored=frozenset()):
    """Yield every file under dirpath, pruning SCAN_IGNORED_DIR_NAMES,
    CEP_BUCKET_DIR_NAMES, and extra_ignored at every level (§17.4's
    unconditional CEP-bucket exclusion, resolves M2's first half)."""
    for root, dirnames, filenames in os.walk(dirpath):
        dirnames[:] = _prune_ignored(dirnames, extra_ignored)
        for fn in filenames:
            yield Path(root) / fn


def _count_docs(dirpath, extra_ignored=frozenset()):
    return sum(1 for f in _iter_files(dirpath, extra_ignored) if f.suffix.lower() in DOC_EXTENSIONS)


def _count_by_ext(dirpath, extensions, extra_ignored=frozenset()):
    return sum(1 for f in _iter_files(dirpath, extra_ignored) if f.suffix.lower() in extensions)


def _count_adr_filenames(dirpath, extra_ignored=frozenset()):
    return sum(1 for f in _iter_files(dirpath, extra_ignored) if ADR_FILENAME_RE.match(f.name))


def _has_api_spec_filenames(dirpath, extra_ignored=frozenset()):
    return any(f.name.lower() in API_SPEC_FILENAMES for f in _iter_files(dirpath, extra_ignored))


def _dir_mtime(dirpath):
    try:
        return dirpath.stat().st_mtime
    except OSError:
        return 0.0


def _has_content(repo_root, rel_path):
    """§17.4 steps 1-2: does this path exist and contain at least one file
    (after CEP-bucket exclusion)? Mirrors check_layer_paths_populated's own
    existence+non-empty check in validate_layout.py."""
    target = Path(repo_root) / rel_path.rstrip("/")
    if not target.is_dir():
        return False
    return any(True for _ in _iter_files(target))


def _top_level_candidate_dirs(repo_root, base=None):
    """Immediate subdirectories of `base` (default: repo_root), pruned of
    SCAN_IGNORED_DIR_NAMES/CEP_BUCKET_DIR_NAMES. §17.4's "sibling
    directories" scan operates one level down from `base`."""
    base = Path(base) if base is not None else Path(repo_root)
    if not base.is_dir():
        return []
    names = _prune_ignored([p.name for p in base.iterdir() if p.is_dir()])
    return sorted(base / n for n in names)


# ---------------------------------------------------------------------------
# §17.4 category signals (What-L2 composite corpus)
# ---------------------------------------------------------------------------

def _requirements_signal(path):
    name_match = bool(REQUIREMENTS_NAME_RE.search(path.name))
    doc_count = _count_docs(path)
    return name_match, doc_count


def _design_signal(path):
    name_match = bool(DESIGN_NAME_RE.search(path.name))
    adr_count = _count_adr_filenames(path)
    diagram_count = _count_by_ext(path, DIAGRAM_EXTENSIONS)
    matched = name_match or adr_count > 0 or diagram_count > 0
    return matched, {"name_match": name_match, "adr_count": adr_count, "diagram_count": diagram_count}


def _api_signal(path):
    name_match = bool(API_NAME_RE.search(path.name))
    has_spec_file = _has_api_spec_filenames(path) or _count_by_ext(path, API_SPEC_EXTENSIONS) > 0
    matched = name_match or has_spec_file
    return matched, {"name_match": name_match, "has_spec_file": has_spec_file}


def _generic_fallback_signal(path, doc_count=None):
    if doc_count is None:
        doc_count = _count_docs(path)
    return doc_count >= MIN_DOC_COUNT_FOR_UNNAMED_MATCH, {"doc_count": doc_count}


def _confidence(name_match, count):
    if name_match and count >= HIGH_CONFIDENCE_FILE_FLOOR:
        return "High"
    if (name_match and count > 0) or (not name_match and count >= MEDIUM_CONFIDENCE_FILE_FLOOR):
        return "Medium"
    return "Low"


def categorize_candidate(path):
    """Return {category: evidence} for every §17.4 category this directory
    matches. A directory matching more than one category gets every match
    folded into one evidence dict here - callers dedup by path, not by
    category (resolves M-2)."""
    categories = {}

    req_name, req_count = _requirements_signal(path)
    if req_name or req_count >= MIN_DOC_COUNT_FOR_UNNAMED_MATCH:
        categories["Requirements"] = {
            "name_match": req_name, "files": req_count,
            "confidence": _confidence(req_name, req_count),
        }

    design_matched, design_ev = _design_signal(path)
    if design_matched:
        categories["Design"] = design_ev

    api_matched, api_ev = _api_signal(path)
    if api_matched:
        categories["API/spec"] = api_ev

    if not categories:
        generic_matched, generic_ev = _generic_fallback_signal(path)
        if generic_matched:
            categories["Generic fallback"] = generic_ev

    return categories


# ---------------------------------------------------------------------------
# Decision-field rendering helpers (§17.3's PENDING-field vocabulary)
# ---------------------------------------------------------------------------

def _fmt_evidence(categories):
    parts = []
    for cat, ev in categories.items():
        bits = ", ".join(f"{k}={v}" for k, v in ev.items())
        parts.append(f"{cat} ({bits})")
    return "; ".join(parts)


class LayerSection:
    """One §17.3 artifact section - the rendered result for a single layer
    (or the cross-layer collision block, which reuses the same shape)."""

    def __init__(self, title, status_lines=None, notices=None, table=None,
                 table_header=None, decision_lines=None, warning=None):
        self.title = title
        self.status_lines = status_lines or []
        self.notices = notices or []
        self.table_header = table_header
        self.table = table or []
        self.decision_lines = decision_lines or []
        self.warning = warning

    def render(self):
        lines = [f"## {self.title}"]
        lines.extend(self.status_lines)
        for n in self.notices:
            lines.append("")
            lines.append(f"NOTICE: {n}")
        if self.table:
            lines.append("")
            lines.append("| " + " | ".join(self.table_header) + " |")
            lines.append("| " + " | ".join("---" for _ in self.table_header) + " |")
            for row in self.table:
                lines.append("| " + " | ".join(row) + " |")
        if self.warning:
            lines.append("")
            lines.append(f"    # WARNING: {self.warning}")
        for d in self.decision_lines:
            lines.append("")
            lines.append(f"    {d}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# What-L2 (§17.4 composite corpus)
# ---------------------------------------------------------------------------

def discover_what_l2(repo_root, config):
    repo_root = Path(repo_root)
    configured_path = None
    what_l2 = (config.get("layers") or {}).get("what_l2")
    if isinstance(what_l2, dict) and isinstance(what_l2.get("path"), str) and what_l2["path"]:
        configured_path = what_l2["path"]
    wr = vl._normalize_workspace_root(config)
    # The "would-be" default with the explicit override stripped out -
    # resolve_what_l2_path(config) always honors an explicit `path`, so it
    # cannot be used to detect whether one was set (that comparison would
    # always be false-positive-free-of-signal: configured value vs. itself).
    unconfigured_default = f"{wr}/" if wr and wr != "." else "docs/requirements/"
    default_path = vl.resolve_what_l2_path(config)

    # Step 1: hand-configured-path precedence (resolves H4). "Other than the
    # CEP default" - if the explicit value differs from what resolve_*
    # would compute in the ABSENCE of that override (i.e. it's not simply
    # restating the default).
    if configured_path and configured_path.rstrip("/") != unconfigured_default.rstrip("/"):
        if _has_content(repo_root, configured_path):
            return LayerSection(
                "What-L2 - project's own requirements/spec docs",
                status_lines=["**Status:** hand-configured already."],
                notices=[
                    f"`what_l2.path` is set to `{configured_path}`, which is not the "
                    f"CEP default and exists with content (§17.4 step 1, shape 2b). "
                    f"Discovery does not re-score or challenge it."
                ],
            ), configured_path, []

    if wr:
        return _discover_what_l2_workspace_root_set(repo_root, config, wr, default_path)
    return _discover_what_l2_workspace_root_unset(repo_root, config, default_path)


def _discover_what_l2_workspace_root_set(repo_root, config, wr, default_path):
    section_title = "What-L2 - project's own requirements/spec docs"
    exclude = set(e.rstrip("/") for e in vl.resolve_what_l2_exclude(config))
    wr_dir = Path(repo_root) / wr

    # Outside-workspace_root composite scan always runs (Founder
    # clarification on C1) - proposed as include_roots regardless of
    # whether `path` itself resolved.
    outside_candidates = _composite_sibling_scan(repo_root, exclude_base=wr_dir)

    # Step 2: does {workspace_root}/ exist and have content after
    # exclusions?
    if wr_dir.is_dir() and any(
        f for f in _iter_files(wr_dir) if not any(
            f.relative_to(wr_dir).parts[:1] == (Path(e).parts[0],) for e in exclude if e
        )
    ):
        section = LayerSection(
            section_title,
            status_lines=[f"**Status:** enabled by default. **workspace_root: set -> `{wr}/`**"],
            notices=[
                f"`what_l2.path` already resolves to `{wr}/` (§16.5) and has content "
                f"after the CEP-bucket exclusions (`contexts/`, `inputs/`, `cache/` - "
                f"never `outputs/`). This is the correct answer by construction "
                f"(shape 2a) - nothing to decide."
            ],
        )
    else:
        section = LayerSection(
            section_title,
            status_lines=[f"**Status:** enabled by default. **workspace_root: set -> `{wr}/`**"],
            decision_lines=["decision: PENDING   # CUSTOM: <path> | ACKNOWLEDGE"],
            warning=(
                f"`{wr}/` resolves as `what_l2.path` (§16.5) but has no content after "
                f"CEP-bucket exclusions. CUSTOM to point it at a corpus once one "
                f"exists, or ACKNOWLEDGE to record that this project has no such "
                f"content yet."
            ),
        )

    # Non-CEP-bucket subdirectory inside workspace_root that scores as
    # vendor/generated -> exclude_decision proposal, with M-3 CAUTION note
    # if it also equals another layer's hand-configured path.
    exclude_rows = []
    exclude_lines = []
    for cand in _top_level_candidate_dirs(repo_root, base=wr_dir):
        rel = cand.relative_to(repo_root).as_posix() + "/"
        if _looks_vendor_or_generated(cand):
            other_layer = _matches_other_hand_configured_path(config, rel)
            exclude_rows.append([f"`{rel}`", str(_count_docs(cand) if _count_docs(cand) else _count_by_ext(cand, ('',))), "generated/vendor filenames, minimal human-authored content" + (f" - **also equals `{other_layer}`** (hand-configured)" if other_layer else "")])
            exclude_lines.append(f"exclude_decision: PENDING   # ADD: {rel} | SKIP")
            if other_layer:
                exclude_lines.append(
                    f"    # CAUTION (cross-layer overlap, M-3): {rel} also equals "
                    f"{other_layer}. Excluding it would silently drop that layer's "
                    f"already-confirmed content from What-L2's composite corpus. "
                    f"This is a warning, not a block - the general cross-layer "
                    f"collision check below covers the blocking case."
                )
    if exclude_rows:
        section.table_header = ["Candidate", "Files", "Evidence"]
        section.table = exclude_rows
        section.decision_lines.extend(exclude_lines)

    include_rows, include_lines = _render_include_roots(outside_candidates, primary_path=None)
    if include_rows:
        section.decision_lines.append("")
        section.decision_lines.extend(include_lines)
        section.table_header = section.table_header or ["Candidate", "Category", "Evidence"]
        section.table = section.table + include_rows if section.table else include_rows

    resolved_path = wr + "/" if wr_dir.is_dir() else None
    include_roots_paths = [c[0] for c in outside_candidates]
    return section, resolved_path, include_roots_paths


def _discover_what_l2_workspace_root_unset(repo_root, config, default_path):
    section_title = "What-L2 - project's own requirements/spec docs"

    if _has_content(repo_root, default_path):
        section = LayerSection(
            section_title,
            status_lines=["**Status:** enabled by default."],
            notices=[
                f"`what_l2.path` resolves to the pre-D21 default `{default_path}` "
                f"and has content (§17.4 step 2, shape 2a). Nothing to decide."
            ],
        )
        resolved_path = default_path
    else:
        candidates = _top_level_candidate_dirs(repo_root)
        req_candidates = []
        for cand in candidates:
            name_match, doc_count = _requirements_signal(cand)
            if name_match or doc_count >= MIN_DOC_COUNT_FOR_UNNAMED_MATCH:
                req_candidates.append((cand, name_match, doc_count))
        req_candidates.sort(key=lambda c: (c[1], c[2], _dir_mtime(c[0])), reverse=True)

        rows = [
            [f"`{c.relative_to(repo_root).as_posix()}/`", "Requirements",
             "yes" if nm else "no", str(dc), _confidence(nm, dc)]
            for c, nm, dc in req_candidates
        ]

        if req_candidates:
            top = req_candidates[0][0]
            top_rel = top.relative_to(repo_root).as_posix() + "/"
            section = LayerSection(
                section_title,
                status_lines=["**Status:** enabled by default."],
                table_header=["Candidate", "Category", "Name match", "Files", "Confidence"],
                table=rows,
                decision_lines=[f"decision: PENDING   # CONFIRM: {top_rel} | CUSTOM: <path> | SKIP"],
            )
            resolved_path = None  # proposal only, not yet confirmed
        elif rows:
            # Should not happen (rows implies req_candidates non-empty); guard.
            resolved_path = None
            section = LayerSection(section_title, status_lines=["**Status:** enabled by default."])
        else:
            # H-2: no Requirements match at all. List every surviving
            # other-category candidate and require an explicit decision -
            # never auto-assign `path` to another category's best score.
            other_candidates = _composite_sibling_scan(repo_root, exclude_base=None, exclude_categories=("Requirements",))
            if other_candidates:
                rows2 = [[f"`{rel}`", cats, ev] for rel, cats, ev in other_candidates]
                decision_lines = [
                    f"decision: PENDING   # CONFIRM: {rel} | SKIP  "
                    f"(H-2: no Requirements match exists - pick which category match, "
                    f"if any, fills `what_l2.path`; every candidate not picked still "
                    f"becomes an include_roots candidate below)"
                    for rel, _cats, _ev in other_candidates
                ]
                section = LayerSection(
                    section_title,
                    status_lines=["**Status:** enabled by default."],
                    table_header=["Candidate", "Category", "Evidence"],
                    table=rows2,
                    decision_lines=decision_lines,
                )
            else:
                section = LayerSection(
                    section_title,
                    status_lines=["**Status:** enabled by default."],
                    decision_lines=["decision: PENDING   # CUSTOM: <path> | ACKNOWLEDGE"],
                    warning=(
                        f"No requirements/design/API documentation was found anywhere "
                        f"in this repo, and `what_l2.path` (`{default_path}`) has no "
                        f"existing content to default to. CUSTOM to point it at a "
                        f"corpus once one exists, or ACKNOWLEDGE that this project has "
                        f"no such content yet."
                    ),
                )
            resolved_path = None

    # Composite sibling scan for every OTHER category always runs,
    # independent of whether `path` resolved (fixes H-1).
    other_candidates = _composite_sibling_scan(repo_root, exclude_base=None, exclude_categories=("Requirements",))
    include_rows = [[f"`{rel}`", cats, ev] for rel, cats, ev in other_candidates]
    include_lines = [f"include_roots_decision: PENDING   # ADD: {rel} | SKIP" for rel, _c, _e in other_candidates]
    if include_rows:
        if section.table:
            section.table.extend(include_rows)
        else:
            section.table_header = ["Candidate", "Category", "Evidence"]
            section.table = include_rows
        section.decision_lines.append("")
        section.decision_lines.extend(include_lines)

    include_roots_paths = [rel for rel, _c, _e in other_candidates]
    return section, resolved_path, include_roots_paths


def _looks_vendor_or_generated(path):
    """Heuristic used only for the workspace_root-set exclude_decision
    proposal: a directory with many files but effectively no human-authored
    docs (.md/.rst/.adoc) looks generated/vendored. Not part of §17.4's
    named category signals - a narrow, explicitly-flagged implementation
    choice, since the design doc names the *outcome* (propose as exclude)
    but not the exact detection rule."""
    total = sum(1 for _ in _iter_files(path))
    docs = _count_docs(path)
    return total >= 5 and docs == 0


def _matches_other_hand_configured_path(config, rel):
    """M-3: does `rel` equal another layer's hand-configured path? Returns
    the label of that layer if so, else None."""
    rel_norm = rel.rstrip("/")
    checks = [
        ("how_dimension.how_l2", vl.resolve_how_l2_path(config)),
        ("layers.what_l1", vl.resolve_what_l1_path(config)),
        ("how_dimension.how_l1", vl.resolve_how_l1_path(config)),
    ]
    for label, path in checks:
        if path and path.rstrip("/") == rel_norm:
            return f"{label}.path"
    return None


def _composite_sibling_scan(repo_root, exclude_base=None, exclude_categories=()):
    """Scan top-level directories (outside `exclude_base` if given) for
    every §17.4 category match, dedup by unique resolved path with every
    matched category folded into one evidence string (resolves M-2). Returns
    [(rel_path_str, categories_str, evidence_str)]."""
    repo_root = Path(repo_root)
    candidates = _top_level_candidate_dirs(repo_root)
    if exclude_base is not None:
        exclude_base = Path(exclude_base).resolve()
        candidates = [c for c in candidates if c.resolve() != exclude_base]

    results = []
    for cand in candidates:
        categories = categorize_candidate(cand)
        for cat in exclude_categories:
            categories.pop(cat, None)
        if not categories:
            continue
        rel = cand.relative_to(repo_root).as_posix() + "/"
        results.append((rel, ", ".join(categories.keys()), _fmt_evidence(categories)))
    results.sort(key=lambda r: r[0])
    return results


def _render_include_roots(candidates, primary_path):
    rows = [[f"`{rel}`", cats, ev] for rel, cats, ev in candidates if rel != primary_path]
    lines = [f"include_roots_decision: PENDING   # ADD: {rel} | SKIP" for rel, _c, _e in candidates if rel != primary_path]
    return rows, lines


# ---------------------------------------------------------------------------
# How-L2 (§17.4: fixed directory-candidate list, then root-signal fallback)
# ---------------------------------------------------------------------------

def discover_how_l2(repo_root, config):
    repo_root = Path(repo_root)
    section_title = "How-L2 - this project's own compiled conventions"
    configured_path = None
    how_l2 = (config.get("how_dimension") or {}).get("how_l2")
    if isinstance(how_l2, dict) and isinstance(how_l2.get("path"), str) and how_l2["path"]:
        configured_path = how_l2["path"]
    # Literal fallback resolve_how_l2_path(config) would use in the ABSENCE
    # of an explicit override (see discover_what_l2's identical concern -
    # comparing configured_path against resolve_how_l2_path(config) itself
    # is always a no-op, since that function already honors the override).
    unconfigured_default = "org/"
    default_path = vl.resolve_how_l2_path(config)

    if configured_path and configured_path.rstrip("/") != unconfigured_default.rstrip("/"):
        if _has_content(repo_root, configured_path):
            return LayerSection(
                section_title,
                status_lines=["**Status:** hand-configured already."],
                notices=[
                    f"`how_l2.path` is set to `{configured_path}`, which is not the "
                    f"CEP default (`{default_path}`) but exists with content (§17.4 "
                    f"step 1, shape 2b). Discovery does not re-score or challenge it."
                ],
            ), configured_path

    if _has_content(repo_root, default_path):
        return LayerSection(
            section_title,
            status_lines=["**Status:** enabled by default."],
            notices=[
                f"`how_l2.path` resolves to the pre-D21 default `{default_path}` and "
                f"has content (§17.4 step 2, shape 2a). Nothing to decide."
            ],
        ), default_path

    ranked = []
    for cand_rel in HOW_L2_CANDIDATE_DIRS:
        cand = repo_root / cand_rel.rstrip("/")
        if cand.is_dir():
            doc_count = _count_docs(cand)
            if doc_count > 0 or any(True for _ in _iter_files(cand)):
                ranked.append((cand_rel, doc_count, _dir_mtime(cand)))
    ranked.sort(key=lambda r: (r[1], r[2]), reverse=True)

    if ranked:
        top_rel = ranked[0][0]
        return LayerSection(
            section_title,
            status_lines=["**Status:** no hand-configured `how_l2.path`; CEP default missing/empty."],
            decision_lines=[f"decision: PENDING   # CONFIRM: {top_rel} | CUSTOM: <path> | SKIP"],
        ), None

    # Root-signal-only fallback (fixes H-3's "not a directory" framing):
    # evidence conventions exist, but not enough to name a directory.
    signals = _how_l2_root_signals(repo_root)
    if signals:
        return LayerSection(
            section_title,
            status_lines=["**Status:** no hand-configured `how_l2.path`; CEP default and candidate directories all missing/empty."],
            decision_lines=["decision: PENDING   # CUSTOM: <path> | ACKNOWLEDGE"],
            warning=(
                f"Root-level convention files found ({', '.join(signals)}), but no "
                f"dedicated directory exists to set `how_l2.path` to. CUSTOM to point "
                f"it somewhere real, or ACKNOWLEDGE that conventions live only in "
                f"scattered root config for now."
            ),
        ), None

    return LayerSection(
        section_title,
        status_lines=["**Status:** no hand-configured `how_l2.path`; CEP default and candidate directories all missing/empty."],
        decision_lines=["decision: PENDING   # CUSTOM: <path> | ACKNOWLEDGE"],
        warning=(
            "No conventions directory or root-level convention signal was found "
            "anywhere in this repo. CUSTOM to point it at a corpus once one exists, "
            "or ACKNOWLEDGE that this project has no such content yet."
        ),
    ), None


def _how_l2_root_signals(repo_root):
    repo_root = Path(repo_root)
    found = []
    for name in HOW_L2_ROOT_SIGNAL_FILES:
        if (repo_root / name).is_file():
            found.append(name)
    for pattern in HOW_L2_ROOT_SIGNAL_GLOBS:
        for match in repo_root.glob(pattern):
            if match.is_file():
                found.append(match.name)
    pyproject = repo_root / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8", errors="ignore")
        if "[tool.ruff]" in text or "[tool.black]" in text:
            found.append("pyproject.toml [tool.ruff]/[tool.black]")
    return found


# ---------------------------------------------------------------------------
# What-L1 / How-L1 (§17.4: opt-in, enabled/found 4-case matrix)
# ---------------------------------------------------------------------------

def _discover_opt_in_layer(repo_root, config, *, section_title, config_section_getter,
                            resolve_path, resolve_enabled, candidate_dirs, layer_label):
    repo_root = Path(repo_root)
    section_data = config_section_getter(config)
    configured_path = None
    if isinstance(section_data, dict) and isinstance(section_data.get("path"), str) and section_data["path"]:
        configured_path = section_data["path"]
    enabled = resolve_enabled(config)

    # Step 1: hand-configured-path precedence applies to opt-in layers too -
    # "discovery does not re-score or challenge" a path a human already set,
    # regardless of the layer's current enabled value (§17.4 step 1 is
    # unconditional; the enabled/found matrix below only ever governs what
    # happens when step 1 did NOT resolve the layer).
    if configured_path and _has_content(repo_root, configured_path):
        return LayerSection(
            section_title,
            status_lines=[f"**Status:** hand-configured already (`{layer_label}.enabled: {str(enabled).lower()}`)."],
            notices=[
                f"`{layer_label}.path` is set to `{configured_path}` and exists with "
                f"content (§17.4 step 1, shape 2b). Discovery does not re-score or "
                f"challenge it."
            ],
        ), configured_path

    found_rel = None
    for cand_rel in candidate_dirs:
        if _has_content(repo_root, cand_rel):
            found_rel = cand_rel
            break

    if found_rel and not enabled:
        return LayerSection(
            section_title,
            status_lines=[f"**Status:** disabled by default (`{layer_label}.enabled: false`)."],
            decision_lines=[
                f"decision: PENDING   # CONFIRM: {found_rel} | CUSTOM: <path> | SKIP",
                "enable: PENDING      # true | false - discovery never flips this on by itself",
            ],
        ), None
    if found_rel and enabled:
        return LayerSection(
            section_title,
            status_lines=[f"**Status:** `{layer_label}.enabled: true` already."],
            decision_lines=[f"decision: PENDING   # CONFIRM: {found_rel} | CUSTOM: <path> | SKIP"],
        ), None
    if not found_rel and not enabled:
        return LayerSection(
            section_title,
            status_lines=[f"**Status:** disabled by default (`{layer_label}.enabled: false`)."],
            notices=[
                f"No existing drop-zone found (checked {', '.join(candidate_dirs)}). "
                f"Nothing proposed (shape 3) - leaving this layer disabled is the "
                f"correct default, not a gap."
            ],
        ), None
    # not found_rel and enabled: escalated, never shape 3 (S32).
    return LayerSection(
        section_title,
        status_lines=[f"**Status:** `{layer_label}.enabled: true` already, but nothing resolves."],
        decision_lines=[f"decision: PENDING   # CUSTOM: <path> | DISABLE"],
        warning=(
            f"`{layer_label}.enabled` is true but no path resolves (checked "
            f"{', '.join(candidate_dirs)}). CUSTOM to point it at the corpus, or "
            f"DISABLE (sets `{layer_label}.enabled: false`)."
        ),
    ), None


def discover_what_l1(repo_root, config):
    return _discover_opt_in_layer(
        repo_root, config,
        section_title="What-L1 - external reference material (standards/specs this project didn't author)",
        config_section_getter=lambda c: (c.get("layers") or {}).get("what_l1"),
        resolve_path=vl.resolve_what_l1_path,
        resolve_enabled=vl.resolve_what_l1_enabled,
        candidate_dirs=WHAT_L1_CANDIDATE_DIRS,
        layer_label="what_l1",
    )


def discover_how_l1(repo_root, config):
    return _discover_opt_in_layer(
        repo_root, config,
        section_title="How-L1 - org-wide process standards",
        config_section_getter=lambda c: (c.get("how_dimension") or {}).get("how_l1"),
        resolve_path=vl.resolve_how_l1_path,
        resolve_enabled=vl.resolve_how_l1_enabled,
        candidate_dirs=HOW_L1_CANDIDATE_DIRS,
        layer_label="how_l1",
    )


# ---------------------------------------------------------------------------
# Cross-layer collision/nesting check (S30, open question 6, pulled into
# scope per decision log D-017/D-018 - NOT specified in the design doc
# beyond naming the gap; this module's own extension of §17.3's PENDING-
# decision-field pattern, flagged in the PR 1 report).
# ---------------------------------------------------------------------------

def _resolved_layer_paths(config, what_l2_path, what_l2_roots, what_l1_path, how_l2_path, how_l1_path):
    paths = {}
    if what_l2_path:
        paths["layers.what_l2.path"] = what_l2_path.rstrip("/")
    for i, root in enumerate(what_l2_roots or []):
        paths[f"layers.what_l2.include_roots[{i}]"] = root.rstrip("/")
    if what_l1_path:
        paths["layers.what_l1.path"] = what_l1_path.rstrip("/")
    if how_l2_path:
        paths["how_dimension.how_l2.path"] = how_l2_path.rstrip("/")
    if how_l1_path:
        paths["how_dimension.how_l1.path"] = how_l1_path.rstrip("/")
    return paths


def _paths_collide_or_nest(a, b):
    a_parts, b_parts = Path(a).parts, Path(b).parts
    shorter, longer = (a_parts, b_parts) if len(a_parts) <= len(b_parts) else (b_parts, a_parts)
    return longer[: len(shorter)] == shorter


def check_cross_layer_collisions(config, *, what_l2_path=None, what_l2_roots=None,
                                  what_l1_path=None, how_l2_path=None, how_l1_path=None):
    """S30 (§17.4 known limitation): flag any two of the four layers' - or
    What-L2's include_roots candidates' - resolved/proposed paths that are
    equal or nest inside one another. Returns a list of (label_a, label_b,
    path_a, path_b) collisions."""
    paths = _resolved_layer_paths(config, what_l2_path, what_l2_roots, what_l1_path, how_l2_path, how_l1_path)
    items = list(paths.items())
    collisions = []
    for i, (label_a, path_a) in enumerate(items):
        for label_b, path_b in items[i + 1:]:
            if _paths_collide_or_nest(path_a, path_b):
                collisions.append((label_a, label_b, path_a, path_b))
    return collisions


def render_collision_section(collisions):
    if not collisions:
        return None
    section = LayerSection("Cross-layer path collisions (S30, D-017/D-018)")
    section.status_lines = [
        "Checked every resolved/proposed layer path (including What-L2's "
        "include_roots candidates) pairwise for equality or nesting. This "
        "check is newly in scope for this package (decision log D-017/D-018) "
        "- it was a named-but-unimplemented gap in the design doc (§17.4's "
        "\"known limitation\", S30)."
    ]
    for label_a, label_b, path_a, path_b in collisions:
        section.decision_lines.append(
            f"collision_decision: PENDING   # ACKNOWLEDGE | CUSTOM: <layer> -> <new path>"
        )
        section.decision_lines.append(
            f"    # {label_a} ('{path_a}') and {label_b} ('{path_b}') collide or nest. "
            f"ACKNOWLEDGE to record the overlap is intentional (e.g. How-L2 living "
            f"inside a What-L2 include_root), or CUSTOM to move one of them."
        )
    return section


# ---------------------------------------------------------------------------
# Top-level discovery + artifact rendering
# ---------------------------------------------------------------------------

def discover_layers(repo_root):
    """Run §17.2-17.4 discovery for all four layers plus the S30 cross-layer
    check. Returns (sections: list[LayerSection], config: dict) - does not
    write anything (discovery is a proposal only, §17.2)."""
    repo_root = Path(repo_root).resolve()
    config = vl.load_yaml_file(repo_root / "context-config.yaml") or {}

    what_l2_section, what_l2_path, what_l2_roots = discover_what_l2(repo_root, config)
    how_l2_section, how_l2_path = discover_how_l2(repo_root, config)
    what_l1_section, what_l1_path = discover_what_l1(repo_root, config)
    how_l1_section, how_l1_path = discover_how_l1(repo_root, config)

    collisions = check_cross_layer_collisions(
        config,
        what_l2_path=what_l2_path, what_l2_roots=what_l2_roots,
        what_l1_path=what_l1_path, how_l2_path=how_l2_path, how_l1_path=how_l1_path,
    )
    collision_section = render_collision_section(collisions)

    sections = [what_l2_section, how_l2_section, what_l1_section, how_l1_section]
    if collision_section:
        sections.append(collision_section)
    return sections, config


def render_discovery_artifact(repo_name, sections):
    lines = [
        f"# Context Layout Discovery - {repo_name}",
        "",
        "Generated by `ult-repo-layout discover` (§17.2). Scoped to this "
        "project's own `context-config.yaml` only.",
        "",
    ]
    for section in sections:
        lines.append(section.render())
        lines.append("")
    lines.append(
        "## How to confirm\n\n"
        "1. Edit every `PENDING` field above. `NOTICE:` lines have none - "
        "there is nothing to edit for a layer discovery already confirmed "
        "is correct.\n"
        "2. Run `ult-repo-layout confirm-layers`.\n"
    )
    return "\n".join(lines)


def run_discovery(repo_root, repo_name=None):
    """Run discovery and write context-layout-discovery.md at
    `{workspace_root}/` if set (well-formed), else repo root (§17.2's
    placement convention, mirroring context-config.yaml)."""
    repo_root = Path(repo_root).resolve()
    sections, config = discover_layers(repo_root)
    wr = vl._normalize_workspace_root(config)
    out_dir = (repo_root / wr) if wr and wr != "." else repo_root
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "context-layout-discovery.md"
    artifact = render_discovery_artifact(repo_name or repo_root.name, sections)
    out_path.write_text(artifact, encoding="utf-8")
    return out_path, artifact


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", nargs="?", default=".", help="repo root (default: .)")
    args = parser.parse_args(argv)

    out_path, _artifact = run_discovery(args.repo_root)
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
