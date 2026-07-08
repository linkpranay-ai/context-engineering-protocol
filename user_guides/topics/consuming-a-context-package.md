# Consuming a context package (10-minute guide)

You're building a skill (or a step in a larger workflow) that produces something for a specific
feature — a design note, a test plan, a code review, a debug writeup. This guide is about the
one thing that skill should do *before* it starts: check whether an approved context package
already exists for this feature, and if so, use it instead of free-reading the repo.

This is the friendly on-ramp. For the full formal contract — tag discovery, multi-package
addenda, supersession, item-level tags — read
[`CONSUMING-CONTEXT-PACKAGE.md`](../../.github/skills/ult-context-generate/CONSUMING-CONTEXT-PACKAGE.md)
once you need those edge cases. For a working example you can read end-to-end or copy from,
see [`demo-consume-context`](../../.github/skills/demo-consume-context/SKILL.md).

## The five things to do

### 1. Check whether a package exists

Look in `contexts/` for a file matching `<feature-slug>_<task-type>_*.yaml` with
`human_approved: true`.

- **Not found** → proceed however your skill normally would (read the code, check compiled
  guidelines if relevant). Don't tell the user to go run `/ult-context-generate` — that's a
  heavier step than this quick check warrants.
- **Found** → continue.

### 2. Confirm with the user, in one line

> "Found a context package for this feature (`<id>`, generated `<date>`, human_approved) — use
> it as primary context for this work?"

### 3. Load it as primary context

Read the package's `decisions_log`, `context_items`, `gaps_detected`, and `summary`. Treat this
as your starting point instead of re-reading the whole repo. If a sibling
`<feature-slug>_<task-type>_<date>.addenda.yaml` file exists, read that too — newest entries
first.

Two item types are worth handling specially:

- Any `context_items` entry with `what_l1_fallback: true` is an external-reference suggestion
  (a 3GPP/ISO/IEEE-style spec excerpt, or occasionally a live web-search result) that already
  passed human review — but it describes what an external source says, not what *this product*
  does. If your work touches that topic, say so explicitly: "this package includes an
  external-reference suggestion for `<topic>` — treat as informative, not authoritative."
- Entries also carry `source: file:line-range` where possible — that's your citation. Use it
  when you write your own output.

### 4. Do a quick freshness spot-check — not a full re-run

Before relying on the package, spend thirty seconds confirming it's still true:

- Re-read 2–3 `context_items` whose source is a `file:line-range` — does the code still say
  what the package claims?
- If a compiled-guidelines file exists, is its date newer than the package's `generated_at`?

Two outcomes, handled differently:

- **A fact simply moved on** (code changed since the package was generated, nothing was
  "decided" either way) — note it, write a short addendum (step 5 below), and keep going. Tell
  the user in one line; don't block on it.
- **A decision is contradicted** (the current code disagrees with something the package's
  `decisions_log` says was *decided*) — **stop and ask**: "`<topic>` was decided as `<X>` in
  the approved package, but the code now does `<Y>` — is this a bug, or should the decision be
  revisited?" Don't proceed on that part of the work until you get an answer.

### 5. Write what you found back as an addendum

If something came up during your work that the package didn't cover, do one small, targeted
lookup — not a full re-scan — then append it to
`contexts/<feature-slug>_<task-type>_<date>.addenda.yaml` (create the file if it doesn't exist
yet) so the next skill that touches this feature doesn't have to look it up again:

```yaml
addenda:
  - id: add_001
    kind: context_item        # or: decision
    added_by: <your-skill-name>
    added_at: <ISO timestamp>
    note: >
      <one line — what you were looking up, and why>
    # then the normal context_items shape: id/layer/source/type/confidence/summary
```

Never edit the approved package file itself — only ever append to its `.addenda.yaml` sibling.
Folding addenda back into the approved package is `ult-context-generate`'s job, not yours.

## Close the loop: say what you used

At the end of your work, state in one line which mode you were in:

- `"Context package consulted: <id>@<hash8> (human_approved, generated <date>; <N> addenda
  read, <M> written)"`
- or `"No context package found — proceeding without it."`

If your output is a persisted file (not just a chat response), add a
`**Context package(s):** <id>@<hash8>` line near its top — that's the citation a future reader
follows back to the source of truth.

## When you're ready for more

- Multiple packages cited by one feature, tag-based discovery from a pasted user story,
  supersession chains, item-level tags for tracker integrations — all covered in
  [`CONSUMING-CONTEXT-PACKAGE.md`](../../.github/skills/ult-context-generate/CONSUMING-CONTEXT-PACKAGE.md).
- Want to see this whole loop run end-to-end against a real package? Run
  [`demo-consume-context`](../../.github/skills/demo-consume-context/SKILL.md) — it's a small,
  from-scratch skill that does exactly the five steps above and nothing else.
- Want to understand *why* packages look the way they do — the gap/conflict/staleness checks
  that produced them? See [`PROTOCOL.md`](../../PROTOCOL.md).
