#!/usr/bin/env python3
"""md_index.py - deterministic, zero-LLM markdown structural indexer.

The "graphify for markdown". Build-once -> write JSON index -> skills query it.
Re-implementation of the deleted ``ast_crossref.py`` (Context Engineering D14),
this time as a real, tested CLI that does NOT get deleted.

Python 3 stdlib only (argparse, re, json, hashlib, pathlib, datetime) so the
script is vendorable for an OSS framework with no pip install step.

CLI:
    python md_index.py index <dir-or-file> -o <out.json> [--profile generic|3gpp] [--stale-check]
        [--exclude <subpath> ...] [--include-root <dir> ...]
    python md_index.py query <index.json> "<term1> <term2> ..." [--top N]
    python md_index.py query-batch <index.json> <queries.json> [--top N]

See scripts/README.md for the JSON schema, profile schema, and the
line-numbering / section-bounds convention.
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0"

# Directory holding the bundled profile pattern-packs.
PROFILES_DIR = Path(__file__).resolve().parent / "profiles"


# --------------------------------------------------------------------------- #
# Profiles                                                                     #
# --------------------------------------------------------------------------- #

def load_profile(name):
    """Load a profile pattern-pack by name from profiles/<name>.json.

    Returns a dict with compiled regexes added under private keys.
    """
    path = PROFILES_DIR / "{}.json".format(name)
    if not path.exists():
        available = sorted(p.stem for p in PROFILES_DIR.glob("*.json"))
        raise SystemExit(
            "Unknown profile '{}'. Available: {}".format(name, ", ".join(available))
        )
    with path.open(encoding="utf-8") as fh:
        prof = json.load(fh)

    prof["_clause_id_re"] = re.compile(prof["clause_id_regex"])
    prof["_cross_ref_res"] = [
        (re.compile(p["regex"], re.IGNORECASE), p["kind"])
        for p in prof.get("cross_ref_patterns", [])
    ]
    prof["_toc_suppress"] = {
        t.strip().lower() for t in prof.get("toc_titles_to_suppress", [])
    }
    return prof


# --------------------------------------------------------------------------- #
# Line reading / normalisation                                                #
# --------------------------------------------------------------------------- #

def read_lines(path):
    """Read a file and return (raw_bytes_for_hash, lines).

    ``lines`` are 0-indexed in the list but every line *number* exposed in the
    output is 1-based. Windows CRLF and lone CR are normalised so regexes that
    anchor on end-of-line behave identically across platforms; the sha256 is
    taken over the *original* bytes so it is a faithful content fingerprint.
    """
    data = path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    # Normalise line endings for parsing only.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    return data, lines


def sha256_of(data_bytes):
    return hashlib.sha256(data_bytes).hexdigest()


# --------------------------------------------------------------------------- #
# Code-block / front-matter masking                                           #
# --------------------------------------------------------------------------- #

_FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})")
_INDENTED_CODE_RE = re.compile(r"^( {4,}|\t)")


def compute_masks(lines):
    """Return (code_mask, front_matter_lines).

    ``code_mask[i]`` is True when 1-based line (i+1) is inside a fenced or
    indented code block, OR inside a detected front-matter block. Masked lines
    are excluded from heading / table-separator detection entirely.

    ``front_matter_lines`` is ``[start, end]`` (1-based, inclusive) of a
    detected front-matter block at the head of the file, or ``None``.

    Front matter recognised:
      * YAML ``---`` ... ``---`` at the very top of the file.
      * An HTML comment block ``<!-- ... -->`` at the very top (TS 33.401 uses
        this for its provenance header).
    """
    n = len(lines)
    mask = [False] * n
    front_matter = None

    # ---- front matter (must be at file head, after optional blank lines) ----
    first = 0
    while first < n and lines[first].strip() == "":
        first += 1

    if first < n:
        stripped = lines[first].strip()
        if stripped == "---":
            # YAML front matter: closes at the next line that is exactly '---'.
            for j in range(first + 1, n):
                if lines[j].strip() == "---":
                    front_matter = [first + 1, j + 1]
                    for k in range(first, j + 1):
                        mask[k] = True
                    break
        elif stripped.startswith("<!--"):
            # HTML-comment header block. Closes at the line containing '-->'.
            if "-->" in lines[first]:
                front_matter = [first + 1, first + 1]
                mask[first] = True
            else:
                for j in range(first + 1, n):
                    if "-->" in lines[j]:
                        front_matter = [first + 1, j + 1]
                        for k in range(first, j + 1):
                            mask[k] = True
                        break

    # ---- fenced code blocks ----
    fm_end = front_matter[1] if front_matter else 0  # 1-based; 0 => none
    in_fence = False
    fence_marker = None
    for i, line in enumerate(lines):
        if i + 1 <= fm_end:
            continue  # already masked as front matter
        m = _FENCE_RE.match(line)
        if not in_fence:
            if m:
                in_fence = True
                fence_marker = m.group(2)[0]  # '`' or '~'
                mask[i] = True
        else:
            mask[i] = True
            # A closing fence uses the same marker char, >= as many chars.
            if m and m.group(2)[0] == fence_marker:
                in_fence = False
                fence_marker = None

    # ---- indented code blocks ----
    # An indented code block requires a preceding blank line (CommonMark): a
    # 4-space indent that merely continues a paragraph or a list item is NOT a
    # code block. We approximate: an indented line is code only if the nearest
    # preceding non-masked line is blank. This keeps Setext underlines (never
    # indented) and ATX headings (never indented) safe while still masking
    # genuine indented code that could contain '#', '---', or '|---|'.
    for i, line in enumerate(lines):
        if mask[i] or in_fence:
            continue
        if _INDENTED_CODE_RE.match(line) and line.strip() != "":
            prev = i - 1
            if prev < 0 or lines[prev].strip() == "":
                mask[i] = True

    return mask, front_matter


# --------------------------------------------------------------------------- #
# Heading detection                                                           #
# --------------------------------------------------------------------------- #

_ATX_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")

# A table-separator row: pipes / dashes / colons / spaces only, with at least
# two consecutive dashes somewhere. Covers '|---|---|', ':--|--:', '---|---',
# and alignment-colon variants. Must contain a dash run and may be pipe-less.
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]*-{2,}[\s:|-]*\|?\s*$")

# Setext underline: a line of only '=' (level 1) or only '-' (level 2).
_SETEXT_UNDER_RE = re.compile(r"^\s*(=+|-+)\s*$")


def is_table_separator(line):
    """True if the line is a markdown pipe-table separator row.

    Distinguished from a Setext H2 underline (which is dashes only, no pipes
    and no colons) by the presence of a pipe or a colon, OR by the structure
    of a multi-column dash row.
    """
    if "|" in line or ":" in line:
        # Any pipe/colon dashed row is a table separator, never a heading.
        return bool(_TABLE_SEP_RE.match(line))
    return False


def detect_headings(lines, mask, profile):
    """Walk the masked line list and produce a list of raw heading dicts.

    Each dict: {style, level, title, line (1-based of the heading TEXT line),
    underline_line (1-based, only for setext else None)}.
    """
    headings = []
    n = len(lines)
    i = 0
    while i < n:
        if mask[i]:
            i += 1
            continue
        line = lines[i]

        # ---- ATX ----
        m = _ATX_RE.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            headings.append({
                "style": "atx",
                "level": level,
                "title": title,
                "line": i + 1,
                "underline_line": None,
            })
            i += 1
            continue

        # ---- Setext ----
        # Current line is the (non-empty, non-masked) title candidate; the NEXT
        # non-masked line must be a pure '='/'-' underline and NOT a table sep.
        text = line.rstrip()
        if text.strip() != "" and i + 1 < n and not mask[i + 1]:
            nxt = lines[i + 1]
            if _SETEXT_UNDER_RE.match(nxt) and not is_table_separator(nxt):
                # Guard: the title candidate itself must not be ATX/table/blank
                # and must not itself look like an underline (avoid '---' over
                # '---'). Also the title line cannot be a list/blockquote start
                # that would normally be a lazy continuation.
                if not _SETEXT_UNDER_RE.match(text) and not is_table_separator(text):
                    underline = nxt.strip()
                    level = 1 if underline[0] == "=" else 2
                    headings.append({
                        "style": "setext",
                        "level": level,
                        "title": text.strip(),
                        "line": i + 1,
                        "underline_line": i + 2,
                    })
                    i += 2
                    continue
        i += 1
    return headings


# --------------------------------------------------------------------------- #
# Clause id + section bounds + cross-refs                                      #
# --------------------------------------------------------------------------- #

# Strip pandoc attribute tails like '{#contents .TT}' from setext titles before
# clause-id / TOC matching.
_ATTR_TAIL_RE = re.compile(r"\s*\{[^}]*\}\s*$")


def clean_title(title):
    return _ATTR_TAIL_RE.sub("", title).strip()


def parse_clause_id(title, profile):
    """Return (clause_id or None, display_title). Profile-driven."""
    m = profile["_clause_id_re"].match(title)
    if m:
        return m.group(1), m.group(2).strip()
    return None, title


def compute_section_bounds(headings, total_lines):
    """Set section_bounds on each heading in place.

    Convention (documented in README): section_bounds = [content_start,
    content_end], 1-based inclusive, where:
        content_start = heading text line + 1, and +1 again for a Setext
                        underline (so the bound begins at the first BODY line,
                        excluding both the title and its underline).
        content_end   = (line of the next heading at the SAME-OR-HIGHER level) - 1,
                        EOF-clamped.
    If a section has no body (next heading immediately follows), content_start
    may exceed content_end; we clamp to an empty range [content_start,
    content_start - 1] -> represented as [content_start, content_start - 1].
    """
    n = len(headings)
    for idx, h in enumerate(headings):
        if h["style"] == "setext":
            content_start = h["underline_line"] + 1
        else:
            content_start = h["line"] + 1

        # Find next heading at same or higher level (level <= current level).
        end_line = total_lines  # EOF default (1-based last line)
        for j in range(idx + 1, n):
            if headings[j]["level"] <= h["level"]:
                end_line = headings[j]["line"] - 1
                break

        if end_line < content_start:
            end_line = content_start - 1  # empty section
        h["section_bounds"] = [content_start, end_line]


def build_clause_index(headings):
    """Map clause_id -> heading id (first occurrence wins)."""
    index = {}
    for h in headings:
        cid = h.get("clause_id")
        if cid and cid not in index:
            index[cid] = h["id"]
    return index


def find_cross_refs(body_text, profile, clause_index):
    """Find and resolve cross-references in a section body.

    Returns a de-duplicated list of cross_ref dicts. Resolution is single-hop,
    same-file: a ref resolves only if its target clause id is a heading in THIS
    file. Unresolved refs are kept with resolved=False (never guessed).
    """
    seen = {}
    for regex, kind in profile["_cross_ref_res"]:
        for m in regex.finditer(body_text):
            raw = m.group(0).strip()
            target = m.group(1)
            if kind == "annex":
                # 'Annex A.3' -> clause id 'A.3'; 'Annex E' -> 'E'.
                target_clause = target
            else:
                target_clause = target
            key = (raw.lower(), target_clause)
            if key in seen:
                continue
            resolved_id = clause_index.get(target_clause)
            seen[key] = {
                "raw": raw,
                "kind": kind,
                "target_clause": target_clause,
                "resolved_heading_id": resolved_id,
                "resolved": resolved_id is not None,
            }
    return list(seen.values())


# --------------------------------------------------------------------------- #
# Per-file parsing                                                             #
# --------------------------------------------------------------------------- #

def parse_file(path, root, profile):
    """Parse a single markdown file into the file-entry dict for the index."""
    data_bytes, lines = read_lines(path)
    mask, front_matter = compute_masks(lines)
    raw_headings = detect_headings(lines, mask, profile)

    # Assign stable ids + clause ids + TOC suppression flag.
    for n, h in enumerate(raw_headings):
        h["id"] = "h_{:04d}".format(n)
        title = clean_title(h["title"])
        h["title"] = title
        cid, _disp = parse_clause_id(title, profile)
        h["clause_id"] = cid
        h["is_toc"] = title.strip().lower() in profile["_toc_suppress"]

    total_lines = len(lines)
    compute_section_bounds(raw_headings, total_lines)
    clause_index = build_clause_index(raw_headings)

    # Cross-refs: scan each section's body (scoped to its own bounds).
    for h in raw_headings:
        start, end = h["section_bounds"]
        if end >= start:
            body = "\n".join(lines[start - 1:end])  # 1-based -> slice
        else:
            body = ""
        h["cross_refs"] = find_cross_refs(body, profile, clause_index)

    # Emit final heading objects (drop internal-only keys).
    out_headings = []
    for h in raw_headings:
        out_headings.append({
            "id": h["id"],
            "style": h["style"],
            "level": h["level"],
            "title": h["title"],
            "clause_id": h["clause_id"],
            "is_toc": h["is_toc"],
            "line": h["line"],
            "section_bounds": h["section_bounds"],
            "cross_refs": h["cross_refs"],
        })

    try:
        rel = str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        rel = str(path)
    rel = rel.replace("\\", "/")

    return {
        "path": rel,
        "sha256": sha256_of(data_bytes),
        "front_matter_lines": front_matter,
        "headings": out_headings,
    }


# --------------------------------------------------------------------------- #
# Index build                                                                 #
# --------------------------------------------------------------------------- #

def gather_md_files(target, exclude=None, include_roots=None):
    """Return (files, root) - a sorted list of *.md files for a dir or single
    file, and the root they're collected relative to.

    ``exclude`` (D21 §16.5, ``what_l2.exclude``): subtree paths relative to
    ``target`` to skip - only applies when ``target`` is a directory. A
    candidate is skipped when its path-relative-to-``target`` starts with one
    of these entries (path-component prefix match). Defaults to ``[]``
    (no-op): every project that doesn't set ``what_l2.exclude`` collects
    exactly the files it did before this parameter existed.

    ``include_roots`` (D21 §16.7, ``what_l2.include_roots``): additional
    directories OUTSIDE ``target`` to also walk with ``rglob("*.md")`` and
    union into the result, unfiltered - being named here *is* the inclusion
    decision. Defaults to ``[]`` (no-op). Each entry is resolved to an
    absolute path before globbing, so ``parse_file``'s existing
    not-under-root fallback (and ``query_index``'s absolute-path candidate)
    locate these files correctly regardless of the current working directory.
    """
    target = Path(target)
    if target.is_file():
        if target.suffix.lower() != ".md":
            raise SystemExit("Input file is not a .md file: {}".format(target))
        return [target], target.parent
    if not target.is_dir():
        raise SystemExit("Path does not exist: {}".format(target))

    exclude_parts = []
    for entry in exclude or []:
        stripped = entry.rstrip("/\\")
        if stripped:
            exclude_parts.append(Path(stripped).parts)

    files = []
    for f in sorted(target.rglob("*.md")):
        rel_parts = f.relative_to(target).parts
        if any(rel_parts[:len(ep)] == ep for ep in exclude_parts):
            continue
        files.append(f)

    for extra in include_roots or []:
        extra_path = Path(extra)
        if extra_path.is_dir():
            files.extend(sorted(extra_path.resolve().rglob("*.md")))

    return files, target


def build_index(target, profile_name, exclude=None, include_roots=None):
    files, root = gather_md_files(target, exclude=exclude, include_roots=include_roots)
    profile = load_profile(profile_name)
    file_entries = [parse_file(f, root, profile) for f in files]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile_name,
        # Absolute root the file paths are relative to. Used by `query` to
        # re-open source files for content search wherever the index lives.
        "root": str(root.resolve()).replace("\\", "/"),
        "files": file_entries,
    }


def is_stale(out_path, inputs, profile_name):
    """Return True if the index must be (re)built.

    Stale when: out file missing, built with a different profile, or older than
    any input file. Mirrors graphify's build-once / incremental behaviour.
    """
    out_path = Path(out_path)
    if not out_path.exists():
        return True
    try:
        with out_path.open(encoding="utf-8") as fh:
            existing = json.load(fh)
    except (ValueError, OSError):
        return True
    if existing.get("profile") != profile_name:
        return True
    out_mtime = out_path.stat().st_mtime
    for f in inputs:
        if Path(f).stat().st_mtime > out_mtime:
            return True
    return False


# --------------------------------------------------------------------------- #
# Query                                                                       #
# --------------------------------------------------------------------------- #

def query_index(index_path, terms, top):
    """Search section *content* for any of the OR'd terms; rank by match count.

    The index does not store section text -- we re-open each source file and
    scan only the already-known section_bounds line range (zero-LLM, file I/O
    only). Source files are resolved relative to the index file's directory,
    matching how the index recorded their (relative) paths.
    """
    index_path = Path(index_path)
    with index_path.open(encoding="utf-8") as fh:
        index = json.load(fh)
    index_dir = index_path.parent
    root = Path(index["root"]) if index.get("root") else index_dir

    term_res = [re.compile(re.escape(t), re.IGNORECASE) for t in terms if t.strip()]
    if not term_res:
        raise SystemExit("No search terms provided.")

    results = []
    file_cache = {}
    for fentry in index["files"]:
        # Resolve source file: prefer the recorded absolute root, then the
        # index's own directory, then the path as-is (absolute paths).
        candidates = [root / fentry["path"], index_dir / fentry["path"],
                      Path(fentry["path"])]
        src = next((c for c in candidates if c.exists()), None)
        if src is None:
            print(
                "Warning: source file not found for indexed path '{}' "
                "(tried: {}) - skipping".format(
                    fentry["path"], ", ".join(str(c) for c in candidates)
                ),
                file=sys.stderr,
            )
            continue
        if src not in file_cache:
            _data, file_cache[src] = read_lines(src)
        lines = file_cache[src]

        for h in fentry["headings"]:
            if h.get("is_toc"):
                continue
            start, end = h["section_bounds"]
            if end < start:
                body = ""
            else:
                body = "\n".join(lines[start - 1:end])
            # Also let the heading title match (helps short sections).
            haystack = h["title"] + "\n" + body
            count = sum(len(r.findall(haystack)) for r in term_res)
            if count > 0:
                results.append({
                    "file": fentry["path"],
                    "clause_id": h.get("clause_id"),
                    "title": h["title"],
                    "heading_id": h["id"],
                    "line": h["line"],
                    "section_bounds": h["section_bounds"],
                    "match_count": count,
                    "cross_refs": [
                        c for c in h.get("cross_refs", []) if c.get("resolved")
                    ],
                })

    results.sort(key=lambda r: (-r["match_count"], r["file"], r["line"]))
    return results[:top]


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #

def cmd_index(args):
    files, _root = gather_md_files(args.target, exclude=args.exclude, include_roots=args.include_roots)
    if not files:
        print("No .md files found under {}".format(args.target), file=sys.stderr)

    if args.stale_check:
        if not is_stale(args.output, files, args.profile):
            print("Index up to date (profile={}, {} inputs): {}".format(
                args.profile, len(files), args.output))
            return 0
        print("Index stale - rebuilding: {}".format(args.output), file=sys.stderr)

    index = build_index(args.target, args.profile, exclude=args.exclude, include_roots=args.include_roots)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2, ensure_ascii=False)
    n_headings = sum(len(f["headings"]) for f in index["files"])
    print("Indexed {} file(s), {} heading(s) -> {} (profile={})".format(
        len(index["files"]), n_headings, args.output, args.profile))
    return 0


def cmd_query(args):
    terms = args.terms.split()
    results = query_index(args.index, terms, args.top)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


def cmd_query_batch(args):
    with open(args.queries_file, encoding="utf-8") as fh:
        queries = json.load(fh)
    out = {}
    for key, terms in queries.items():
        out[key] = query_index(args.index, terms, args.top)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="md_index.py",
        description="Deterministic, zero-LLM markdown structural indexer "
                    "(the 'graphify for markdown').",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Build a JSON index from .md files.")
    p_index.add_argument("target", help="Directory or single .md file to index.")
    p_index.add_argument("-o", "--output", required=True,
                         help="Output JSON path (e.g. specs-out/index.json).")
    p_index.add_argument("--profile", default="generic",
                         help="Pattern profile: generic | 3gpp | <name> "
                              "(default: generic).")
    p_index.add_argument("--stale-check", action="store_true",
                         help="Skip rebuild if index is newer than all inputs "
                              "and built with the same profile.")
    p_index.add_argument("--exclude", action="append", default=[],
                         metavar="SUBPATH",
                         help="Subtree path relative to <target> to skip "
                              "(repeatable). D21 what_l2.exclude (§16.5). "
                              "Default: none.")
    p_index.add_argument("--include-root", dest="include_roots", action="append",
                         default=[], metavar="DIR",
                         help="Additional directory outside <target> to also "
                              "index, unfiltered (repeatable). D21 "
                              "what_l2.include_roots (§16.7). Default: none.")
    p_index.set_defaults(func=cmd_index)

    p_query = sub.add_parser("query", help="Search a built index by content terms.")
    p_query.add_argument("index", help="Path to index.json.")
    p_query.add_argument("terms", help="Space-separated OR'd search terms.")
    p_query.add_argument("--top", type=int, default=10,
                         help="Return at most N ranked matches (default: 10).")
    p_query.set_defaults(func=cmd_query)

    p_query_batch = sub.add_parser(
        "query-batch",
        help="Run multiple queries from a JSON file in one process.")
    p_query_batch.add_argument("index", help="Path to index.json.")
    p_query_batch.add_argument(
        "queries_file",
        help="JSON file mapping an arbitrary key (e.g. aspect id) to a list "
             'of OR\'d search terms, e.g. {"1": ["term1", "term2"], "2": ["term3"]}.')
    p_query_batch.add_argument("--top", type=int, default=10,
                         help="Return at most N ranked matches per key (default: 10).")
    p_query_batch.set_defaults(func=cmd_query_batch)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
