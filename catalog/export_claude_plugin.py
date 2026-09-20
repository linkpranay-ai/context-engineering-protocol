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
import os
import re
import stat
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


def _decode_git_ls_files_z(raw_stdout):
    """Decodes the raw -z/NUL-delimited stdout of a `git ls-files -z` call as
    UTF-8, rather than via subprocess.run(text=True): text=True decodes via
    the platform's locale encoding (a Windows codepage like cp1252, not
    necessarily UTF-8) AND applies universal-newline translation, which would
    turn a literal \\r byte inside a path into \\n -- corrupting the one case
    -z's NUL-delimiting exists to keep intact. Decoding bytes directly
    sidesteps both. In the rare case a tracked path genuinely isn't valid
    UTF-8, fails with a clear message instead of a raw traceback.
    """
    try:
        return raw_stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(
            f"export_claude_plugin: git reported a tracked path that isn't "
            f"valid UTF-8 ({exc}) -- rename the file or investigate with "
            "`git ls-files -z` directly."
        ) from exc


def included_skill_dirs(tracked_by_dir=None):
    """Skill directories to advertise in plugin.json/README.md -- requires
    SKILL.md to be git-tracked, not just present on disk. An untracked
    SKILL.md (e.g. a skill being drafted, never `git add`ed) would
    otherwise get a README entry and a loadable description while
    tracked_skill_files() -- which is git-driven -- exports zero files
    for it, advertising a command that ships nothing.
    Sorted by name (not by Path, whose ordering is locale/platform-dependent
    -- case-insensitive on Windows, case-sensitive on POSIX) so README/plugin
    output is identical across the platforms this repo's CI runs on.
    Accepts an optional dict to record each included dir's tracked_skill_files()
    result into, keyed by dir name -- plan() passes one through so it doesn't
    have to re-run the same `git ls-files` call a second time per skill dir.
    """
    names = []
    for p in sorted(SKILLS_DIR.iterdir(), key=lambda path: path.name):
        if not p.is_dir() or p.name in EXCLUDED_SKILLS:
            continue
        if not (p / "SKILL.md").exists():
            continue
        tracked = tracked_skill_files(p.name)
        if tracked_by_dir is not None:
            tracked_by_dir[p.name] = tracked
        if Path("SKILL.md") not in tracked:
            continue
        names.append(p.name)
    return names


def tracked_skill_files(skill_dir_name):
    """Git-tracked file paths (relative to the skill dir) for one skill --
    excludes local-only build artifacts (e.g. __pycache__) that git ignores.
    -z/NUL-splits rather than reading newline-delimited output, since a
    plain `git ls-files` quotes (and octal-escapes) any path containing a
    non-ASCII byte by default -- -z always prints paths raw, so a real
    file never gets missed here because its path merely looked unusual.
    See _decode_git_ls_files_z() for why the output is decoded manually
    rather than via subprocess.run(text=True).
    """
    skill_path = SKILLS_DIR / skill_dir_name
    out = _decode_git_ls_files_z(subprocess.run(
        ["git", "-C", str(LIBRARY_ROOT), "ls-files", "-z", "--", str(skill_path)],
        capture_output=True, check=True,
    ).stdout)
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
    tracked_by_dir = {}
    skill_dirs = included_skill_dirs(tracked_by_dir)

    entries = [
        (PLUGIN_MANIFEST_PATH, render_manifest(version)),
        (PLUGIN_README_PATH, render_readme(skill_dirs)),
    ]
    for skill_dir in skill_dirs:
        src_root = SKILLS_DIR / skill_dir
        dst_root = PLUGIN_SKILLS_DIR / skill_dir
        for rel_path in tracked_by_dir[skill_dir]:
            src = src_root / rel_path
            if src.is_symlink():
                if not src.exists():
                    # A tracked symlink whose target no longer exists looks
                    # exactly like a missing file to is_file() (it follows the
                    # link), but "run `git status`" is bad advice there -- the
                    # symlink itself IS on disk and git sees nothing wrong;
                    # it's the target that's gone. Flagged separately so the
                    # message points at the actual problem. (exists() also
                    # returns False on a symlink loop -- same message covers
                    # that case too, since the fix is the same either way.)
                    raise SystemExit(
                        f"export_claude_plugin: {src.relative_to(LIBRARY_ROOT).as_posix()} "
                        "is a tracked symlink whose target is missing or unreadable "
                        "(e.g. a symlink loop) -- fix or remove the symlink before "
                        "regenerating claude-plugin/."
                    )
                if not src.is_file():
                    # A symlink whose target exists but isn't a regular file
                    # (a directory, a gitlink/submodule) -- is_file() alone
                    # would fall through to the generic "missing on disk"
                    # branch below, which is equally wrong: git sees nothing
                    # missing, the symlink resolves fine, it just doesn't
                    # point at something this tool can read as a file.
                    raise SystemExit(
                        f"export_claude_plugin: {src.relative_to(LIBRARY_ROOT).as_posix()} "
                        "is a tracked symlink that resolves to something other than "
                        "a regular file -- fix or remove the symlink before "
                        "regenerating claude-plugin/."
                    )
            elif not src.is_file():
                # tracked_skill_files() reflects git's index, not the
                # worktree -- a file tracked in git but removed from disk
                # without `git rm` would otherwise crash this read_bytes()
                # call with a raw FileNotFoundError traceback instead of a
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
    -z/NUL-splits and the manual UTF-8 decode are for the same non-ASCII-
    path reason as tracked_skill_files() -- see its docstring.
    Trade-off: an untracked file that also isn't gitignored (e.g. added by
    hand and never `git add`ed) is no longer flagged as extra either --
    fine for CI's fresh checkout, where every real file is tracked. The
    is_file()-or-_is_reparse_point() filter below also covers a path that's
    tracked in the index but was deleted from disk without `git rm`, so
    --write's cleanup pass never tries to unlink a path that isn't there
    at all; _is_reparse_point() is included alongside is_file() so a tracked
    symlink or junction whose target is missing (is_file() alone would call
    that "not there" too, since it follows the link) still comes back and
    gets cleaned up, rather than silently surviving --write forever.
    """
    if not PLUGIN_DIR.exists():
        return set()
    out = _decode_git_ls_files_z(subprocess.run(
        ["git", "-C", str(LIBRARY_ROOT), "ls-files", "-z", "--", str(PLUGIN_DIR)],
        capture_output=True, check=True,
    ).stdout)
    candidates = (LIBRARY_ROOT / entry for entry in out.split("\0") if entry)
    return {path for path in candidates if path.is_file() or _is_reparse_point(path)}


def _is_reparse_point(path):
    """True if `path` itself -- not whatever it points at -- is a symlink
    (POSIX or Windows) or a Windows junction.

    Path.is_symlink() alone misses a junction: on Windows a junction is
    implemented as a reparse point exactly like a symlink is, but
    Path.is_symlink() (verified empirically on Python 3.12/Windows) returns
    False for one. Every "is this path a redirection rather than an
    ordinary file/directory this generator owns" check in this module needs
    both tests, not is_symlink() alone -- a junction left under
    claude-plugin/ would otherwise walk straight past all of them. On POSIX
    there's no separate junction concept, so is_symlink() alone is already
    complete and the attribute check is skipped.
    """
    if path.is_symlink():
        return True
    if os.name != "nt":
        return False
    try:
        attrs = os.lstat(path).st_file_attributes
    except OSError:
        return False
    return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _first_symlink_under_plugin_dir(path):
    """Returns the first symlink or junction from PLUGIN_DIR down to `path`
    inclusive (PLUGIN_DIR itself, then each ancestor component, then
    `path`), or None if none of them is one.

    Every path under claude-plugin/ is generator-owned (see module
    docstring), so a symlink or junction anywhere in that tree -- not just
    at the leaf -- is already anomalous: `path.parent.mkdir(parents=True,
    exist_ok=True)` would silently walk through a redirected ancestor
    directory and write outside claude-plugin/ entirely, before a
    leaf-only check ever ran. That includes PLUGIN_DIR itself being one,
    which is checked first for the same reason. Checking every component
    closes that gap, and reusing the same check for --check's staleness
    test closes the matching gap there: a redirection whose target's
    content happens to match `expected` would otherwise pass
    `path.read_bytes() != expected` and never get flagged, even though the
    path itself still isn't the generator-owned regular file it's supposed
    to be.
    """
    if _is_reparse_point(PLUGIN_DIR):
        return PLUGIN_DIR
    cursor = PLUGIN_DIR
    for part in path.relative_to(PLUGIN_DIR).parts:
        cursor = cursor / part
        if _is_reparse_point(cursor):
            return cursor
        if not cursor.exists():
            break
    return None


def _is_windows_directory_symlink(path):
    """True if the entry at `path` itself has Windows' FILE_ATTRIBUTE_DIRECTORY
    bit set, on Windows; always False on POSIX.

    Callers must already know `path` is a symlink or junction (e.g. via
    _is_reparse_point()) before calling this -- it only distinguishes a
    directory-type reparse point from a file-type one, and returns True for
    an ordinary directory that isn't a reparse point at all too (see
    TestIsWindowsDirectorySymlink.test_windows_directory_entry_is_true),
    since it never itself checks FILE_ATTRIBUTE_REPARSE_POINT.

    Reads the attribute off the link itself via `os.lstat` (which does not
    follow the link), rather than following it with `Path.is_dir()` -- a
    *broken* directory symlink or junction (target deleted or looping)
    still needs rmdir(), but `is_dir()` can't tell, since it has nothing
    left to follow and inspect and simply returns False. On POSIX a symlink
    is never itself a directory entry regardless of what it points at, so
    this is unconditionally False there and the caller always uses
    unlink().
    """
    if os.name != "nt":
        return False
    return bool(os.lstat(path).st_file_attributes & stat.FILE_ATTRIBUTE_DIRECTORY)


def _remove_plugin_owned_path(path):
    """Remove a generator-owned path that must go before mkdir()/
    write_bytes() can safely run again -- either a stray symlink/junction
    found in a generated path's ancestry, or an extra tracked file left
    over (itself possibly a symlink/junction) from a previous --write.

    Dispatches rmdir() vs unlink() by _is_windows_directory_symlink()
    (platform plus the entry's own directory-attribute bit) rather than
    Path.is_dir(), which follows the link and would misjudge a *broken*
    directory symlink/junction as not-a-directory, since it has no target
    left to inspect -- unlink() unconditionally raises PermissionError on
    a plain directory, so a broken one misjudged that way would crash
    here. (On a *live* Windows junction, unlink() alone was empirically
    found to also succeed here -- CPython's os.unlink() falls back to
    RemoveDirectoryW internally -- but this module doesn't depend on that
    undocumented fallback existing, covering every Python version, or
    extending to an actual directory *symlink*, which this dev machine has
    no privilege to construct and check directly.) On POSIX, rmdir() alone
    raises NotADirectoryError on a symlink to a directory, since POSIX
    rmdir() does not follow a trailing symlink -- _is_windows_directory_symlink()
    is False unconditionally on POSIX, so unlink() is always chosen there,
    which is always correct since a POSIX symlink is never itself a
    directory entry regardless of what it points at.
    """
    if _is_windows_directory_symlink(path):
        path.rmdir()
    else:
        path.unlink()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--print"
    entries, expected_paths = plan()
    extras = existing_plugin_files() - expected_paths

    stale = [
        (path, expected)
        for path, expected in entries
        # Symlink/junction check first: a leaf path that's one pointing at a
        # directory still has path.exists() == True, so path.read_bytes()
        # would run next and raise IsADirectoryError (POSIX) or
        # PermissionError (Windows) uncaught, instead of this loop cleanly
        # reporting the path as stale.
        if _first_symlink_under_plugin_dir(path) is not None
        or not path.exists()
        or path.read_bytes() != expected
    ]

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
            # Checked (and removed) BEFORE mkdir, not after: every path
            # under claude-plugin/ is generator-owned (see module
            # docstring), so a symlink or junction anywhere in this path's
            # ancestry -- not just at the leaf -- is already anomalous.
            # mkdir(parents=True) would otherwise silently walk through a
            # redirected ancestor directory (writing outside claude-plugin/
            # entirely) before a leaf-only check ever ran; write_bytes() on
            # a redirected leaf would do the same for the file itself.
            # Removing the first one found in the chain, PLUGIN_DIR down to
            # the leaf, before mkdir runs keeps --write's output confined to
            # the tree it's supposed to own either way. See
            # _remove_plugin_owned_path()'s docstring for why this can't
            # just be unlink().
            stray_symlink = _first_symlink_under_plugin_dir(path)
            if stray_symlink is not None:
                _remove_plugin_owned_path(stray_symlink)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)
        for path in extras:
            _remove_plugin_owned_path(path)
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
