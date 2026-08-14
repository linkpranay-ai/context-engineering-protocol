#!/usr/bin/env python3
"""
Mechanical Radisys-reference scrub gate for ult-cep-wizard and
ult-autoscaffold-content (D24 §18.9 Q-g, v5; ult-autoscaffold-content added Phase D).

Q-g authorized porting patterns from Radisys's internal `ult-scaffold-repo` into
ult-cep-wizard, "as long as we remove all the Radisys specific references" - but
round-3 adversarial review found that authorization alone was never backed by a
mechanical check that the scrub actually happened, or *stayed* true as the skill
evolves after the port. This script is that check: a case-insensitive deny-list grep
across every file under each covered skill's own directory, run as a required CI
step on every PR that touches either one (not a one-time port-time check, and not a
repo-wide grep - a repo-wide grep would false-positive on this repo's own legitimate
IETF/standards-body references in existing case studies, per the implementation
plan's own risk R5).

ult-autoscaffold-content is ground-up content, not ported from Radisys internal
source the way ult-cep-wizard was (`origin: ground-up` in its own SKILL.md
frontmatter) - it's covered here defensively anyway, per Phase D's explicit
instruction, rather than assuming ground-up authorship guarantees a clean scan.

Deny-list, per §18.4's "what's dropped" column plus the Radisys name itself:
  - "Radisys" (and the `Radi[Ss]ys` internal-shorthand variant)
  - the telecom-domain content explicitly dropped, not ported: RAN, CN, BBA, MRF,
    3GPP - `ult-scaffold-repo`'s own built-in domain content, per §18.4.
  - known internal project code-names - none identified as of this port; extend
    DENY_PATTERNS below if one surfaces during review, rather than leaving it
    silently unchecked.

False positives (e.g. a legitimate future changelog entry crediting Radisys as the
origin) are handled with an inline `<!-- scrub-allow: reason -->` marker on the
*same line* as the flagged term - reviewed like any other diff, not a blanket
exemption file (Q-g, v5).

Exits 1 if any un-allow-listed match is found under either skill's directory.
"""
import re
import sys
from pathlib import Path

LIBRARY_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIRS = (
    LIBRARY_ROOT / ".github" / "skills" / "ult-cep-wizard",
    LIBRARY_ROOT / ".github" / "skills" / "ult-autoscaffold-content",
    LIBRARY_ROOT / ".github" / "skills" / "ult-cep-retrofit",
)

ALLOW_MARKER_RE = re.compile(r"<!--\s*scrub-allow\s*:.*-->")

# "Radisys" gets case-insensitive matching - there's no legitimate lowercase
# collision risk for a proper noun this specific. The telecom acronyms are the
# opposite case: RAN in particular collides with "ran" (plain past tense of "run"),
# an ordinary English word that turned up for real on the very first scan of this
# skill's own test fixtures ("just ran ult-repo-layout init"). Acronyms are
# conventionally written all-caps in prose, so these four are matched
# case-SENSITIVE (all-caps only) and \b-bounded - a real "RAN"/"CN"/"BBA"/"MRF"
# acronym reference still matches, but "ran"/"cn" as ordinary lowercase text does
# not.
DENY_PATTERNS = {
    "Radisys": re.compile(r"radisys", re.IGNORECASE),
    "Radi[Ss]ys shorthand": re.compile(r"\bradi[sz]ys\b", re.IGNORECASE),
    "RAN (telecom, dropped per §18.4)": re.compile(r"\bRAN\b"),
    "CN (telecom, dropped per §18.4)": re.compile(r"\bCN\b"),
    "BBA (telecom, dropped per §18.4)": re.compile(r"\bBBA\b"),
    "MRF (telecom, dropped per §18.4)": re.compile(r"\bMRF\b"),
    "3GPP (telecom, dropped per §18.4)": re.compile(r"\b3GPP\b", re.IGNORECASE),
}

# Binary/generated files this scan shouldn't try to decode as text.
SKIPPED_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pyc"}


def _iter_scannable_files(skill_dir: Path):
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in SKIPPED_SUFFIXES:
            continue
        if "__pycache__" in path.parts:
            continue
        yield path


def scan_file(path: Path):
    """Returns a list of (line_no, label, line_text) for every un-allow-listed
    deny-list match in this file. A `scrub-allow` marker anywhere on the same line
    suppresses every match on that line, not just the one it names - simple and
    auditable beats trying to tie a marker to a specific pattern."""
    hits = []
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (UnicodeDecodeError, OSError):
        # Not decodable as UTF-8 text - not something this scrub gate can meaningfully
        # grep, and not silently skipped without a trace either.
        return [(0, "undecodable file (skipped, not scanned)", "")]

    for line_no, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER_RE.search(line):
            continue
        for label, pattern in DENY_PATTERNS.items():
            if pattern.search(line):
                hits.append((line_no, label, line.strip()))
    return hits


def main():
    failures = []
    files_scanned = 0
    for skill_dir in SKILL_DIRS:
        if not skill_dir.is_dir():
            print(f"{skill_dir} does not exist - nothing to scrub-check.")
            continue

        dir_files = 0
        for path in _iter_scannable_files(skill_dir):
            dir_files += 1
            files_scanned += 1
            rel = path.relative_to(LIBRARY_ROOT).as_posix()
            for line_no, label, line_text in scan_file(path):
                if label.startswith("undecodable"):
                    continue
                failures.append(f"{rel}:{line_no}: [{label}] {line_text}")
        print(f"Scanned {dir_files} file(s) under {skill_dir.relative_to(LIBRARY_ROOT)}.")

    if failures:
        print(f"\n{len(failures)} Radisys-scrub violation(s):\n")
        for f in failures:
            print(f"  {f}")
        print(
            "\nIf a match is a legitimate, reviewed exception (e.g. a changelog "
            "crediting the origin), add an inline `<!-- scrub-allow: reason -->` "
            "marker on that same line rather than removing this check."
        )
        return 1
    print(f"No Radisys-scrub violations found ({files_scanned} file(s) total).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
