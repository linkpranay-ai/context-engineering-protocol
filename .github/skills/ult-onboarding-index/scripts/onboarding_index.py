#!/usr/bin/env python3
"""onboarding_index.py -- discovery + marked-block splice for ult-onboarding-index.

This docstring covers CLI surface only -- see the skill's SKILL.md for the
full workflow this belongs to, and references/slot-discovery.md +
references/marked-block-write-protocol.md for the exact contract each
subcommand implements.

Python 3 stdlib only (argparse, json, os, sys, glob, pathlib) -- vendorable,
no pip install step, same posture as scaffold_state.py
(ult-autoscaffold-content/scripts/) and decision_ledger.py
(ult-institutional-memory-distill/scripts/). This script does not parse
context-config.yaml or any other YAML -- path resolution is agent-driven
(see SKILL.md Step 2); this script only does mechanical existence-checking
and glob work against paths it's handed.

No state file. Every write this script makes is independently
existence-gated or marker-scoped, and idempotent on re-run -- the target
files themselves are the state, so there's nothing here to checkpoint.

Subcommands:
  onboarding_index.py discover --repo-root <path> --slots-json <path>
      [--how-l2-path <path>]
    Reads --slots-json (a flat JSON object, slot id -> absolute path --
    see references/slot-discovery.md for the exact id list and an example)
    and existence-checks each path. A file-kind slot counts as present only
    if the path is a file that exists. A directory-kind slot counts as
    present only if the path is a directory that exists AND contains at
    least one file (recursively) -- an empty directory is not "content".
    If --how-l2-path is given, also globs that directory (non-recursively
    for the two named files, recursively for interfaces/*.md and CONTEXT.md)
    for CODING-STANDARDS.md, TESTING-GUIDELINES.md, interfaces/*.md, and any
    CONTEXT.md. Prints {slot_id: {"path": ..., "exists": bool}, ...} plus
    (if requested) a "how_l2" key with its own found-files breakdown.

  onboarding_index.py merge-block <target-file> <block-content-file>
      --begin-marker <str> --end-marker <str>
    The create/replace-block/append-to-unmarked-file splice described in
    references/marked-block-write-protocol.md, ported from install.sh's
    merge_agents_md() (install.sh lines ~199-260):
      1. Target file doesn't exist -> create it containing just the marked
         block (begin marker, block content, end marker).
      2. Target file exists, marker pair present -> replace only the
         content between the markers, byte-for-byte; everything outside
         (including any other marker pair, e.g. install.sh's own
         "context-engineering-protocol SKILLS" block) is left untouched.
      3. Target file exists, marker pair absent -> append the marked block
         at the end, preceded by a blank line.
    Idempotent: running twice with the same block content produces no
    further change after the first run. Prints {"target": ..., "action":
    "created"|"block-replaced"|"block-appended"}.

  onboarding_index.py write-stub <target-file> --content-file <path>
    Whole-file existence gate for .cursor/rules/onboarding.mdc: if
    <target-file> already exists, does nothing and reports "skipped". If it
    doesn't exist, writes --content-file's contents as the entire file,
    creating parent directories as needed. Prints {"target": ..., "action":
    "written"|"skipped"}.
"""

import argparse
import glob as globmod
import json
import os
import sys
from pathlib import Path


# --------------------------------------------------------------------------- #
# discover                                                                    #
# --------------------------------------------------------------------------- #

HOW_L2_FLAT_FILES = ("CODING-STANDARDS.md", "TESTING-GUIDELINES.md")


def _dir_has_any_file(path):
    for _root, _dirs, files in os.walk(path):
        if files:
            return True
    return False


def resolve_slots(slots):
    """slots: {slot_id: path_str}. Returns {slot_id: {"path", "exists"}}."""
    result = {}
    for slot_id, path_str in slots.items():
        p = Path(path_str)
        if p.is_file():
            exists = True
        elif p.is_dir():
            exists = _dir_has_any_file(str(p))
        else:
            exists = False
        result[slot_id] = {"path": path_str, "exists": exists}
    return result


def resolve_how_l2(how_l2_path):
    """Globs how_l2_path for the four known How-L2 artifact kinds."""
    base = Path(how_l2_path)
    if not base.is_dir():
        return {"path": how_l2_path, "exists": False, "found": []}
    found = []
    for name in HOW_L2_FLAT_FILES:
        if (base / name).is_file():
            found.append(name)
    interfaces = sorted(
        str(Path(f).relative_to(base)).replace(os.sep, "/")
        for f in globmod.glob(str(base / "interfaces" / "*.md"))
    )
    found.extend(interfaces)
    context_files = sorted(
        str(Path(f).relative_to(base)).replace(os.sep, "/")
        for f in globmod.glob(str(base / "**" / "CONTEXT.md"), recursive=True)
    )
    found.extend(context_files)
    return {"path": how_l2_path, "exists": len(found) > 0, "found": found}


def discover(repo_root, slots, how_l2_path=None):
    if not Path(repo_root).is_dir():
        raise FileNotFoundError("--repo-root does not exist or is not a directory: {}".format(repo_root))
    result = resolve_slots(slots)
    if how_l2_path is not None:
        result["how_l2"] = resolve_how_l2(how_l2_path)
    return result


# --------------------------------------------------------------------------- #
# merge-block                                                                 #
# --------------------------------------------------------------------------- #

def splice_marked_block(existing_text, block_content, begin_marker, end_marker):
    """Returns (new_text, action). existing_text is None if the file didn't exist.

    block_core deliberately carries no trailing newline of its own -- the
    end marker is its last character. That's what keeps a replace
    idempotent: the replacement only ever reintroduces exactly the bytes
    that already followed the old end marker (usually a single trailing
    newline), instead of adding a fresh one on top each run.
    """
    block_core = "{}\n{}\n{}".format(begin_marker, block_content.rstrip("\n"), end_marker)

    if existing_text is None:
        return block_core + "\n", "created"

    begin_idx = existing_text.find(begin_marker)
    end_idx = existing_text.find(end_marker)

    if begin_idx != -1 and end_idx != -1 and end_idx > begin_idx:
        end_idx_after_marker = end_idx + len(end_marker)
        new_text = existing_text[:begin_idx] + block_core + existing_text[end_idx_after_marker:]
        # Idempotency: if this produces no change, splice_marked_block still
        # reports "block-replaced" -- the caller doesn't need to distinguish
        # a no-op replace from a real one, only created/appended from it.
        return new_text, "block-replaced"

    if begin_idx != -1 or end_idx != -1:
        raise ValueError(
            "Found only one of the two markers in the target file -- refusing to "
            "guess. Begin marker present: {}. End marker present: {}.".format(
                begin_idx != -1, end_idx != -1
            )
        )

    separator = "" if existing_text.endswith("\n\n") else (
        "\n" if existing_text.endswith("\n") else "\n\n"
    )
    new_text = existing_text + separator + block_core + "\n"
    return new_text, "block-appended"


# --------------------------------------------------------------------------- #
# write-stub                                                                  #
# --------------------------------------------------------------------------- #

def write_stub(target_path, content):
    p = Path(target_path)
    if p.exists():
        return "skipped"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return "written"


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #

def _cmd_discover(args):
    try:
        with open(args.slots_json, "r", encoding="utf-8") as f:
            slots = json.load(f)
    except (OSError, ValueError) as e:
        print("ERROR: could not read --slots-json: {}".format(e), file=sys.stderr)
        return 1
    try:
        result = discover(args.repo_root, slots, how_l2_path=args.how_l2_path)
    except (ValueError, FileNotFoundError) as e:
        print("ERROR: {}".format(e), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def _cmd_merge_block(args):
    try:
        with open(args.block_content_file, "r", encoding="utf-8") as f:
            block_content = f.read()
    except OSError as e:
        print("ERROR: could not read block-content-file: {}".format(e), file=sys.stderr)
        return 1

    target = Path(args.target_file)
    existing_text = None
    if target.exists():
        try:
            existing_text = target.read_text(encoding="utf-8")
        except OSError as e:
            print("ERROR: could not read target-file: {}".format(e), file=sys.stderr)
            return 1

    try:
        new_text, action = splice_marked_block(
            existing_text, block_content, args.begin_marker, args.end_marker
        )
    except ValueError as e:
        print("ERROR: {}".format(e), file=sys.stderr)
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new_text, encoding="utf-8")
    print(json.dumps({"target": str(target), "action": action}, indent=2))
    return 0


def _cmd_write_stub(args):
    try:
        with open(args.content_file, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        print("ERROR: could not read --content-file: {}".format(e), file=sys.stderr)
        return 1
    action = write_stub(args.target_file, content)
    print(json.dumps({"target": args.target_file, "action": action}, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="onboarding_index.py",
        description="Discovery + marked-block splice for ult-onboarding-index.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_disc = sub.add_parser(
        "discover", help="Existence-check the registered slots and (optionally) glob How-L2."
    )
    p_disc.add_argument("--repo-root", required=True)
    p_disc.add_argument(
        "--slots-json", required=True,
        help="Path to a JSON object mapping slot id -> resolved absolute path. "
             "See references/slot-discovery.md for the id list and an example.",
    )
    p_disc.add_argument(
        "--how-l2-path", default=None,
        help="Resolved how_dimension.how_l2.path to glob for CODING-STANDARDS.md, "
             "TESTING-GUIDELINES.md, interfaces/*.md, and CONTEXT.md files.",
    )
    p_disc.set_defaults(func=_cmd_discover)

    p_merge = sub.add_parser(
        "merge-block",
        help="Create/replace/append the marked block in a target file (AGENTS.md, "
             ".github/copilot-instructions.md, or CLAUDE.md).",
    )
    p_merge.add_argument("target_file")
    p_merge.add_argument("block_content_file")
    p_merge.add_argument("--begin-marker", required=True)
    p_merge.add_argument("--end-marker", required=True)
    p_merge.set_defaults(func=_cmd_merge_block)

    p_stub = sub.add_parser(
        "write-stub",
        help="Write a whole new file if it doesn't already exist (.cursor/rules/onboarding.mdc).",
    )
    p_stub.add_argument("target_file")
    p_stub.add_argument("--content-file", required=True)
    p_stub.set_defaults(func=_cmd_write_stub)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
