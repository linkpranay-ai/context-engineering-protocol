# Decision Ledger JSON Schema

This file is the field-level spec for the trip-wire decision ledger;
`decision_ledger.py` is the only code that reads or writes it — never
hand-edit the ledger file itself. The
`complexity_budget` block it uses (below) is the same shared schema
context-package assembly already uses, not a new convention.

Read this before running `/ult-distill-decisions` or before wiring a new
consumer against the `decision_ledger` layout slot
(`ult-repo-layout/SKILL.md`'s path-resolution algorithm; pre-D21 default
`starter_kit/decision_ledger/DECISION-LEDGER.json`, `workspace_root` leaf
`cache/decision-ledger/DECISION-LEDGER.json`).

**Format is JSON, not YAML** — unlike `COMPILED-GUIDELINES.md` and context
packages. Those are human-authored-or-skimmed prose-with-structure; this file
is a machine-read/written structured log queried under a `complexity_budget`
and only ever mutated through `decision_ledger.py`'s CLI (mirrors
`graphify_graph_path`'s `graph.json` / `md_index.py`'s index files — CEP's
existing convention for derived, script-owned artifacts — not
`compiled_guidelines`'s convention). It is still reviewed by a human on every
write, via the write-gate below — JSON diffs review fine in a PR, and
`decision_ledger.py add-entry`/`alias`/`reject-source` always emit the file
with stable key order and 2-space indent so diffs stay small and readable.

## Contents

- [Top-level shape](#top-level-shape)
- [Ledger entry](#ledger-entry)
- [Cursor (`run_state.cursors[]`) — idempotency, part 1](#cursor-run_statecursors--idempotency-part-1)
- [Tombstone (`run_state.rejected_sources[]`) — idempotency, part 2](#tombstone-run_staterejected_sources--idempotency-part-2)
- [Disposition (`hit_dispositions[]`) — the audit trail for hits](#disposition-hit_dispositions--the-audit-trail-for-hits)
- [`complexity_budget`](#complexity_budget)
- [Coverage — per aspect, not per package](#coverage--per-aspect-not-per-package)

## Top-level shape

```json
{
  "schema_version": 1,
  "entries": [ /* Ledger entry, see below */ ],
  "run_state": {
    "cursors": [ /* Cursor, see below */ ],
    "rejected_sources": [ /* Tombstone, see below */ ]
  },
  "hit_dispositions": [ /* Disposition, see below */ ]
}
```

An absent file is not an error — `decision_ledger.py` any subcommand
initializes this skeleton (empty `entries`/`cursors`/`rejected_sources`/
`hit_dispositions`) the first time it writes. A ledger with zero entries is a
legitimate, fully-valid state (a project that hasn't distilled anything yet),
distinct from a missing/corrupt file.

## Ledger entry

```json
{
  "id": "dl_<slug>_<NNN>",
  "decision": "<free text: what was decided>",
  "reasoning": "<free text: why — the part static docs usually drop>",
  "rejected_alternatives": ["<alternative considered and not chosen>", "..."],
  "topics": ["<free-form tag>", "..."],
  "source": {
    "type": "pr" | "design-doc" | "postmortem",
    "ref": "<url or repo-relative path>",
    "excerpt": "<short verbatim quote the decision/reasoning was distilled from>"
  },
  "confidence": "EXTRACTED" | "INFERRED" | "SUGGESTED",
  "distilled_by": "<distillation run id>",
  "distilled_through": "<cursor value at distillation time — traceability, not the cursor itself>",
  "created_at": "<ISO8601>",
  "aliases": [
    {
      "entry_id": "<other entry id merged into this one>",
      "merge_confidence": "EXTRACTED" | "INFERRED" | "SUGGESTED",
      "merged_by": "<distillation run id>",
      "merged_at": "<ISO8601>"
    }
  ],
  "supersedes": "<entry id>|null",
  "superseded_by": "<entry id>|null"
}
```

Notes:
- **`topics`** is the match target the trigger step (`decision_ledger.py
  query`) queries against — free-form tags distilled alongside the decision,
  not a fixed taxonomy. Distill 3-8 short, literal, domain-vocabulary tags per
  entry (e.g. `"kafka"`, `"message-queue"`, `"load-testing"`) — not
  paraphrased summaries. Query-side matching is literal-token overlap, so
  vague or over-abstracted tags silently reduce recall.
- **`confidence`** reuses CEP's existing `EXTRACTED`/`INFERRED`/`SUGGESTED`
  triple (`context-package-schema.md`) — no new vocabulary.
- **Constraint 4 (never merge, only alias) is load-bearing.** Two entries
  that describe the same underlying decision are never collapsed into one
  record — `aliases` on the surviving entry records the merge as a
  first-class, confidence-and-provenance-carrying claim, exactly like any
  other CEP claim, so a bad merge can be audited and undone without
  rebuilding the ledger. Never write a bare id into `aliases`; always the
  full object.
- `supersedes`/`superseded_by` are optional and distinct from `aliases`: a
  supersession is "this decision replaced that one" (both stay addressable,
  the old one is just no longer current); an alias is "these two records were
  the same underlying decision, distilled twice."

## Cursor (`run_state.cursors[]`) — idempotency, part 1

```json
{ "stream_id": "<e.g. github-prs, postmortems-drive>", "last_processed_id": "<id/sha/timestamp>", "advanced_at": "<ISO8601>" }
```

One entry per source stream. `decision_ledger.py distill-since <stream_id>`
only considers source artifacts newer than that stream's cursor — advanced
only past artifacts *fully* processed (entry written or explicitly
tombstoned), so an out-of-order or later-edited PR/postmortem still gets
picked up on its own merge/edit event rather than silently skipped by id
order. This resolves the idempotency tension between re-runnable distillation
and never-merge (only alias): re-running distillation over already-processed
artifacts is a no-op, not a duplicate-entry generator.

## Tombstone (`run_state.rejected_sources[]`) — idempotency, part 2

```json
{ "source_id": "<id>", "stream_id": "<...>", "rejected_at": "<ISO8601>", "rejected_by": "<human:id or distillation run id>", "reason": "<why this source was looked at and NOT distilled>" }
```

A source artifact a distillation run looked at and deliberately decided *not*
to turn into an entry (no real decision in it, duplicate of something already
captured, etc.) is tombstoned alongside the cursor advancing past it — so
that decision is neither lost nor re-proposed on the next run. A tombstoned
`source_id` is a terminal state; `decision_ledger.py` refuses to add a new
entry citing a tombstoned source without `--override-tombstone` (an explicit,
logged action, not a silent bypass).

## Disposition (`hit_dispositions[]`) — the audit trail for hits

```json
{
  "hit_id": "<context-package-local id, e.g. ihm_001>",
  "package_id": "<context package id that surfaced the hit>",
  "aspect_id": "<aspect id the hit was scoped to>",
  "matched_decision": "<ledger entry id>",
  "tier": "revise" | "proceed" | "escalate",
  "disposition": "dismissed" | "accepted" | "escalated",
  "reason": "<required for revise/escalate-tier hits, optional for proceed-tier>",
  "by": "human:<id>",
  "at": "<ISO8601>"
}
```

**Tier maps directly to legal `disposition` values** — `decision_ledger.py
disposition` rejects any combination outside this table:

| hit tier   | legal dispositions              |
|------------|----------------------------------|
| `revise`   | `dismissed`, `accepted`, `escalated` |
| `escalate` | `accepted`, `escalated`          |
| `proceed`  | `accepted` only                  |

A `proceed`-tier hit cannot be `dismissed` — the ledger already agrees with
the task, so there is nothing to overrule, only to acknowledge. `reason` is
enforced required for `revise`/`escalate` tiers, optional (routine
one-click acknowledgment) for `proceed`.

**A hit with no matching entry in `hit_dispositions[]` is `unresolved`, not
dismissed.** The ledger never treats silence as an answer — a hit nobody
acted on must stay visible in the package's next assembly and in coverage
reporting, not quietly vanish. `decision_ledger.py query` never writes to
`hit_dispositions[]`; only `decision_ledger.py disposition`, called from
`ult-context-generate/SKILL.md` Step 9, does.

## `complexity_budget`

The same shared block used across context-package assembly and derived-
package composition also bounds trip-wire queries now. Every
`decision_ledger.py query` call is bounded by one, passed as
`--budget <path-to-json>` or inline flags:

```json
{
  "max_model_calls": 0,
  "max_sub_agents": 0,
  "max_concurrent_workers": 1,
  "max_tool_calls": 1,
  "max_wall_clock_ms": 2000,
  "max_tokens": 0,
  "max_financial_cost_usd": 0,
  "max_retries": 0,
  "max_graph_writes": 0,
  "min_evidence_required": 1
}
```

`decision_ledger.py query` itself only ever spends `max_wall_clock_ms` and
`max_tool_calls`/`max_entries_scanned` (it is a single deterministic script
invocation — no model calls, sub-agents, or graph writes of its own; those
fields exist so the *same* schema can bound the agent-side steps that read
its output and author the final `institutional_memory_hits[]` entries, one
shared schema reused identically rather than a second bespoke one).
`min_evidence_required`
gates whether a candidate is surfaced as a hit at all — a candidate entry
with fewer than this many overlapping `topics` tokens is dropped, not
surfaced as a low-confidence hit.

**Hard rule, no exception:** hitting any budget field returns the best
current coverage/hits found so far, plus an explicit
`"stopped_early": true, "stop_reason": "<field that was hit>"` — never a
silent partial scan presented as complete. `decision_ledger.py query`'s JSON
output always carries `stopped_early`/`stop_reason` (`false`/`null` when the
budget wasn't hit), and `ult-context-generate/SKILL.md` Step 7.7 surfaces
that flag in the package's `ledger_coverage` block rather than dropping it.

## Coverage — per aspect, not per package

The single sharpest failure mode this schema guards against: **false
absence**, not false positives. "No hits" silently read as "no prior decision
here" when it actually means "not covered yet" lets an aspect the query never
reached masquerade as one that was checked and came up clear — the two look
identical unless coverage is reported explicitly. Never treat a zero-hit
result as clearance without checking coverage first. `decision_ledger.py
query` always reports, per aspect queried:

```json
{ "covers_through": "<cursor value>", "total_entries": 0, "entries_in_scope_for_this_aspect": 0 }
```

so zero hits on a given aspect always carries its own coverage caveat instead
of a package-wide number reading as blanket clearance for aspects the query
never actually scanned (e.g. because the budget was exhausted before
reaching them). See `context-package-schema.md`'s `ledger_coverage` field
(per-aspect, matching hit scope) for how this lands in the package.
