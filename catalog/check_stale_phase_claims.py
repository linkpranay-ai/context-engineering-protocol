#!/usr/bin/env python3
"""
Stale forward-looking-phase-claim gate, repo-wide.

This repo has a recurring defect class, closed piecemeal across ten separate
commits (`740dada`, `6c61e2c`, `1561cd4`, `8714873`, `a0e1a93`, `785af44`, and
others): a docstring or comment says a route/module/feature "doesn't exist
yet", is "disabled by design", or belongs to "a future Phase N" - true when
written, false the moment that phase actually lands, because nothing ever
forces the prose to be revisited. Every one of those ten commits was a manual
adversarial-review catch, months after the phase in question had shipped. The
Round 4 rerun's handoff explicitly asked for a mechanical version of that
catch instead of relying on the next adversarial sweep to notice by hand.

This is not a general prose linter - it is deliberately narrow, calibrated
against the exact phrasing those ten commits removed (see each commit's diff
for the original wording). A bare phrase like "doesn't exist yet" is *not* on
the list: grepping the live tree at authoring time showed that exact string
in dozens of legitimate, permanently-true sentences about filesystem state
("the file doesn't exist yet", "an empty skeleton if it doesn't exist yet") -
completely unrelated to a feature or phase not having landed. Every pattern
below was checked against the current tree (`git ls-files` over `.py`/`.js`/
`.md`/`.html`) and produces zero hits - so a fresh false positive here means
new prose actually resembles a past staleness bug, not that the checker is
noisy.

A handful of prior legitimate uses of nearby words (e.g. D22's "a deferred
follow-on, not yet implemented" in `references/design-scratchpad-glossary.md`,
which really is unimplemented) are not matched by these patterns; if a future
legitimate use ever does collide with one, mark it in place with an inline
`<!-- stale-phase-claim-allow: reason -->` on that line rather than loosening
the pattern for everyone, mirroring `check_private_refs.py`'s own convention.

Exits 1 if any un-allow-listed match is found anywhere in the tracked working
tree's `.py`, `.js`, `.md`, or `.html` files.
"""
import re
import subprocess
import sys
from pathlib import Path

LIBRARY_ROOT = Path(__file__).resolve().parent.parent
THIS_SCRIPT = Path(__file__).resolve()
# This script's own unit tests necessarily write each denylisted phrase into
# fixture content, to prove `scan_file`/`run_check` actually catch it - the
# check exercising itself, not a real stale claim. Exempted by path (relative
# to whatever root is being scanned, so this is testable against a disposable
# fixture repo the same way the rest of `run_check` is), the same convention
# `check_private_refs.py` uses for its own test fixture.
THIS_SCRIPTS_TEST_FILE_REL = "catalog/tests/test_check_stale_phase_claims.py"

# Extensions this check applies to - per the task this gate exists for:
# stale forward-looking claims in Python/JS comments and docstrings, and in
# markdown prose (SKILL.md files, references/, case studies, and the
# wizard's own served static/index.html - the same directory that produced
# one of the ten historical fix commits, 6c61e2c, in its sibling wizard.js).
SCANNED_SUFFIXES = {".py", ".js", ".md", ".html"}

# Each pattern is calibrated against real wording removed by one of the ten
# historical stale-phase-claim fix commits, narrowed just enough that it does
# not also match this repo's extremely common *legitimate* references to a
# named phase ("D24 Phase 1", "Phase 0", "Phase C") or to ordinary filesystem
# non-existence ("the file doesn't exist yet"). See the module docstring.
STALE_PHASE_PATTERNS = (
    ("future Phase", re.compile(r"future phase", re.I)),
    # Broader than just "exist until Phase" - also catches the "disabled ...
    # until Phase C" shape from 6c61e2c. Checked against the live tree at
    # authoring time: zero hits outside genuinely stale wording.
    ("until Phase", re.compile(r"until phase\b", re.I)),
    ("disabled by design", re.compile(r"disabled by design", re.I)),
    ("not called by anything yet", re.compile(r"not called by anything yet", re.I)),
    (
        "registers zero mutating routes",
        re.compile(r"registers zero mutating routes", re.I),
    ),
    ("will be the first caller", re.compile(r"will be the first caller", re.I)),
    ("nothing new to design here", re.compile(r"nothing new to design here", re.I)),
    (
        "this release is read-only",
        re.compile(r"\(this release\) is read-only", re.I),
    ),
)

ALLOW_MARKER_RE = re.compile(r"<!--\s*stale-phase-claim-allow\s*:.*-->")


def _tracked_files(library_root: Path):
    """Every `.py`/`.js`/`.md`/`.html` file `git` tracks in `library_root` -
    not a filesystem walk, so untracked scratch files are never in scope.
    -z/NUL-splits rather than reading newline-delimited output, since a plain
    `git ls-files` quotes (and octal-escapes) any path containing a non-ASCII
    byte by default - a file whose path merely looked unusual would otherwise
    come back quoted, fail the `path.is_file()` check below, and get silently
    dropped from this scan rather than checked for a stale phase claim.
    Each -z-delimited entry is used exactly as git printed it, with no
    `.strip()` - unlike newline-delimited output, -z entries carry no
    trailing separator to strip, and a real (if unusual) tracked POSIX
    filename can legitimately contain leading/trailing whitespace or a
    literal \\r; stripping those would corrupt the exact path -z exists to
    keep intact, the same class of bug this function's own non-ASCII-path
    handling exists to avoid. Decoded manually as UTF-8 from raw bytes
    rather than via subprocess.run(text=True), which decodes via the
    platform's locale encoding (a Windows codepage like cp1252, not UTF-8)
    - same reasoning as `export_claude_plugin.py`'s `tracked_skill_files()`;
    fails with a clear message rather than a raw traceback if a tracked
    path genuinely isn't valid UTF-8."""
    raw = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=library_root,
        capture_output=True,
        check=True,
    ).stdout
    try:
        out = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(
            f"check_stale_phase_claims: git reported a tracked path that "
            f"isn't valid UTF-8 ({exc}) -- rename the file or investigate "
            "with `git ls-files -z` directly."
        ) from exc
    for rel in out.split("\0"):
        if not rel:
            continue
        if rel == THIS_SCRIPTS_TEST_FILE_REL:
            continue
        path = library_root / rel
        if not path.is_file():
            continue
        if path.resolve() == THIS_SCRIPT:
            # This module's own docstring necessarily quotes the phrasing it
            # forbids; it is the gate, not a violation of it.
            continue
        if path.suffix.lower() not in SCANNED_SUFFIXES:
            continue
        if "__pycache__" in path.parts:
            continue
        yield path


def scan_file(path: Path):
    """Returns a list of (line_no, pattern_name, line_text) for every
    un-allow-listed stale-phase-claim match in this file. A
    `stale-phase-claim-allow` marker anywhere on the line suppresses every
    match on that line."""
    hits = []
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (UnicodeDecodeError, OSError):
        return []

    for line_no, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER_RE.search(line):
            continue
        for name, pattern in STALE_PHASE_PATTERNS:
            if pattern.search(line):
                hits.append((line_no, name, line.strip()))
    return hits


def run_check(library_root: Path) -> int:
    """Scans every tracked `.py`/`.js`/`.md`/`.html` file under `library_root`
    and returns the process exit code (0 clean, 1 on any un-allow-listed
    match), printing the same report `main()` does. Factored out so tests can
    point this at a disposable fixture repo instead of the real one."""
    failures = []
    files_scanned = 0
    for path in _tracked_files(library_root):
        files_scanned += 1
        rel = path.relative_to(library_root).as_posix()
        for line_no, name, line_text in scan_file(path):
            failures.append(f"{rel}:{line_no}: [{name}] {line_text}")

    if failures:
        print(f"{len(failures)} stale forward-looking-phase-claim violation(s):\n")
        for f in failures:
            print(f"  {f}")
        print(
            "\nThis phrasing matches a recurring defect class this repo has fixed "
            "ten separate times: a comment/docstring saying a route or feature "
            "'doesn't exist yet', is 'disabled by design', or belongs to 'a future "
            "Phase N' - true when written, stale the moment that phase lands. "
            "Update the claim to describe current, landed behavior. If this is a "
            "reviewed, genuinely still-true exception, add an inline "
            "`<!-- stale-phase-claim-allow: reason -->` marker on that same line "
            "rather than removing this check."
        )
        return 1
    print(
        f"No stale forward-looking-phase-claim violations found "
        f"({files_scanned} file(s) scanned)."
    )
    return 0


def main():
    return run_check(LIBRARY_ROOT)


if __name__ == "__main__":
    sys.exit(main())
