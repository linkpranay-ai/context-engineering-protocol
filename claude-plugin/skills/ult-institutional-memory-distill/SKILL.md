---
name: ult-institutional-memory-distill
description: Distill decisions, reasoning, and rejected alternatives from PRs, design docs, and postmortems into the project's decision_ledger, so ult-context-generate's trip-wire can surface institutional memory before new work quietly repeats settled ground.
namespace: ult
version: 0.1.0
origin: ground-up
author: Pranay Mishra
maintainer: Pranay Mishra
adapted_from: ~
upstream_version: ~
released: 2026-08-05
tags: [developer, workflow, institutional-memory, trip-wire, decision-ledger, conflict-resolution]
bundle: utilities
tier: draft
---

# Distilling Institutional Memory (Trip-Wire)

## Overview

Codebases accumulate decisions faster than anyone can remember them: "we tried Redis here and
reverted it," "legal blocked this vendor once already," "the team already decided against a
global feature flag and re-litigates it every few months." That reasoning usually lives — once —
in a merged PR's description, a design doc's "Alternatives Considered" section, or a postmortem's
root-cause writeup, and then it's gone. Nobody re-reads six-month-old PRs before starting new work,
so the same rejected path gets proposed again, argued again, and sometimes shipped again before
someone remembers why it didn't work last time.

This skill is the **distillation half** of trip-wire (`CEP-1.0-ROADMAP.md` §7): it reads a
project's own PR history, design docs, and postmortems, and turns *decisions with reasoning* —
not just decisions — into structured, queryable entries in the project's `decision_ledger`. The
**query half** lives in `ult-context-generate/SKILL.md` Step 7.7, which checks every new context
package's aspects against this ledger and surfaces a `revise`/`proceed`/`escalate` hit when
something the ledger already knows about overlaps the new work.

**Run this:**
- Once, early in a project's life, to backfill the ledger from existing history
- Again periodically, or on demand ("distill decisions from the last 20 merged PRs") — it is
  fully re-runnable; see "Idempotency" below

**Output:** entries, cursors, tombstones, and (indirectly, via `ult-context-generate`)
dispositions in the `decision_ledger` path-slot — resolved via
`ult-repo-layout/SKILL.md`'s path-resolution algorithm, same mechanism as `compiled_guidelines`.
Pre-D21 default: `starter_kit/decision_ledger/DECISION-LEDGER.json`; once
`layout.workspace_root` is set: `{workspace_root}/cache/decision-ledger/DECISION-LEDGER.json`
(a derived, script-owned artifact — see `layout-slots-registry.yaml`'s `decision_ledger` entry
for the bucket-reassignment rationale, same pattern as `compiled_guidelines`). Resolve it once
per run and substitute it for the pre-D21 default everywhere below.

**All ledger reads and writes go through `scripts/decision_ledger.py`'s CLI** — never hand-edit
the JSON file, and never reimplement its validation, tombstone-terminality, or alias logic inline.
See `references/ledger-schema.md` for the full field-level spec this script implements.

## The load-bearing principle: distill decisions with reasoning, never summaries without it

Read this before doing anything else. Everything below depends on it.

> A PR titled "Switch to Kafka" is not, by itself, a ledger-worthy decision — it's a fact anyone
> can already read from `git log`. What makes it worth distilling is the *reasoning* ("RabbitMQ
> dropped 40% of events under our peak load") and the *rejected alternative* ("we tried tuning
> RabbitMQ's prefetch first; it helped but not enough"). Without those, a future trip-wire hit
> just says "this happened" — which the ledger consumer already knew from reading the code — not
> "here's why, and here's what was already tried and didn't work," which is the only thing that
> actually prevents a repeated mistake.

If a source artifact states a decision but not its reasoning, that is exactly the "no real
decision in it" case `decision_ledger.py reject-source` (tombstone) exists for — **do not
distill a bare decision just to have an entry.** A ledger full of unreasoned decisions is worse
than a small ledger of well-reasoned ones, for the same reason a compiled-guidelines file full of
fabricated conventions is worse than none: it looks authoritative while adding nothing a reader
couldn't already see for themselves.

## Idempotency: this skill is designed to be re-run, not run once

Two mechanisms — both implemented in `decision_ledger.py`, not something you need to track
yourself — make re-running safe:

1. **Cursors** (`run_state.cursors[]`, one per source stream you name in Step 1) mean a re-run
   only considers source artifacts *newer* than what was already fully processed for that stream.
   "Fully processed" means either distilled (an entry now cites it via `distilled_through`) or
   explicitly tombstoned — never silently skipped.
2. **Tombstones** (`run_state.rejected_sources[]`) record a source you looked at and deliberately
   decided *not* to distill, so the next run doesn't re-propose it as a candidate. A tombstoned
   source is terminal — `decision_ledger.py reject-source` refuses to re-decide it without
   `--override-tombstone`, an explicit, logged action for the rare case new information changes
   the earlier call.

You do not need to remember what you distilled last time. Read the cursor, only look at what's
newer, and let the script enforce the rest.

## The flow

### Step 1 — Identify source streams

A "stream" is any single, ordered source of institutional-memory-bearing artifacts this project
has — you name it, `decision_ledger.py` just needs a stable `stream_id` string and a way for you
to tell "newer than the cursor" apart from "already covered." This skill stays deliberately
generic here: it has no built-in integration for any specific PR host, doc store, or postmortem
tool, because baking one in would make this skill only work for projects that happen to use that
tool.

Ask the user which streams this project has and how to enumerate "new since `<cursor value>`"
for each — typical answers look like:

- **PRs / merge history** — `stream_id: "prs"` (or `"github-prs"`, `"gitlab-mrs"`, whatever fits).
  Cursor is usually a commit SHA or merge date; "new" means `git log <cursor>..HEAD --merges` or
  the host's own "merged after `<date>`" API/CLI filter.
- **Design docs** — `stream_id: "design-docs"`. Cursor is often a doc ID, revision, or a folder's
  last-scanned timestamp; "new" means whatever changed or was added since.
- **Postmortems** — `stream_id: "postmortems"`. Same idea — a folder, wiki space, or doc list,
  cursor tracking the last one processed.

Auto-suggest candidates from conventional locations the same way `compiling-project-guidelines`
does (`docs/postmortems/**`, `docs/design/**`, `docs/adr/**`, the repo's own PR/MR history) —
**then show the user what you found and ask them to confirm, add, or remove streams**, including
pointing you at wherever their actual PR host, wiki, or design-doc store lives if it isn't a
conventional in-repo path. Read each stream's current cursor with
`decision_ledger.py show <ledger>` (counts only) or by reading the ledger JSON's
`run_state.cursors[]` directly (read-only — never hand-edit) to find `last_processed_id` for that
`stream_id`. A stream with no existing cursor entry is being distilled for the first time; treat
everything as "new."

### Step 2 — Enumerate candidate artifacts per stream

For each stream, gather the artifacts newer than its cursor, using whatever mechanism Step 1
established for that stream (git log, host CLI/API, folder listing + mtimes, etc.). This is
ordinary investigation — read the PRs, open the docs — not a scripted step, because "what counts
as new" is inherently specific to each project's tooling in a way `decision_ledger.py` deliberately
does not know about.

### Step 3 — Judge each candidate: distill, or tombstone

For every candidate artifact, read it and decide:

**Does it contain a genuine decision with stated (or clearly inferable) reasoning?**

- **Yes, and the reasoning is explicit in the source** → distill it (Step 4), `confidence:
  EXTRACTED`.
- **Yes, but you're inferring the reasoning from context the source doesn't state outright**
  (e.g., a PR's diff makes the "why" obvious even though the description doesn't say it) →
  distill it, `confidence: INFERRED`, and say in the entry's `reasoning` field that this is your
  inference, not a quote.
- **Maybe — there's a hint of a decision but it's genuinely unclear** → distill it, `confidence:
  SUGGESTED`, so the ledger surfaces it as a weaker-confidence hit rather than dropping it
  entirely; do not silently discard genuine uncertainty.
- **No — it's routine work, a dependency bump, a typo fix, or a decision with no recoverable
  reasoning at all** → do not distill it. Tombstone it instead:

```
decision_ledger.py reject-source <ledger.json> \
  --stream-id <stream_id> --source-id <artifact id> \
  --rejected-by <this run's id> --reason "<why this wasn't distilled>"
```

Never leave a candidate artifact neither distilled nor tombstoned when you're done with it — an
artifact in that limbo state is what re-surfaces as a duplicate candidate on the next run, which
is exactly what cursors and tombstones exist to prevent.

### Step 4 — Check for an existing entry describing the same underlying decision

**Before adding a new entry, query the ledger for topic overlap with what you're about to
distill:**

```
decision_ledger.py query <ledger.json> --aspects <topics-you'd-tag-this-with.json>
```

If a returned candidate is clearly the *same underlying decision* as what you're distilling
(e.g., a postmortem restating a decision an earlier PR already made) — **do not add a duplicate
entry.** Constraint 4 (`references/ledger-schema.md`) is load-bearing here: **never merge, only
alias.** Record the relationship instead:

```
decision_ledger.py alias <ledger.json> \
  --into <surviving entry id> --from <this candidate would-be entry id, if you'd added it> \
  --merge-confidence EXTRACTED|INFERRED|SUGGESTED --merged-by <this run's id>
```

If you haven't added the "from" entry yet, add it first (Step 5), then alias it — `alias`
requires both entries to already exist; it never invents one from a bare id. This keeps both
sources addressable and auditable rather than collapsing them into a single record that hides
which source said what.

If the candidates you find are topically related but describe a genuinely *different* decision
(narrower, later, or about a different sub-area), they are **not** duplicates — add a new entry
and, if one decision explicitly replaces another rather than merely relating to it, pass
`--supersedes <old entry id>` on `add-entry` (this sets a symmetric back-link — the old entry's
`superseded_by` is updated automatically, and the old entry stays fully addressable). Otherwise
let simple topic overlap do the connecting. Don't force an alias or supersession relationship
that doesn't actually hold.

### Step 5 — Write the entry

```
decision_ledger.py add-entry <ledger.json> \
  --decision "<free text: what was decided>" \
  --reasoning "<free text: why — the part static docs usually drop>" \
  [--rejected-alternative "<alternative considered and not chosen>"]... \
  --topic <tag> [--topic <tag>]...   (3-8 short, literal, domain-vocabulary tags -- see below) \
  --source-type pr|design-doc|postmortem --source-ref "<url or repo-relative path>" \
  [--source-excerpt "<short verbatim quote>"] \
  --confidence EXTRACTED|INFERRED|SUGGESTED \
  --distilled-by <this run's id> --distilled-through <this stream's cursor value at distillation time>
```

**Topics are the trigger's match target** — `ult-context-generate` Step 7.7 queries against them
by literal-token overlap, not semantic similarity. Tag with short, literal, domain-vocabulary
terms someone would actually use when describing related work (`"kafka"`, `"message-queue"`,
`"load-testing"`), not paraphrased summaries or single mega-tags. Under-tagging silently reduces
recall — err toward a few extra concrete tags over one abstract one.

`--source-type` is restricted to `pr`, `design-doc`, `postmortem` (the three types §7 scopes this
skill to). If a project's real source doesn't map cleanly onto one of these (a Slack thread, an
email decision), that is a real gap — don't force it into the nearest type; say so to the user and
treat it as a scope question for a future revision of this skill, not something to paper over with
a mislabeled `source_type`.

### Step 6 — Advance the stream's cursor

Once every candidate artifact gathered in Step 2 for a stream has been either distilled or
tombstoned:

```
decision_ledger.py advance-cursor <ledger.json> --stream-id <stream_id> --last-processed-id <newest artifact's id/sha/timestamp>
```

Advance **only past what was fully processed this run** — if you stopped partway through a large
backlog (budget, time, or judgment-fatigue reasons), advance the cursor only to the last artifact
you actually finished, not to the end of what you enumerated. An out-of-order or later-edited
artifact still gets picked up correctly on its own next-run pass because the cursor reflects
genuine processing progress, not enumeration progress.

### Step 7 — Validate and report

Run `decision_ledger.py show <ledger.json>` and confirm `validation_problems` is empty. Report to
the user, per stream: how many candidates were found, how many were distilled (by confidence
tier), how many were tombstoned, how many were aliased into an existing entry, and the new cursor
position. This is the same shape of summary `compiling-project-guidelines` gives after a compile
— a human-readable account of what changed and why, not just a diff.

### Step 8 — Land the ledger diff via a review PR

**The write gate (§7): ledger entries land via a dedicated review PR distinct from the source
PR's own review.** Do not commit ledger changes directly to a protected branch, and do not treat
a source PR's existing approval as having also approved the ledger entry distilled from it — the
two are reviewed separately because the ledger entry is a *new claim about why*, not just a record
that the source PR happened. Open (or add to) a PR containing only the `decision_ledger` file's
diff, with the Step 7 summary as its description, and let a human review the distilled reasoning
before it becomes queryable trip-wire material.

## What this skill deliberately does not do

- It does not decide `revise`/`proceed`/`escalate` for anything, and it never writes to
  `hit_dispositions[]`. That vocabulary belongs to a *query* against the ledger during a specific
  piece of new work (`ult-context-generate/SKILL.md` Step 7.7 and Step 9) — this skill only
  populates `entries[]`, `run_state.cursors[]`, and `run_state.rejected_sources[]`.
- It does not merge entries. Two records describing the same underlying decision are always
  `alias`-ed, never collapsed — see Step 4.
- It does not hardcode any specific PR host, wiki, or design-doc tool. Step 1 exists precisely so
  this skill adapts to whatever streams a given project actually has, rather than assuming GitHub,
  a specific wiki product, or a specific folder layout.
- It does not fabricate reasoning a source doesn't state or clearly imply. `confidence: INFERRED`
  and `confidence: SUGGESTED` exist so genuine uncertainty is recorded honestly, not smoothed over
  into false-`EXTRACTED` certainty.
- It does not gate or block anything by itself — it has no enforcement mechanism. The ledger it
  produces is read-only reference material for `ult-context-generate`'s trigger step; a human
  always makes the actual revise/proceed/escalate call at that later point.

## When something doesn't fit this flow

If a source stream's "new since cursor" enumeration genuinely can't be automated (no API, no
reliable mtime, a wiki with no revision history), say so and fall back to asking the user to name
the specific artifacts to consider this run — don't skip the stream silently, and don't guess at
what's new.

If an artifact is ambiguous between two source types, or references a decision that's already
been superseded by something else in the same batch, distill both and pass `--supersedes` when
writing the later entry (see Step 4) rather than silently dropping the older one — a superseded
decision still explains what was tried, which is exactly the "already walked this road" context
trip-wire exists to surface.
