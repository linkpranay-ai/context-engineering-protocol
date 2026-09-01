#!/usr/bin/env python3
"""
Private-document reference scrub gate, repo-wide.

The Round-2 adversarial review's finding C-1 was that the original 8-commit fix
sequence, while closing real defects, cited the private evaluation document that
reported those defects (`ISSUES.md`, never committed, never published) by filename
from ~90 sites in tracked skill code, tests, and reference docs - `ISSUES.md Round 2
finding N`. That's a dead end for anyone reading this repo standalone, and it also
implicitly acknowledges the existence of an internal-only evaluation artifact this
repo has no business pointing at. All ~90 sites were rewritten to state the finding's
substance inline (a date plus a plain-English description, no filename) rather than
citing the document; this script is the mechanical gate that keeps that true going
forward, the same way `check_radisys_scrub.py` guards the Radisys-reference scrub.

Unlike `check_radisys_scrub.py` (deliberately scoped to two or three skill
directories, to avoid false-positiving on this repo's own legitimate standards-body
references), this check is repo-wide: every one of these filenames is unpublished and
has no legitimate reason to be named from *any* tracked file, not just skill code.
`ISSUES.md` and `CEP-HANDOFF.md` are private, untracked working files that must never
be committed, pushed, or referenced from inside this repo at all. `CEP_INSTALLATION_REPORT.md`
is the private adversarial-review report those two fed into. `CONTEXT-ENGINEERING-DESIGN.md`
is the pre-existing internal design scratchpad this repo was originally built against
(ROADMAP.md item 15's "pre-1.0 citation cleanup") - already scrubbed once before; kept
in this denylist so a future contributor can't reintroduce the same dead-end citation
under a different feature.

A handful of tracked files legitimately *name* these documents while describing the
past cleanup itself (this docstring, `CONTRIBUTING.md`'s citation note,
`references/design-scratchpad-glossary.md`, the relevant `CHANGELOG.md`/`ROADMAP.md`
entries) - recording that a mistake happened and was fixed is not the mistake. Those
sites carry an inline `<!-- private-ref-allow: reason -->` marker, reviewed like any
other diff line, not a blanket exemption (same discipline `check_radisys_scrub.py`
uses for its own allow marker).

Exits 1 if any un-allow-listed match is found anywhere in the tracked working tree.
"""
import re
import subprocess
import sys
from pathlib import Path

LIBRARY_ROOT = Path(__file__).resolve().parent.parent
THIS_SCRIPT = Path(__file__).resolve()

# Every one of these is an unpublished, non-public document. None has a legitimate
# reason to be cited by filename from tracked content - see the module docstring for
# why each one is here and why bare substring matching (no \b, no case-folding) is
# precise enough: these are specific enough filenames that a real match is never an
# ordinary-English false positive the way "RAN" or "CN" would be.
DENYLIST_FILENAMES = (
    "ISSUES.md",
    "CEP_INSTALLATION_REPORT.md",
    "CEP-HANDOFF.md",
    "CONTEXT-ENGINEERING-DESIGN.md",
)

ALLOW_MARKER_RE = re.compile(r"<!--\s*private-ref-allow\s*:.*-->")

# Binary/generated files this scan shouldn't try to decode as text.
SKIPPED_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pyc"}


def _tracked_files(library_root: Path):
    """Every file `git` tracks in `library_root` - not a filesystem walk, so
    untracked scratch files (including a real `ISSUES.md` or `CEP-HANDOFF.md`
    sitting in a contributor's own working copy, per the standing rule that those
    must never even be added) are never in scope to begin with."""
    out = subprocess.run(
        ["git", "ls-files"],
        cwd=library_root,
        capture_output=True,
        text=True,
        check=True,
    )
    for rel in out.stdout.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        path = library_root / rel
        if not path.is_file():
            continue
        if path.resolve() == THIS_SCRIPT:
            # This module's own docstring/denylist necessarily names every one of
            # these filenames; it is not a citation of the document, it's the gate
            # that forbids citing it.
            continue
        if path.suffix.lower() in SKIPPED_SUFFIXES:
            continue
        if "__pycache__" in path.parts:
            continue
        yield path


def scan_file(path: Path):
    """Returns a list of (line_no, filename, line_text) for every un-allow-listed
    denylist match in this file. A `private-ref-allow` marker anywhere on the same
    line suppresses every match on that line, not just the one it names - simple and
    auditable beats trying to tie a marker to a specific filename."""
    hits = []
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (UnicodeDecodeError, OSError):
        return []

    for line_no, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER_RE.search(line):
            continue
        for name in DENYLIST_FILENAMES:
            if name in line:
                hits.append((line_no, name, line.strip()))
    return hits


def run_check(library_root: Path) -> int:
    """Scans every file `git` tracks under `library_root` and returns the process
    exit code (0 clean, 1 on any un-allow-listed match), printing the same report
    `main()` does. Factored out so tests can point this at a disposable fixture
    repo instead of the real one, without shelling out to a subprocess."""
    failures = []
    files_scanned = 0
    for path in _tracked_files(library_root):
        files_scanned += 1
        rel = path.relative_to(library_root).as_posix()
        for line_no, name, line_text in scan_file(path):
            failures.append(f"{rel}:{line_no}: [{name}] {line_text}")

    if failures:
        print(f"{len(failures)} private-document reference violation(s):\n")
        for f in failures:
            print(f"  {f}")
        print(
            "\nThese filenames are private, unpublished documents (see this "
            "script's module docstring) that must never be cited from tracked "
            "content - state the substance inline instead. If a match is a "
            "legitimate, reviewed exception (e.g. documenting that a past "
            "citation leak was cleaned up), add an inline "
            "`<!-- private-ref-allow: reason -->` marker on that same line "
            "rather than removing this check."
        )
        return 1
    print(f"No private-document reference violations found ({files_scanned} file(s) scanned).")
    return 0


def main():
    return run_check(LIBRARY_ROOT)


if __name__ == "__main__":
    sys.exit(main())
