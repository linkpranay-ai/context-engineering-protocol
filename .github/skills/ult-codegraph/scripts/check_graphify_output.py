#!/usr/bin/env python3
"""check_graphify_output.py - post-`graphify update` sanity check
(the 2026-08-31 Round-2 evaluation's finding on the codegraph sanity-check invocation not being runnable as documented).

`graphify update` can fail on Windows in a way that gives a caller almost
nothing to act on: its internal watch/rebuild step exits with
`[WinError 5] Access is denied`, names no file, and leaves an empty
`graphify-out/cache/` behind with no `graph.json` ever written - confirmed
by running it twice in a row against a real repo, both times ending the
same way. `SKILL.md`'s "How to run" section had no step that would ever
notice this; a consuming skill following `CONSUMING-CODE-GRAPH.md` step 1
("check whether `graphify-out/graph.json` exists") would just silently fall
back to "no code graph found" with no idea *why*.

Run this immediately after `graphify update` (see `SKILL.md`'s "How to run")
and treat a nonzero exit the same way you'd treat `graphify update` itself
failing - don't proceed to `graphify query`/`path`/`explain`/`affected` on a
graph this flags as not actually produced.

Five states, in order of severity:

  - "never_ran": `graphify-out/` doesn't exist at all under the target
    directory. Either `graphify update` was never run there, or it was run
    against a different directory than the one being checked (`graphify
    update` can be scoped to a subdirectory - see `SKILL.md` Step 0).
  - "partial_failure": `graphify-out/` exists (so *something* ran) but
    `graph.json` was never written - the exact repro above.
  - "empty_or_corrupt": `graph.json` exists but is zero-length, isn't valid
    JSON, or parses to something with no actual graph content (e.g.
    `{"nodes": [], "edges": []}`) - a graph a consuming skill would silently
    get zero results from without ever being told why.
  - "stale": `graph.json` exists, parses, and has content, but its mtime
    predates the target's current HEAD commit - the 2026-09-01 evaluation's
    finding on this check having no state between "well-formed" and
    "fresh": a graph built on Monday and never rebuilt still comes back
    `ok` on Friday even after 400 new commits, and a consumer trusts that
    `ok` at face value. Determined by comparing `graph.json`'s mtime
    against HEAD's commit timestamp (cheaper and more robust than walking
    every tracked source file's own mtime); when that comparison can't be
    made at all (not a git working tree, git not on PATH, no commits yet)
    this falls back to "ok" rather than guessing - the same "no signal
    available, don't invent one" stance `_read_cep_manifest` takes
    elsewhere in this project for an absent manifest.
  - "ok": `graph.json` exists, parses, has content, and is not stale (or
    staleness could not be determined).

This script does not know graphify's internal JSON schema - that's an
external tool's implementation detail (see `SKILL.md`'s "Why wrap rather
than vendor"), not something this repo controls or should assume the shape
of. "Has content" below is checked schema-agnostically: valid JSON, and not
an empty container or a container of only-empty values. This is a check
that *something* was produced, not a validator of graph correctness.

The Windows troubleshooting text below is specific to the exact signature
that evaluation run hit (`[WinError 5] Access is denied`, no path, no
retry) rather than generic "permission denied" advice, because that's the
one failure mode this project has an actual confirmed repro for.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

NEVER_RAN = "never_ran"
PARTIAL_FAILURE = "partial_failure"
EMPTY_OR_CORRUPT = "empty_or_corrupt"
STALE = "stale"
OK = "ok"

# The exact failure signature from the 2026-08-31 Round-2 evaluation's finding on the codegraph sanity-check invocation not being runnable as documented -
# `graphify update`'s own output gives no path or further detail beyond this
# line, which is why the guidance below is written for this specific symptom
# instead of generic "permission denied" advice.
WINDOWS_ACCESS_DENIED_SIGNATURE = "[WinError 5] Access is denied"

WINDOWS_TROUBLESHOOTING: List[str] = [
    "This matches a known Windows failure mode: `graphify update`'s internal "
    f"watch/rebuild step can exit with `{WINDOWS_ACCESS_DENIED_SIGNATURE}` "
    "without naming the file it couldn't access, leaving `graphify-out/cache/` "
    "behind but no `graph.json`.",
    "Close anything that can transiently lock files under the target "
    "directory during the run: antivirus/Defender real-time scanning, an "
    "IDE's own file watcher, or a second terminal already running `graphify "
    "watch`/`graphify update` against the same path.",
    "If the target directory is inside a cloud-synced folder (OneDrive, "
    "Dropbox, Google Drive) - a common source of transient Windows file "
    "locks during sync - pause sync for the duration of the run, or re-run "
    "from a local (non-synced) clone.",
    "Add a Windows Defender exclusion for the target directory if it's "
    "trusted, then retry `graphify update . --no-cluster`.",
    "If it still fails, re-run once more before treating it as a persistent "
    "blocker - the error text doesn't name the specific file, so a second "
    "clean run after closing conflicting handles is often the fastest way "
    "to tell a transient lock apart from a real one.",
]

GRAPHIFYIGNORE_NOTE = (
    "Note: graphify's own docs state that `.graphifyignore` needs no CLI "
    "flag - it's auto-discovered next to the target directory the same way "
    "`.gitignore` is, evaluated after it. `graphify --help` not listing an "
    "ignore-file option is expected per that documentation, not a sign it "
    "isn't being honored. That said, a 2026-08-31 evaluation on Windows "
    "retried with the documented ignore configuration in place and observed "
    "no change in output - so treat the auto-discovery behavior itself as "
    "unconfirmed on Windows rather than settled fact, even though the "
    "documentation is unambiguous about it."
)


@dataclass
class CheckResult:
    status: str
    message: str
    troubleshooting: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == OK


def _graph_has_content(data) -> bool:
    """Schema-agnostic "isn't obviously empty" check - see module docstring
    for why this doesn't assume graphify's internal JSON shape. `graphify`'s
    output is a JSON object or array by construction; a bare string, number,
    or null at the top level isn't a graph at all."""
    if not isinstance(data, (list, dict)):
        return False
    if len(data) == 0:
        return False
    if isinstance(data, dict):
        # e.g. {"nodes": [], "edges": []} is the same "nothing here" state
        # as an empty top-level dict.
        return any(bool(v) for v in data.values())
    return True


def _head_commit_timestamp(repo_dir):
    """Returns the current HEAD commit's Unix timestamp for the git
    working tree containing `repo_dir`, or None if that can't be
    determined - not a git working tree, git isn't on PATH, there are no
    commits yet, or the command otherwise fails. None means "no staleness
    signal available"; callers must fall back to their pre-staleness
    behavior (returning `ok`) rather than treat an unmanifested/non-git
    target as an error - mirrors `_read_cep_manifest`'s same stance in the
    repo-layout skill for an absent manifest."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "HEAD"],
            cwd=str(repo_dir), capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    if not out.isdigit():
        return None
    return int(out)


def check_graphify_output(target_dir) -> CheckResult:
    """Runs the check against `target_dir` - the same directory `graphify
    update` was pointed at (repo root, or a scoped subdirectory - see
    `SKILL.md` Step 0). Never raises; every failure mode comes back as a
    CheckResult, not an exception, so this stays usable both as a CLI
    (`main()` maps status -> exit code) and as an importable check other
    scripts can call directly."""
    target = Path(target_dir).resolve()
    out_dir = target / "graphify-out"
    graph_json = out_dir / "graph.json"

    if not out_dir.is_dir():
        return CheckResult(
            NEVER_RAN,
            f"No `graphify-out/` found under {target}. Either `graphify "
            "update` was never run here, or it was run against a different "
            "directory (Step 0 in SKILL.md lets you scope it to a "
            "subdirectory instead of the repo root) - run `graphify update "
            "<dir> --no-cluster` against this exact directory, then re-run "
            "this check.",
        )

    if not graph_json.is_file():
        return CheckResult(
            PARTIAL_FAILURE,
            f"`graphify-out/` exists at {out_dir} but `graph.json` was "
            "never written - graphify started and exited without "
            "completing.",
            troubleshooting=list(WINDOWS_TROUBLESHOOTING),
        )

    try:
        raw = graph_json.read_text(encoding="utf-8")
    except OSError as exc:
        return CheckResult(
            EMPTY_OR_CORRUPT,
            f"`graph.json` exists at {graph_json} but could not be read: "
            f"{exc}",
        )

    if not raw.strip():
        return CheckResult(
            EMPTY_OR_CORRUPT,
            f"`graph.json` at {graph_json} is empty (zero content) - "
            "graphify wrote the file but the run didn't complete far enough "
            "to populate it.",
            troubleshooting=list(WINDOWS_TROUBLESHOOTING),
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return CheckResult(
            EMPTY_OR_CORRUPT,
            f"`graph.json` at {graph_json} is not valid JSON ({exc}) - the "
            "file is likely truncated from an interrupted write.",
            troubleshooting=list(WINDOWS_TROUBLESHOOTING),
        )

    if not _graph_has_content(data):
        return CheckResult(
            EMPTY_OR_CORRUPT,
            f"`graph.json` at {graph_json} parses but contains no graph "
            "content (empty node/edge lists) - re-run `graphify update "
            "<dir> --no-cluster` against a directory that actually contains "
            "source files.",
        )

    head_ts = _head_commit_timestamp(target)
    if head_ts is not None:
        try:
            graph_mtime = graph_json.stat().st_mtime
        except OSError:
            graph_mtime = None
        if graph_mtime is not None and graph_mtime < head_ts:
            return CheckResult(
                STALE,
                f"`graph.json` at {graph_json} exists and is populated, but "
                "its mtime predates the repo's current HEAD commit - it was "
                "built from an older snapshot and may not reflect recent "
                "changes. Re-run `graphify update <dir> --no-cluster` to "
                "refresh it, or proceed deliberately if a stale graph is "
                "acceptable for this question (see CONSUMING-CODE-GRAPH.md's "
                "graph-availability policy).",
            )

    return CheckResult(
        OK,
        f"`graph.json` found at {graph_json} and looks populated.",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target_dir",
        nargs="?",
        default=".",
        help="Directory `graphify update` was run against (default: current "
        "directory). Must match the directory passed to `graphify update`, "
        "not necessarily the repo root - see Step 0 of SKILL.md.",
    )
    args = parser.parse_args(argv)

    result = check_graphify_output(args.target_dir)
    print(result.message)
    for line in result.troubleshooting:
        print(f"  - {line}")
    print(GRAPHIFYIGNORE_NOTE)

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
