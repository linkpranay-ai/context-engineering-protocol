#!/usr/bin/env python3
"""wizard_docs.py - read-only discovery of ult-layout-wizard's own project
docs (D24 UI design pass) for the in-app docs viewer.

These docs (PROTOCOL.md, README.md, case-studies/*/CASE-STUDY.md) describe
the CEP protocol itself, not the target repo being onboarded - they always
live next to this skill's own install location, not under `ctx.repo_root`
(the repo the wizard is *running against*, which may be any repo at all).
See `install_root()` below.

Doc IDs are never user-supplied paths: `list_docs()` builds the full closed
set itself by scanning the install root once per call; `wizard_server.py`'s
`/api/docs/{id}` route can only ever return a doc whose ID is already in that
scan (a plain 404 dict-lookup miss otherwise) - the same closed-set posture
`STATIC_ASSETS` already uses for wizard.css/wizard.js. There is no
path-traversal surface here for `wizard_containment.check_containment` to
guard, unlike `wizard_picker.py` (which does take an arbitrary user-supplied
`rel_path` and needs it).

Missing docs are not an error: a future install of this skill copied into an
unrelated consumer repo may not bundle PROTOCOL.md/case-studies/ at all - this
module omits what isn't found rather than failing, matching the project's
fail-closed-but-not-fatal posture elsewhere (a broken layout doesn't crash the
server; a missing doc shouldn't either).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Every real case study but one opens with this exact H1 (grep-confirmed
# against all 9 files) - the one exception (ripgrep-user-stories/CASE-STUDY.md,
# which opens with a yaml fence instead) falls back to its directory slug in
# _case_study_title below, rather than guessing a title from body content.
_CASE_STUDY_H1 = re.compile(r"^#\s*Case Study:\s*(.+?)\s*$", re.MULTILINE)


@dataclass
class DocEntry:
    doc_id: str
    title: str
    kind: str  # "doc" | "case-study"
    path: Path


def install_root() -> Path:
    """Repo root this skill is installed under: four levels up from this file
    (scripts -> ult-layout-wizard -> skills -> .github -> repo root)."""
    return Path(__file__).resolve().parents[4]


def _case_study_title(path: Path, fallback_slug: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return fallback_slug
    match = _CASE_STUDY_H1.search(text)
    return match.group(1) if match else fallback_slug


def list_docs(root: Optional[Path] = None) -> List[DocEntry]:
    """Ordered list of every doc currently available to serve: Protocol,
    README, then one entry per case-studies/*/CASE-STUDY.md sorted by
    directory slug. `root` defaults to install_root() - overridable for
    tests only, never by a request."""
    root = root or install_root()
    docs: List[DocEntry] = []

    protocol = root / "PROTOCOL.md"
    if protocol.is_file():
        docs.append(DocEntry("protocol", "Protocol", "doc", protocol))

    readme = root / "README.md"
    if readme.is_file():
        docs.append(DocEntry("readme", "README", "doc", readme))

    case_studies_dir = root / "case-studies"
    if case_studies_dir.is_dir():
        for child in sorted(case_studies_dir.iterdir(), key=lambda p: p.name.casefold()):
            cs_path = child / "CASE-STUDY.md"
            if not cs_path.is_file():
                continue
            title = _case_study_title(cs_path, fallback_slug=child.name)
            docs.append(DocEntry(f"case-study-{child.name}", title, "case-study", cs_path))

    return docs


def find_doc(doc_id: str, root: Optional[Path] = None) -> Optional[DocEntry]:
    """Looks up one doc by ID against the current scan. Returns None (never
    raises) when doc_id isn't in the closed set - callers 404, mirroring
    every other module's non-distinguishing-failure contract in this
    codebase (see wizard_server.py's _require_session/_try_layout_source)."""
    for entry in list_docs(root):
        if entry.doc_id == doc_id:
            return entry
    return None


def to_json_dict(entries: List[DocEntry]) -> dict:
    return {
        "docs": [
            {"id": e.doc_id, "title": e.title, "kind": e.kind} for e in entries
        ]
    }
