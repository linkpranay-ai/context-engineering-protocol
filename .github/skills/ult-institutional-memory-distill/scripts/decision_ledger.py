#!/usr/bin/env python3
"""decision_ledger.py - the only code that reads or writes DECISION-LEDGER.json.

Trip-wire: a persistent, project-scoped decision ledger distilled from
PRs, design docs, and postmortems, queried every time a context package is
assembled so a task doesn't quietly repeat a road the org already walked and
rejected. See references/ledger-schema.md for the full field-level spec --
this docstring covers the CLI surface only.

Python 3 stdlib only (argparse, json, re, sys, uuid, datetime, pathlib) --
vendorable alongside content_hash.py / md_index.py, no pip install step.

Subcommands:
    decision_ledger.py add-entry <ledger.json> --decision ... --reasoning ...
        [--rejected-alternative ...]* [--topic ...]+ [--source-type pr|design-doc|postmortem]
        --source-ref ... [--source-excerpt ...] --confidence EXTRACTED|INFERRED|SUGGESTED
        --distilled-by ... --distilled-through ... [--supersedes <entry-id>]
        Appends one new Ledger entry. Never merges with an existing entry --
        use `alias` for that (constraint 4: never merge, only alias).
        --supersedes sets a symmetric back-link to an existing entry ("this
        decision replaced that one") -- distinct from alias, which only
        annotates the surviving entry.

    decision_ledger.py alias <ledger.json> --into <entry-id> --from <entry-id>
        --merge-confidence EXTRACTED|INFERRED|SUGGESTED --merged-by <run-id>
        Records a structured alias on the surviving (`--into`) entry. The
        `--from` entry is NOT deleted or rewritten -- it stays addressable,
        per the graph-engineering-paper invariant "a superseded object
        remains addressable" this design cites.

    decision_ledger.py advance-cursor <ledger.json> --stream-id ... --last-processed-id ...
        Advances (or creates) a stream's run-level cursor. Only past
        artifacts fully processed (entry written or explicitly tombstoned).

    decision_ledger.py reject-source <ledger.json> --stream-id ... --source-id ...
        --rejected-by ... --reason ...
        Tombstones a source artifact a distillation run looked at and
        deliberately did not turn into an entry, so it is neither lost nor
        re-proposed on the next run. Terminal: a later `add-entry` citing a
        tombstoned source-id is refused unless --override-tombstone is
        passed explicitly.

    decision_ledger.py query <ledger.json> --aspects <aspects.json> [--budget <budget.json>]
        The trigger step. `aspects.json` is a list of
        `{"aspect_id": ..., "topics": [...]}`. Returns, per aspect, ranked
        candidate entries (literal topic-token overlap) plus per-aspect
        coverage (`covers_through`/`total_entries`/
        `entries_in_scope_for_this_aspect`) and `stopped_early`/`stop_reason`
        if `complexity_budget` was exhausted. This command NEVER writes --
        turning a candidate into a final `institutional_memory_hits[]` entry
        (deciding revise/proceed/escalate, writing `reason`/
        `required_evidence`) is the calling agent's judgment call
        (ult-context-generate/SKILL.md Step 7.7), same division of labor as
        md_index.py query returning ranked candidates for the agent to author
        context_items from.

    decision_ledger.py disposition <ledger.json> --hit-id ... --package-id ...
        --aspect-id ... --matched-decision <entry-id> --tier revise|proceed|escalate
        --disposition dismissed|accepted|escalated --by human:<id> [--reason ...]
        Records a human's disposition of a hit. Enforces the tier ->
        legal-disposition table in references/ledger-schema.md; refuses an
        illegal combination (e.g. dismissing a proceed-tier hit) rather than
        writing it. `--reason` is required for revise/escalate tiers.

    decision_ledger.py show <ledger.json>
        Prints the ledger's schema_version, entry/cursor/disposition counts.
        Sanity/debugging aid, not part of the trip-wire flow itself.

Every write subcommand rewrites the whole file with stable key order and
2-space indent, so diffs in the write-gate PR stay small and readable.
"""

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

_CONFIDENCE_VALUES = ("EXTRACTED", "INFERRED", "SUGGESTED")
_SOURCE_TYPES = ("pr", "design-doc", "postmortem")
_TIERS = ("revise", "proceed", "escalate")

# Tier -> legal disposition values (references/ledger-schema.md's table).
# A proceed-tier hit cannot be "dismissed" -- the ledger already agrees with
# the task, so there is nothing to overrule, only to acknowledge.
_LEGAL_DISPOSITIONS = {
    "revise": ("dismissed", "accepted", "escalated"),
    "escalate": ("accepted", "escalated"),
    "proceed": ("accepted",),
}
# Tiers whose disposition requires a non-empty --reason.
_REASON_REQUIRED_TIERS = ("revise", "escalate")

_DEFAULT_BUDGET = {
    "max_model_calls": 0,
    "max_sub_agents": 0,
    "max_concurrent_workers": 1,
    "max_tool_calls": 1,
    "max_wall_clock_ms": 2000,
    "max_tokens": 0,
    "max_financial_cost_usd": 0,
    "max_retries": 0,
    "max_graph_writes": 0,
    "min_evidence_required": 1,
}

_ID_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(text, max_len=24):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len] or "entry"


# --------------------------------------------------------------------------- #
# Ledger load/save                                                             #
# --------------------------------------------------------------------------- #

def empty_ledger():
    return {
        "schema_version": SCHEMA_VERSION,
        "entries": [],
        "run_state": {"cursors": [], "rejected_sources": []},
        "hit_dispositions": [],
    }


def load_ledger(path):
    """Load the ledger at `path`, or an empty skeleton if it doesn't exist yet.

    A missing file is not an error -- a project that hasn't distilled
    anything yet has a legitimate, fully-valid empty ledger.
    """
    path = Path(path)
    if not path.exists():
        return empty_ledger()
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return empty_ledger()
    ledger = json.loads(text)
    ledger.setdefault("schema_version", SCHEMA_VERSION)
    ledger.setdefault("entries", [])
    ledger.setdefault("run_state", {"cursors": [], "rejected_sources": []})
    ledger["run_state"].setdefault("cursors", [])
    ledger["run_state"].setdefault("rejected_sources", [])
    ledger.setdefault("hit_dispositions", [])
    return ledger


def save_ledger(path, ledger):
    """Write `ledger` to `path`, 2-space indent, stable field order.

    Creates parent directories if needed -- the ledger is a derived artifact,
    not a project-authored drop-zone, so there is no separate scaffolding
    step a human is expected to run first.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = {
        "schema_version": ledger.get("schema_version", SCHEMA_VERSION),
        "entries": ledger.get("entries", []),
        "run_state": {
            "cursors": ledger.get("run_state", {}).get("cursors", []),
            "rejected_sources": ledger.get("run_state", {}).get("rejected_sources", []),
        },
        "hit_dispositions": ledger.get("hit_dispositions", []),
    }
    path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Validation (shared by add-entry / alias / disposition and a standalone
# `validate` use from tests)                                                  #
# --------------------------------------------------------------------------- #

def validate_ledger(ledger):
    """Return a list of problem strings (empty = valid). Structural checks
    only -- does not re-derive whether a merge/disposition was *correct*,
    only whether the file is well-formed per references/ledger-schema.md.
    """
    problems = []
    entry_ids = set()
    for i, entry in enumerate(ledger.get("entries", [])):
        where = "entries[{}]".format(i)
        for field in ("id", "decision", "reasoning", "confidence", "distilled_by", "created_at"):
            if not entry.get(field):
                problems.append("{}: missing required field '{}'".format(where, field))
        if entry.get("id") in entry_ids:
            problems.append("{}: duplicate id '{}'".format(where, entry.get("id")))
        entry_ids.add(entry.get("id"))
        if entry.get("confidence") not in _CONFIDENCE_VALUES:
            problems.append("{}: confidence must be one of {}".format(where, _CONFIDENCE_VALUES))
        for j, alias in enumerate(entry.get("aliases", [])):
            for field in ("entry_id", "merge_confidence", "merged_by", "merged_at"):
                if not alias.get(field):
                    problems.append("{}.aliases[{}]: missing required field '{}'".format(where, j, field))
            if alias.get("merge_confidence") not in _CONFIDENCE_VALUES:
                problems.append("{}.aliases[{}]: merge_confidence must be one of {}".format(where, j, _CONFIDENCE_VALUES))

    for i, disp in enumerate(ledger.get("hit_dispositions", [])):
        where = "hit_dispositions[{}]".format(i)
        for field in ("hit_id", "package_id", "aspect_id", "matched_decision", "tier", "disposition", "by", "at"):
            if not disp.get(field):
                problems.append("{}: missing required field '{}'".format(where, field))
        tier = disp.get("tier")
        disposition = disp.get("disposition")
        if tier not in _LEGAL_DISPOSITIONS:
            problems.append("{}: tier must be one of {}".format(where, _TIERS))
        elif disposition not in _LEGAL_DISPOSITIONS[tier]:
            problems.append(
                "{}: disposition '{}' is not legal for tier '{}' (legal: {})".format(
                    where, disposition, tier, _LEGAL_DISPOSITIONS[tier]
                )
            )
        if tier in _REASON_REQUIRED_TIERS and not disp.get("reason"):
            problems.append("{}: reason is required for tier '{}'".format(where, tier))

    return problems


# --------------------------------------------------------------------------- #
# add-entry / alias / advance-cursor / reject-source                          #
# --------------------------------------------------------------------------- #

def add_entry(ledger, decision, reasoning, topics, source_type, source_ref,
              confidence, distilled_by, distilled_through,
              rejected_alternatives=None, source_excerpt=None, entry_id=None,
              supersedes=None):
    if source_type not in _SOURCE_TYPES:
        raise ValueError("source_type must be one of {}".format(_SOURCE_TYPES))
    if confidence not in _CONFIDENCE_VALUES:
        raise ValueError("confidence must be one of {}".format(_CONFIDENCE_VALUES))
    superseded_entry = None
    if supersedes is not None:
        superseded_entry = next(
            (e for e in ledger.get("entries", []) if e["id"] == supersedes), None
        )
        if superseded_entry is None:
            raise ValueError(
                "no entry with id '{}' (supersedes target must already exist -- "
                "never invent a bare id)".format(supersedes)
            )
    entry = {
        "id": entry_id or "dl_{}_{}".format(_slugify(decision), uuid.uuid4().hex[:6]),
        "decision": decision,
        "reasoning": reasoning,
        "rejected_alternatives": rejected_alternatives or [],
        "topics": topics,
        "source": {"type": source_type, "ref": source_ref, "excerpt": source_excerpt or ""},
        "confidence": confidence,
        "distilled_by": distilled_by,
        "distilled_through": distilled_through,
        "created_at": _now_iso(),
        "aliases": [],
        "supersedes": supersedes,
        "superseded_by": None,
    }
    ledger.setdefault("entries", []).append(entry)
    if superseded_entry is not None:
        # Symmetric back-link -- both entries stay independently addressable
        # ("this decision replaced that one" reads correctly from either
        # side), distinct from aliases which only annotate the survivor.
        superseded_entry["superseded_by"] = entry["id"]
    return entry


def add_alias(ledger, into_id, from_id, merge_confidence, merged_by):
    if merge_confidence not in _CONFIDENCE_VALUES:
        raise ValueError("merge_confidence must be one of {}".format(_CONFIDENCE_VALUES))
    target = next((e for e in ledger.get("entries", []) if e["id"] == into_id), None)
    if target is None:
        raise ValueError("no entry with id '{}' (alias target must already exist)".format(into_id))
    if not any(e["id"] == from_id for e in ledger.get("entries", [])):
        raise ValueError("no entry with id '{}' (alias source must already exist -- never invent a bare id)".format(from_id))
    target.setdefault("aliases", []).append({
        "entry_id": from_id,
        "merge_confidence": merge_confidence,
        "merged_by": merged_by,
        "merged_at": _now_iso(),
    })
    return target


def advance_cursor(ledger, stream_id, last_processed_id):
    cursors = ledger.setdefault("run_state", {}).setdefault("cursors", [])
    for c in cursors:
        if c["stream_id"] == stream_id:
            c["last_processed_id"] = last_processed_id
            c["advanced_at"] = _now_iso()
            return c
    cursor = {"stream_id": stream_id, "last_processed_id": last_processed_id, "advanced_at": _now_iso()}
    cursors.append(cursor)
    return cursor


def reject_source(ledger, stream_id, source_id, rejected_by, reason, override_tombstone=False):
    rejected = ledger.setdefault("run_state", {}).setdefault("rejected_sources", [])
    existing = next((r for r in rejected if r["source_id"] == source_id and r["stream_id"] == stream_id), None)
    if existing is not None and not override_tombstone:
        raise ValueError(
            "source_id '{}' on stream '{}' is already tombstoned "
            "(rejected_at={}) -- pass override_tombstone to re-decide it".format(
                source_id, stream_id, existing["rejected_at"]
            )
        )
    tombstone = {
        "source_id": source_id,
        "stream_id": stream_id,
        "rejected_at": _now_iso(),
        "rejected_by": rejected_by,
        "reason": reason,
    }
    if existing is not None:
        rejected.remove(existing)
    rejected.append(tombstone)
    return tombstone


def is_tombstoned(ledger, stream_id, source_id):
    return any(
        r["stream_id"] == stream_id and r["source_id"] == source_id
        for r in ledger.get("run_state", {}).get("rejected_sources", [])
    )


# --------------------------------------------------------------------------- #
# query (the trigger step) -- read-only, complexity_budget-bounded            #
# --------------------------------------------------------------------------- #

def _topic_tokens(topics):
    tokens = set()
    for t in topics:
        tokens.update(_ID_TOKEN_RE.findall(t.lower()))
    return tokens


def query_ledger(ledger, aspects, budget=None):
    """`aspects` is a list of {"aspect_id": ..., "topics": [...]}.

    Returns a dict: {"stopped_early": bool, "stop_reason": str|None,
    "results": [{"aspect_id", "covers_through", "total_entries",
    "entries_in_scope_for_this_aspect", "candidates": [...]}]}.

    Candidates are ranked by descending topic-token overlap count; an entry
    with fewer overlapping tokens than `min_evidence_required` is dropped,
    not surfaced as a low-confidence hit. Deliberately does not decide
    revise/proceed/escalate or write anything -- that is the calling agent's
    job (ult-context-generate/SKILL.md Step 7.7).
    """
    budget = dict(_DEFAULT_BUDGET, **(budget or {}))
    entries = ledger.get("entries", [])
    total_entries = len(entries)
    covers_through = ", ".join(
        "{}:{}".format(c["stream_id"], c["last_processed_id"])
        for c in ledger.get("run_state", {}).get("cursors", [])
    ) or None

    start = datetime.now(timezone.utc)
    stopped_early = False
    stop_reason = None
    results = []

    for aspect in aspects:
        if stopped_early:
            # Budget already exhausted -- every remaining aspect gets an
            # honest "not covered yet" record, never a silent skip that
            # would read as a clean zero-hits result (the false-absence
            # failure mode this design exists to close).
            results.append({
                "aspect_id": aspect["aspect_id"],
                "covers_through": covers_through,
                "total_entries": total_entries,
                "entries_in_scope_for_this_aspect": None,
                "candidates": [],
                "note": "not scanned -- complexity_budget exhausted before this aspect",
            })
            continue

        aspect_tokens = _topic_tokens(aspect.get("topics", []))
        candidates = []
        in_scope_count = 0
        entries_examined = 0
        stopped_mid_aspect = False
        for entry in entries:
            elapsed_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            if elapsed_ms > budget["max_wall_clock_ms"]:
                stopped_early = True
                stopped_mid_aspect = True
                stop_reason = "max_wall_clock_ms"
                break
            entries_examined += 1
            entry_tokens = _topic_tokens(entry.get("topics", []))
            overlap = aspect_tokens & entry_tokens
            if not overlap:
                continue
            in_scope_count += 1
            if len(overlap) < budget["min_evidence_required"]:
                continue
            candidates.append({
                "entry_id": entry["id"],
                "decision": entry["decision"],
                "reasoning": entry["reasoning"],
                "rejected_alternatives": entry.get("rejected_alternatives", []),
                "matched_topics": sorted(overlap),
                "confidence": entry["confidence"],
                "source": entry["source"],
            })

        candidates.sort(key=lambda c: len(c["matched_topics"]), reverse=True)
        result = {
            "aspect_id": aspect["aspect_id"],
            "covers_through": covers_through,
            "total_entries": total_entries,
            "entries_in_scope_for_this_aspect": in_scope_count,
            "candidates": candidates,
        }
        if stopped_mid_aspect:
            # Budget ran out partway through *this* aspect's own scan --
            # in_scope_count/candidates only reflect the entries_examined
            # prefix, not the full entry set. Without this note it is
            # indistinguishable from a complete scan that found nothing --
            # the exact false-absence failure mode this design exists to
            # close, just relocated to the boundary aspect instead of the
            # ones after it.
            result["note"] = (
                "partial scan -- complexity_budget exhausted after {} of {} "
                "entries; entries_in_scope_for_this_aspect reflects only the "
                "entries examined so far".format(entries_examined, total_entries)
            )
        results.append(result)

    return {"stopped_early": stopped_early, "stop_reason": stop_reason, "results": results}


# --------------------------------------------------------------------------- #
# disposition                                                                 #
# --------------------------------------------------------------------------- #

def record_disposition(ledger, hit_id, package_id, aspect_id, matched_decision,
                        tier, disposition, by, reason=None):
    if tier not in _LEGAL_DISPOSITIONS:
        raise ValueError("tier must be one of {}".format(_TIERS))
    if disposition not in _LEGAL_DISPOSITIONS[tier]:
        raise ValueError(
            "disposition '{}' is not legal for tier '{}' (legal: {})".format(
                disposition, tier, _LEGAL_DISPOSITIONS[tier]
            )
        )
    if tier in _REASON_REQUIRED_TIERS and not reason:
        raise ValueError("reason is required for tier '{}'".format(tier))
    if not any(e["id"] == matched_decision for e in ledger.get("entries", [])):
        raise ValueError("no ledger entry with id '{}'".format(matched_decision))

    record = {
        "hit_id": hit_id,
        "package_id": package_id,
        "aspect_id": aspect_id,
        "matched_decision": matched_decision,
        "tier": tier,
        "disposition": disposition,
        "reason": reason or "",
        "by": by,
        "at": _now_iso(),
    }
    ledger.setdefault("hit_dispositions", []).append(record)
    return record


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def _cmd_add_entry(args):
    ledger = load_ledger(args.ledger)
    try:
        entry = add_entry(
            ledger, args.decision, args.reasoning, args.topic, args.source_type,
            args.source_ref, args.confidence, args.distilled_by, args.distilled_through,
            rejected_alternatives=args.rejected_alternative, source_excerpt=args.source_excerpt,
            supersedes=args.supersedes,
        )
    except ValueError as e:
        print("ERROR: {}".format(e), file=sys.stderr)
        return 1
    problems = validate_ledger(ledger)
    if problems:
        for p in problems:
            print("VALIDATION ERROR: {}".format(p), file=sys.stderr)
        return 1
    save_ledger(args.ledger, ledger)
    print(json.dumps(entry, indent=2))
    return 0


def _cmd_alias(args):
    ledger = load_ledger(args.ledger)
    try:
        target = add_alias(ledger, args.into, args.from_, args.merge_confidence, args.merged_by)
    except ValueError as e:
        print("ERROR: {}".format(e), file=sys.stderr)
        return 1
    save_ledger(args.ledger, ledger)
    print(json.dumps(target, indent=2))
    return 0


def _cmd_advance_cursor(args):
    ledger = load_ledger(args.ledger)
    cursor = advance_cursor(ledger, args.stream_id, args.last_processed_id)
    save_ledger(args.ledger, ledger)
    print(json.dumps(cursor, indent=2))
    return 0


def _cmd_reject_source(args):
    ledger = load_ledger(args.ledger)
    try:
        tombstone = reject_source(
            ledger, args.stream_id, args.source_id, args.rejected_by, args.reason,
            override_tombstone=args.override_tombstone,
        )
    except ValueError as e:
        print("ERROR: {}".format(e), file=sys.stderr)
        return 1
    save_ledger(args.ledger, ledger)
    print(json.dumps(tombstone, indent=2))
    return 0


def _cmd_query(args):
    ledger = load_ledger(args.ledger)
    aspects = json.loads(Path(args.aspects).read_text(encoding="utf-8"))
    budget = json.loads(Path(args.budget).read_text(encoding="utf-8")) if args.budget else None
    result = query_ledger(ledger, aspects, budget=budget)
    print(json.dumps(result, indent=2))
    return 0


def _cmd_disposition(args):
    ledger = load_ledger(args.ledger)
    try:
        record = record_disposition(
            ledger, args.hit_id, args.package_id, args.aspect_id, args.matched_decision,
            args.tier, args.disposition, args.by, reason=args.reason,
        )
    except ValueError as e:
        print("ERROR: {}".format(e), file=sys.stderr)
        return 1
    save_ledger(args.ledger, ledger)
    print(json.dumps(record, indent=2))
    return 0


def _cmd_show(args):
    ledger = load_ledger(args.ledger)
    problems = validate_ledger(ledger)
    print(json.dumps({
        "schema_version": ledger.get("schema_version"),
        "entries": len(ledger.get("entries", [])),
        "cursors": len(ledger.get("run_state", {}).get("cursors", [])),
        "rejected_sources": len(ledger.get("run_state", {}).get("rejected_sources", [])),
        "hit_dispositions": len(ledger.get("hit_dispositions", [])),
        "validation_problems": problems,
    }, indent=2))
    return 1 if problems else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="decision_ledger.py",
        description="Read/write the trip-wire decision ledger.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add-entry", help="Append a new ledger entry.")
    p_add.add_argument("ledger")
    p_add.add_argument("--decision", required=True)
    p_add.add_argument("--reasoning", required=True)
    p_add.add_argument("--rejected-alternative", action="append", default=[])
    p_add.add_argument("--topic", action="append", required=True)
    p_add.add_argument("--source-type", required=True, choices=_SOURCE_TYPES)
    p_add.add_argument("--source-ref", required=True)
    p_add.add_argument("--source-excerpt", default="")
    p_add.add_argument("--confidence", required=True, choices=_CONFIDENCE_VALUES)
    p_add.add_argument("--distilled-by", required=True)
    p_add.add_argument("--distilled-through", required=True)
    p_add.add_argument(
        "--supersedes", default=None,
        help="Entry id this new entry replaces. Must already exist; sets a "
             "symmetric back-link (that entry's superseded_by) automatically.",
    )
    p_add.set_defaults(func=_cmd_add_entry)

    p_alias = sub.add_parser("alias", help="Record a structured alias merge (never a bare-id merge).")
    p_alias.add_argument("ledger")
    p_alias.add_argument("--into", required=True, help="Surviving entry id.")
    p_alias.add_argument("--from", dest="from_", required=True, help="Entry id merged in as an alias.")
    p_alias.add_argument("--merge-confidence", required=True, choices=_CONFIDENCE_VALUES)
    p_alias.add_argument("--merged-by", required=True)
    p_alias.set_defaults(func=_cmd_alias)

    p_cursor = sub.add_parser("advance-cursor", help="Advance a source stream's run-level cursor.")
    p_cursor.add_argument("ledger")
    p_cursor.add_argument("--stream-id", required=True)
    p_cursor.add_argument("--last-processed-id", required=True)
    p_cursor.set_defaults(func=_cmd_advance_cursor)

    p_reject = sub.add_parser("reject-source", help="Tombstone a source deliberately not distilled.")
    p_reject.add_argument("ledger")
    p_reject.add_argument("--stream-id", required=True)
    p_reject.add_argument("--source-id", required=True)
    p_reject.add_argument("--rejected-by", required=True)
    p_reject.add_argument("--reason", required=True)
    p_reject.add_argument("--override-tombstone", action="store_true")
    p_reject.set_defaults(func=_cmd_reject_source)

    p_query = sub.add_parser("query", help="The trigger step: budget-bounded topic-match query.")
    p_query.add_argument("ledger")
    p_query.add_argument("--aspects", required=True, help="Path to a JSON list of {aspect_id, topics}.")
    p_query.add_argument("--budget", help="Path to a complexity_budget JSON file (defaults applied if omitted).")
    p_query.set_defaults(func=_cmd_query)

    p_disp = sub.add_parser("disposition", help="Record a human's disposition of a hit.")
    p_disp.add_argument("ledger")
    p_disp.add_argument("--hit-id", required=True)
    p_disp.add_argument("--package-id", required=True)
    p_disp.add_argument("--aspect-id", required=True)
    p_disp.add_argument("--matched-decision", required=True)
    p_disp.add_argument("--tier", required=True, choices=_TIERS)
    p_disp.add_argument("--disposition", required=True, choices=("dismissed", "accepted", "escalated"))
    p_disp.add_argument("--by", required=True)
    p_disp.add_argument("--reason", default=None)
    p_disp.set_defaults(func=_cmd_disposition)

    p_show = sub.add_parser("show", help="Print ledger summary counts + validation problems.")
    p_show.add_argument("ledger")
    p_show.set_defaults(func=_cmd_show)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
