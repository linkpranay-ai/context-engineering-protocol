#!/usr/bin/env python3
"""
Generate the "Adapted content" section of NOTICE from skill frontmatter.

Scans every .github/skills/*/SKILL.md for a non-empty `adapted_from` field
and lists it with its `upstream_version` and `released` date, so contributors
who adapt content from elsewhere only need to fill in their skill's
frontmatter honestly -- this is the mechanism that keeps NOTICE in sync,
not something maintained by hand.

Usage:
  python catalog/generate_notice.py           # print the generated section
  python catalog/generate_notice.py --write   # rewrite NOTICE in place
  python catalog/generate_notice.py --check   # exit 1 if NOTICE is stale (CI)

The generated block lives between two markers in NOTICE:
  <!-- ADAPTED-CONTENT:START --> ... <!-- ADAPTED-CONTENT:END -->
Everything outside those markers (copyright line, third-party components) is
left untouched.
"""
import re
import sys
from pathlib import Path

LIBRARY_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = LIBRARY_ROOT / ".github" / "skills"
NOTICE_PATH = LIBRARY_ROOT / "NOTICE"
FRONTMATTER_RE = re.compile(r"^---\s*\r?\n(.*?)\r?\n---", re.DOTALL)

START_MARKER = "<!-- ADAPTED-CONTENT:START -->"
END_MARKER = "<!-- ADAPTED-CONTENT:END -->"


def field(fm_text, name):
    m = re.search(rf"^{name}:\s*(.+)$", fm_text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def is_empty(value):
    return value in ("", "~", "null", "None")


def collect_adapted_skills():
    adapted = []
    for path in sorted(SKILLS_DIR.rglob("SKILL.md")):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        m = FRONTMATTER_RE.match(text)
        if not m:
            continue
        fm = m.group(1)
        adapted_from = field(fm, "adapted_from")
        if is_empty(adapted_from):
            continue
        adapted.append({
            "name": field(fm, "name") or path.parent.name,
            "adapted_from": adapted_from,
            "upstream_version": field(fm, "upstream_version") or "unknown",
            "released": field(fm, "released") or "unknown",
        })
    return adapted


def render_section(adapted):
    lines = [START_MARKER]
    if not adapted:
        lines.append("No adapted content at this time -- every skill in this repo is")
        lines.append("ground-up (`origin: ground-up`, `adapted_from: ~`).")
    else:
        for entry in adapted:
            lines.append(f"{entry['name']}")
            lines.append(f"  Adapted from: {entry['adapted_from']} (version {entry['upstream_version']})")
            lines.append(f"  First released in this repo: {entry['released']}")
            lines.append("")
        if lines[-1] == "":
            lines.pop()
    lines.append(END_MARKER)
    return "\n".join(lines)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--print"
    adapted = collect_adapted_skills()
    generated = render_section(adapted)

    current = NOTICE_PATH.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.DOTALL
    )
    if not pattern.search(current):
        print(f"NOTICE is missing {START_MARKER}/{END_MARKER} markers.", file=sys.stderr)
        return 1
    updated = pattern.sub(generated, current)

    if mode == "--check":
        if updated != current:
            print("NOTICE is stale -- run `python catalog/generate_notice.py --write`.")
            return 1
        print("NOTICE is up to date.")
        return 0
    if mode == "--write":
        NOTICE_PATH.write_text(updated, encoding="utf-8")
        print("NOTICE updated.")
        return 0

    print(generated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
