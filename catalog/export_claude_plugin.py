#!/usr/bin/env python3
"""
Build the Claude Code plugin package for this repo's skill library, so the
real skills can be installed via Claude Code's plugin/marketplace flow
without hand-copying files or letting the package drift from
.github/skills/, the single source of truth.

Usage:
  python catalog/export_claude_plugin.py           # print a summary of what would change
  python catalog/export_claude_plugin.py --write   # write the generated plugin package to disk
  python catalog/export_claude_plugin.py --check   # exit 1 if the package is stale (CI)

Ownership: everything under claude-plugin/ is generated -- do not hand-edit.
Run with --write after adding, removing, or changing a skill, or after a new
CHANGELOG.md release heading is added.

`demo-consume-context` is deliberately excluded (EXCLUDED_SKILLS below) -- its
own frontmatter marks it "do NOT use for real feature work", so it has no
place in an installable package (ROADMAP.md Section 5, "Plugin manifest skill
set", Option C). Every other skill under .github/skills/ is included, using
`git ls-files` per skill directory so local-only build artifacts
(__pycache__, etc.) never leak into the package.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

LIBRARY_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = LIBRARY_ROOT / ".github" / "skills"
CHANGELOG_PATH = LIBRARY_ROOT / "CHANGELOG.md"
PLUGIN_DIR = LIBRARY_ROOT / "claude-plugin"
PLUGIN_MANIFEST_PATH = PLUGIN_DIR / ".claude-plugin" / "plugin.json"
PLUGIN_SKILLS_DIR = PLUGIN_DIR / "skills"
PLUGIN_README_PATH = PLUGIN_DIR / "README.md"

REPO_URL = "https://github.com/linkpranay-ai/context-engineering-protocol"
PLUGIN_NAME = "context-engineering-protocol"
PLUGIN_DESCRIPTION = (
    "Source-cited, human-approved context packages (code graph + requirements + "
    "conventions) for AI coding agents -- assembled before a generation task runs, "
    "not guessed at afterward."
)
# Foregrounded per ROADMAP.md Section 5's "Plugin manifest skill set" decision
# (Option C): ult-context-generate is the centerpiece skill a first-time
# installer should try first; the rest are supporting tools, listed after.
FOREGROUNDED_SKILL = "ult-context-generate"
EXCLUDED_SKILLS = {"demo-consume-context"}

FRONTMATTER_RE = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n", re.DOTALL)
VERSION_HEADING_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)


def field(fm_text, name):
    m = re.search(rf"^{name}:\s*(.+)$", fm_text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def load_skill_description(skill_dir_name):
    text = (SKILLS_DIR / skill_dir_name / "SKILL.md").read_text(encoding="utf-8-sig", errors="replace")
    m = FRONTMATTER_RE.match(text)
    fm = m.group(1) if m else ""
    return field(fm, "description").strip('"')


def current_version():
    """First released (non-Unreleased) version heading in CHANGELOG.md."""
    text = CHANGELOG_PATH.read_text(encoding="utf-8")
    m = VERSION_HEADING_RE.search(text)
    if not m:
        raise SystemExit("export_claude_plugin: no released version heading found in CHANGELOG.md")
    return m.group(1)


def included_skill_dirs():
    return sorted(
        p.name for p in SKILLS_DIR.iterdir()
        if p.is_dir() and p.name not in EXCLUDED_SKILLS and (p / "SKILL.md").exists()
    )


def tracked_skill_files(skill_dir_name):
    """Git-tracked file paths (relative to the skill dir) for one skill --
    excludes local-only build artifacts (e.g. __pycache__) that git ignores.
    -z/NUL-splits rather than reading newline-delimited output, since a
    plain `git ls-files` quotes (and octal-escapes) any path containing a
    non-ASCII byte by default -- -z always prints paths raw, so a real
    file never gets missed here because its path merely looked unusual.
    encoding="utf-8" is explicit too: git always writes path bytes as
    UTF-8, but text=True alone decodes via the platform's locale encoding,
    which on Windows is a codepage (e.g. cp1252) that mangles anything
    outside it -- without this, -z fixes the quoting but the decode step
    would still corrupt the same non-ASCII paths it was meant to preserve.
    """
    skill_path = SKILLS_DIR / skill_dir_name
    out = subprocess.run(
        ["git", "-C", str(LIBRARY_ROOT), "ls-files", "-z", "--", str(skill_path)],
        capture_output=True, text=True, check=True, encoding="utf-8",
    ).stdout
    rel_root_len = len(skill_path.relative_to(LIBRARY_ROOT).as_posix()) + 1
    return sorted(Path(entry[rel_root_len:]) for entry in out.split("\0") if entry)


def render_manifest(version):
    manifest = {
        "name": PLUGIN_NAME,
        "version": version,
        "description": PLUGIN_DESCRIPTION,
        "author": {"name": "Pranay Mishra"},
        "homepage": REPO_URL,
        "repository": REPO_URL,
        "license": "Apache-2.0",
        "keywords": ["context-engineering", "code-graph", "requirements", "human-approval"],
    }
    return (json.dumps(manifest, indent=2) + "\n").encode("utf-8")


def render_readme(skill_dirs):
    foregrounded = [d for d in skill_dirs if d == FOREGROUNDED_SKILL]
    supporting = [d for d in skill_dirs if d != FOREGROUNDED_SKILL]
    lines = [
        f"# {PLUGIN_NAME}",
        "",
        PLUGIN_DESCRIPTION,
        "",
        "## Start here",
        "",
    ]
    for d in foregrounded:
        lines.append(f"- **`/{PLUGIN_NAME}:{d}`** -- {load_skill_description(d)}")
    lines += ["", "## Supporting skills", ""]
    for d in supporting:
        lines.append(f"- `/{PLUGIN_NAME}:{d}` -- {load_skill_description(d)}")
    lines += [
        "",
        "Generated by `catalog/export_claude_plugin.py` from `.github/skills/` -- do not "
        "hand-edit; run `python catalog/export_claude_plugin.py --write` after adding, "
        "removing, or changing a skill.",
        "",
    ]
    return ("\n".join(lines)).encode("utf-8")


def plan():
    """Return (entries, expected_paths) where entries is [(path, expected_bytes)]
    for every generator-owned file, and expected_paths is the full set of paths
    that should exist under PLUGIN_DIR once written (used to prune extras).
    """
    version = current_version()
    skill_dirs = included_skill_dirs()

    entries = [
        (PLUGIN_MANIFEST_PATH, render_manifest(version)),
        (PLUGIN_README_PATH, render_readme(skill_dirs)),
    ]
    for skill_dir in skill_dirs:
        src_root = SKILLS_DIR / skill_dir
        dst_root = PLUGIN_SKILLS_DIR / skill_dir
        for rel_path in tracked_skill_files(skill_dir):
            src = src_root / rel_path
            if not src.is_file():
                # tracked_skill_files() reflects git's index, not the
                # worktree -- a file tracked in git but removed from disk
                # without `git rm` (or staged for deletion but not yet
                # committed) would otherwise crash this read_bytes() call
                # with a raw FileNotFoundError traceback instead of a
                # message that says what's actually wrong.
                raise SystemExit(
                    f"export_claude_plugin: {src.relative_to(LIBRARY_ROOT).as_posix()} "
                    "is tracked by git but missing on disk -- run `git status` to "
                    "investigate before regenerating claude-plugin/."
                )
            entries.append((dst_root / rel_path, src.read_bytes()))

    expected_paths = {path for path, _ in entries}
    return entries, expected_paths


def existing_plugin_files():
    """Git-tracked file paths under claude-plugin/ that still exist on disk
    -- same git ls-files technique as tracked_skill_files(), so local-only
    build artifacts (__pycache__, .pytest_cache, etc.) picked up by an
    rglob("*") walk never show up as false "extra" files under --check.
    -z/NUL-splits and the explicit encoding="utf-8" are for the same
    non-ASCII-path reason as tracked_skill_files() -- see its docstring.
    Trade-off: an untracked file that also isn't gitignored (e.g. added by
    hand and never `git add`ed) is no longer flagged as extra either --
    fine for CI's fresh checkout, where every real file is tracked. The
    is_file()-or-is_symlink() filter below also covers a path that's
    tracked in the index but was deleted from disk without `git rm`, so
    --write's cleanup pass never tries to unlink a path that isn't there
    at all; is_symlink() is included alongside is_file() so a tracked
    symlink whose target is missing (is_file() alone would call that
    "not there" too, since it follows the link) still comes back and gets
    cleaned up, rather than silently surviving --write forever.
    """
    if not PLUGIN_DIR.exists():
        return set()
    out = subprocess.run(
        ["git", "-C", str(LIBRARY_ROOT), "ls-files", "-z", "--", str(PLUGIN_DIR)],
        capture_output=True, text=True, check=True, encoding="utf-8",
    ).stdout
    candidates = (LIBRARY_ROOT / entry for entry in out.split("\0") if entry)
    return {path for path in candidates if path.is_file() or path.is_symlink()}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--print"
    entries, expected_paths = plan()
    extras = existing_plugin_files() - expected_paths

    stale = [(path, expected) for path, expected in entries if not path.exists() or path.read_bytes() != expected]

    rel = lambda p: p.relative_to(LIBRARY_ROOT).as_posix()

    if mode == "--check":
        problems = list(stale) + [(path, None) for path in extras]
        if problems:
            print("Stale, missing, or extra Claude Code plugin package file(s):")
            for path, _ in sorted(problems, key=lambda item: rel(item[0])):
                print(f"  {rel(path)}")
            print("Run `python catalog/export_claude_plugin.py --write` to regenerate.")
            return 1
        print(f"claude-plugin/ is up to date ({len(entries)} file(s)).")
        return 0

    if mode == "--write":
        for path, expected in entries:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)
        for path in extras:
            path.unlink()
        print(f"Wrote {len(entries)} file(s) to claude-plugin/, removed {len(extras)} extra file(s).")
        return 0

    stale_paths = {path for path, _ in stale}
    print(f"{len(entries)} file(s) would be generated for claude-plugin/:")
    for path, _ in entries:
        marker = " (stale/missing)" if path in stale_paths else ""
        print(f"  {rel(path)}{marker}")
    if extras:
        print(f"\n{len(extras)} extra file(s) not expected (would be removed by --write):")
        for path in sorted(extras, key=rel):
            print(f"  {rel(path)}")
    if stale or extras:
        print("\nRun with --write to update.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
