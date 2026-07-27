#!/usr/bin/env python3
"""mcp_mirror.py - mirror MCP-fetched content into local .md files.

Backs ROADMAP items 9 (MCP-backed What-L1 source) and 11 (MCP-backed How-L1
source): an MCP-fetched source has no file and no mtime, so it can't satisfy
md_index.py's mtime-based `--stale-check` the way a local .md file does.
Rather than teaching md_index.py a second, MCP-aware staleness model, this
script mirrors fetched content to local .md files and hands md_index.py an
ordinary directory of files it can index completely unchanged.

The trick that makes this work: content is only *rewritten* (and so only
picks up a fresh mtime) when its content_hash8 differs from what the last
mirror run recorded for that spec. Unchanged upstream content leaves the
mirror file's mtime untouched, so `md_index.py index --stale-check`
correctly no-ops; changed content bumps the mtime, so `--stale-check`
correctly rebuilds. Content-hash comparison (not mtime) is the signal at the
fetch layer; everything downstream of the mirror directory needs zero
modification.

Fetching itself is out of scope for this script -- it's called from
references/what-l1-fallback-query.md and references/how-l1-fallback-query.md
Step 0, which has the agent call the configured MCP tool directly and write
the result to a scratchpad JSON file (`{"body": "<fetched text>"}`) per
mcp_source entry; this script only mirrors/hashes/manifests those files. That
split keeps this script Python-stdlib-only with no MCP client dependency.
See examples/mcp-what-l1-demo/WALKTHROUGH.md for a validated, real-command
round trip against synthetic fixtures standing in for that fetched content.

Python 3 stdlib only (argparse, json, tempfile, pathlib, datetime), matching
content_hash.py / md_index.py's "vendorable, no pip install step" convention.
Reuses content_hash.py's content_hash8() directly rather than re-implementing
the normalize-and-hash logic.

CLI:
    python mcp_mirror.py mirror --spec-file <fetch-specs.json> \\
        --mirror-dir <dir> --manifest <manifest.json> \\
        [--content-dir <dir>]
"""

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from content_hash import content_hash8  # noqa: E402


def hash8_of_text(text):
    """Return the content_hash8 of `text` by reusing content_hash8() on a
    throwaway temp file, so the normalize-and-hash logic lives in exactly
    one place (content_hash.py)."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8", newline=""
    )
    try:
        tmp.write(text)
        tmp.close()
        return content_hash8(tmp.name)
    finally:
        Path(tmp.name).unlink()


def read_content_file(content_path):
    """Read a spec's fetched-content JSON file (`{"body": "<text>"}`) --
    either a real MCP tool-call result the calling procedure just wrote to a
    scratchpad path, or (in examples/mcp-what-l1-demo/) a synthetic fixture
    standing in for one. Returns the body text. Raises FileNotFoundError
    (uncaught, deliberately) if the file is missing -- a spec pointing at
    nothing should fail loudly, not silently no-op."""
    with open(content_path, encoding="utf-8") as fh:
        content = json.load(fh)
    return content["body"]


def render_mirror_file(spec, content_hash, fetched_at, body):
    source = spec["source"]
    header = (
        "<!-- mcp-mirror: server={server} tool={tool} identifier={identifier} "
        "fetched_at={fetched_at} content_hash={content_hash} -->\n\n"
    ).format(
        server=source["server"],
        tool=source["tool"],
        identifier=source["identifier"],
        fetched_at=fetched_at,
        content_hash=content_hash,
    )
    return header + body


def mirror_one(spec, mirror_dir, manifest, content_dir, spec_file_dir):
    spec_id = spec["id"]
    mirror_filename = spec["mirror_filename"]

    content_path = Path(spec["content_file"])
    if not content_path.is_absolute():
        base = Path(content_dir) if content_dir else spec_file_dir
        content_path = base / content_path

    body = read_content_file(content_path)
    new_hash = hash8_of_text(body)

    existing = manifest.get(spec_id)
    mirror_path = Path(mirror_dir) / mirror_filename

    if existing is not None and existing.get("content_hash8") == new_hash and mirror_path.exists():
        return "unchanged"

    status = "written (new)" if existing is None else "written (changed)"
    fetched_at = datetime.now(timezone.utc).isoformat()
    mirror_path.parent.mkdir(parents=True, exist_ok=True)
    mirror_path.write_text(
        render_mirror_file(spec, new_hash, fetched_at, body), encoding="utf-8"
    )
    manifest[spec_id] = {
        "mirror_filename": mirror_filename,
        "content_hash8": new_hash,
        "fetched_at": fetched_at,
        "source": spec["source"],
    }
    return status


def cmd_mirror(args):
    spec_file = Path(args.spec_file)
    with spec_file.open(encoding="utf-8") as fh:
        specs = json.load(fh)

    manifest_path = Path(args.manifest)
    if manifest_path.exists():
        with manifest_path.open(encoding="utf-8") as fh:
            manifest = json.load(fh)
    else:
        manifest = {}

    for spec in specs:
        status = mirror_one(
            spec,
            mirror_dir=args.mirror_dir,
            manifest=manifest,
            content_dir=args.content_dir,
            spec_file_dir=spec_file.resolve().parent,
        )
        print("{}: {} -> {}".format(status, spec["id"], spec["mirror_filename"]))

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False, sort_keys=True)

    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="mcp_mirror.py",
        description="Mirror MCP-fetched content into local .md files for "
                    "md_index.py, using content-hash comparison in place of "
                    "mtime as the upstream-changed signal.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_mirror = sub.add_parser(
        "mirror", help="Fetch every spec in --spec-file and mirror it."
    )
    p_mirror.add_argument("--spec-file", required=True,
                          help="JSON file listing fetch specs.")
    p_mirror.add_argument("--mirror-dir", required=True,
                          help="Directory to write mirrored .md files into.")
    p_mirror.add_argument("--manifest", required=True,
                          help="Path to the mirror manifest JSON "
                               "(created if missing, updated in place).")
    p_mirror.add_argument("--content-dir", default=None,
                          help="Resolve each spec's content_file relative to "
                               "this directory instead of --spec-file's own "
                               "directory.")
    p_mirror.set_defaults(func=cmd_mirror)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
