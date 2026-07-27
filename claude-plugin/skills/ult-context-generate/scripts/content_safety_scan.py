#!/usr/bin/env python3
"""content_safety_scan.py - heuristic scan for ingested content that reads
like instructions rather than data (PROTOCOL.md §2.2).

What-L1 and How-L1 ingest .md content this project didn't author (external
specs, org process standards, optionally MCP-mirrored copies of either).
PROTOCOL.md §2.2 states that content MUST be treated as data to cite, never
as instructions to follow. This script is a best-effort SHOULD-level check
(CONFORMANCE.md) that flags lines worth a second look before a package
assembler or human reviewer reads them - informational only, never
auto-blocking, consistent with PROTOCOL.md §3.1's no-automatic-resolution
stance. A flag here is not proof of anything malicious; ordinary process
standards and specs use imperative language ("shall", "must") to describe
their own subject matter, which this script does not attempt to distinguish
from an injection attempt - a human reviewer makes that call, this script
only surfaces candidates.

Python 3 stdlib only (argparse, re, sys, pathlib) - vendorable alongside
md_index.py / content_hash.py, no pip install step.

CLI:
    python content_safety_scan.py <dir-or-file> [--exclude <subpath> ...]
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from md_index import gather_md_files  # noqa: E402

# Deliberately narrow and literal: this heuristic exists to catch the
# clearest injection-style phrasing (instruction-hijack attempts explicitly
# addressed at whatever is processing the file), not to police every
# imperative sentence a spec or process standard legitimately contains.
# Broadening this list trades false positives for a chance at catching more;
# starting narrow keeps the SHOULD-level signal actually worth reading.
_SUSPICIOUS_PATTERNS = [
    re.compile(r"\bignore (?:the )?(?:above|previous|prior|all) instructions\b", re.IGNORECASE),
    re.compile(r"\bdisregard (?:the )?(?:above|previous|prior|all) instructions\b", re.IGNORECASE),
    re.compile(r"\byou (?:are|must|should) now (?:act as|behave as|become)\b", re.IGNORECASE),
    re.compile(r"\bnew instructions?:\s", re.IGNORECASE),
    re.compile(r"\bsystem prompt\b", re.IGNORECASE),
    re.compile(r"\breveal your (?:system prompt|instructions)\b", re.IGNORECASE),
]


def scan_text(text):
    """Return a list of (line_no, line_text, pattern) hits for one file's text.

    1-based line numbers, matching md_index.py's own convention.
    """
    hits = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern in _SUSPICIOUS_PATTERNS:
            if pattern.search(line):
                # One hit per line, even if multiple patterns match --
                # a reviewer only needs to look at the line once.
                hits.append((line_no, line.strip(), pattern.pattern))
                break
    return hits


def scan_path(target, exclude=None):
    """Return {relative_path: [(line_no, line_text, pattern), ...]} for every
    .md file under `target` with at least one hit. Clean files are omitted.
    """
    files, root = gather_md_files(target, exclude=exclude)
    results = {}
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = scan_text(text)
        if hits:
            try:
                rel = str(path.relative_to(root))
            except ValueError:
                rel = str(path)
            results[rel] = hits
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="content_safety_scan.py",
        description="Heuristic scan for ingested .md content that reads "
                    "like instructions rather than data (PROTOCOL.md §2.2). "
                    "Informational only - flags candidates for human review, "
                    "never auto-blocks.",
    )
    parser.add_argument("target", help="Directory or single .md file to scan.")
    parser.add_argument("--exclude", action="append", default=[],
                         metavar="SUBPATH",
                         help="Subtree path relative to <target> to skip "
                              "(directory targets only).")
    args = parser.parse_args(argv)

    results = scan_path(args.target, exclude=args.exclude)

    if not results:
        print("content_safety_scan: no suspicious phrasing found.")
        return 0

    print("content_safety_scan: {} file(s) flagged for human review "
          "(informational only, not a block):".format(len(results)))
    for rel, hits in sorted(results.items()):
        print("\n{}:".format(rel))
        for line_no, line_text, pattern in hits:
            print("  line {}: {}".format(line_no, line_text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
