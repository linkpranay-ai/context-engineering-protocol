# How-L1 dogfood demo: querying a process-standard corpus

This is a **light** worked example of the **How-L1** layer (org-wide process-standard fallback)
described in [`PROTOCOL.md`](../../PROTOCOL.md#5-how-l1--gap-triggered-task-type-scoped-piloting)
— status "piloting" — proving the mechanism works end-to-end against a small synthetic corpus. It
mirrors [`examples/telecom-what-l1-demo/`](../telecom-what-l1-demo/WALKTHROUGH.md)'s pattern for
What-L1. A **comprehensive** validation (real/licensed corpus, multiple task types, a live
`ult-context-generate` agent run through Step 2.1 and Step 9's review block) is deliberately out of
scope here — see `ROADMAP.md`'s "Comprehensive How-L1 validation (pre-1.0 gate)" item.

## What's real here, and what isn't

- **The corpus is synthetic.** [`corpus/sample-process-standard.md`](corpus/sample-process-standard.md)
  is a hand-authored fixture ("CMS-100") describing fictional configuration-management clauses — it
  is **not** derived from any real CMMI, ISO 9001, or IEEE document. It imitates the dotted-numeric
  clause-numbering and in-text `(see 5.1)`-style cross-reference conventions those documents use, so
  the mechanics below are representative, but treat the *content* as demo-only.
- **The commands and output are real.** Every command below was actually run against the fixture in
  this repo, using the actual `scripts/md_index.py` and the actual bundled `generic` profile — the
  same profile `how_l1.md_index_profile` defaults to in
  `starter_kits/context_engineering/context-config.yaml.template`. Nothing here is fabricated
  output.

## Step 1 — build the index

```
$ python .github/skills/ult-context-generate/scripts/md_index.py index \
    examples/how-l1-dogfood-demo/corpus \
    -o examples/how-l1-dogfood-demo/specs-out/index.json \
    --profile generic

Indexed 1 file(s), 7 heading(s) -> examples/how-l1-dogfood-demo/specs-out/index.json (profile=generic)
```

`specs-out/index.json` is a build artifact, gitignored like every other `specs-out/*.json` (see
`.gitignore`) — regenerate it locally with the command above.

## Step 2 — query the index for a task type

Per `references/how-l1-fallback-query.md` step 2, the agent curates 2-4 process-terminology
synonyms for the task type. For a "handle a change request" task type:

```
$ python .github/skills/ult-context-generate/scripts/md_index.py query \
    examples/how-l1-dogfood-demo/specs-out/index.json \
    "change control board disposition approved rejected deferred" --top 2
```

Real output:

```json
[
  {
    "file": "sample-process-standard.md",
    "clause_id": null,
    "title": "CMS-100: Synthetic Demo Configuration Management Process Standard",
    "heading_id": "h_0000",
    "line": 1,
    "section_bounds": [2, 38],
    "match_count": 19,
    "cross_refs": [
      {"raw": "(see 5.1)", "kind": "see", "target_clause": "5.1", "resolved_heading_id": "h_0002", "resolved": true}
    ]
  },
  {
    "file": "sample-process-standard.md",
    "clause_id": "5",
    "title": "5 Configuration Management",
    "heading_id": "h_0001",
    "line": 7,
    "section_bounds": [8, 30],
    "match_count": 19,
    "cross_refs": [
      {"raw": "(see 5.1)", "kind": "see", "target_clause": "5.1", "resolved_heading_id": "h_0002", "resolved": true}
    ]
  }
]
```

Two things worth noticing:

1. **Ranking works as intended.** `--top 2` returns the whole-document root and clause `5`
   (parent of the change-control content) — not the unrelated `6 Verification` / `6.1 Peer Review`
   clauses, which score lower against these terms and are correctly excluded.
2. **`clause_id` is parsed structurally** (`"5"`, not guessed from prose), matching the `generic`
   profile's `^(\d+(?:\.\d+)*)\s+(.+)$` heading regex.

## Step 3 — citation-following (D14)

Neither returned heading *is* clause `5.1` (`h_0002`) — but both cite it via `(see 5.1)`, and both
resolve it (`resolved: true`, `resolved_heading_id: "h_0002"`). Per
`references/how-l1-fallback-query.md` step 4, this is exactly the case that triggers
citation-following: `h_0002` is looked up in the same file's `headings` array and its
`section_bounds` are read too, even though it never appeared in the top-K query results itself.

Reading `sample-process-standard.md` lines 8-30 (clause `5`'s `section_bounds`) and 13-18 (clause
`5.1`'s `section_bounds`, via citation-following) gives the real source text those context items are
paraphrased from below.

## Step 4 — hand-assembled context items

Per `references/how-l1-fallback-query.md` step 4's template and
`references/context-package-schema.md`'s `layer: how-l1` example shape:

```yaml
- id: ctx_001
  layer: how-l1
  source: "examples/how-l1-dogfood-demo/corpus/sample-process-standard.md (5 Configuration Management)"
  type: process-standard
  confidence: EXTRACTED
  summary: >
    The process standard requires a baseline to be established for each work product on
    completion of its defining review; once baselined, a work product may only be changed
    through the change control procedure — a change control board reviews each proposed change
    against the baseline's original acceptance criteria and records its disposition (approved,
    rejected, or deferred) before the change is merged. Status and change history must be
    tracked and made available to affected stakeholders. Note that org-QMS applicability has
    not been confirmed.
  how_l1_fallback: true

- id: ctx_002
  layer: how-l1
  source: "examples/how-l1-dogfood-demo/corpus/sample-process-standard.md (5.1 Baseline Identification)"
  type: process-standard
  confidence: EXTRACTED
  summary: >
    A baseline is established for each work product upon completion of its defining review, is
    uniquely identified, and is then placed under configuration control — no further changes are
    permitted except through the change control procedure. Found via citation-following from "5
    Configuration Management". Note that org-QMS applicability has not been confirmed.
  how_l1_fallback: true
```

Both items are schema-conformant with no `aspect_id`/`aspect` field (How-L1 is task-type-scoped, not
aspect-scoped) — confirming the reference doc's template is actually fillable from real
`md_index.py` output, not just internally consistent on paper. `how_l1_fallback_count` would be
incremented to `2` and `how_l1_covered` set to `true` for this package.

## Step 5 — how this feeds `ult-context-generate`

This indexed query isn't meant to be run by hand during normal use — `ult-context-generate`'s Step
2.1 runs it automatically, but **only when Step 2's How-L2 check finds no relevant content for the
task type** (D8 — "How dimension complete gap"), and once per package rather than per aspect. Unlike
What-L1, there's no separate web-search/training-knowledge fallback here: if How-L1 also finds
nothing, Step 2's existing D8 prompt ("(a) use my best-practice suggestion / (b) I'll provide the
template myself") is what surfaces next.

Every How-L1 item is gated at Step 9's `[HOW-L1 FALLBACK ITEMS — REVIEW]` block — nothing from this
layer enters an approved context package silently. A match describes what the *organization's
process* requires, not necessarily what *this project* already does — the same "informative, not
automatically authoritative" caveat that applies to What-L1 items applies here too.

## Using your own real corpus

Everything above works identically against real, properly-licensed process-standard content — no
code changes, same commands:

1. Get a corpus you're licensed to use — your org's internal QMS documents, or a properly licensed
   external standard (CMMI, ISO 9001, IEEE process standards, etc.).
2. Drop `.md` excerpts under a directory of your choosing (e.g. `org/process-standards/`).
3. In your project's `context-config.yaml`:
   ```yaml
   how_l1:
     enabled: true
     path: org/process-standards/
     md_index_profile: generic   # or: 3gpp | rfc | ieee | <your-own-profile>.json
     index_path: specs-out/how_l1_index.json
     graphify_budget: 20
   ```
4. Run `/ult-context-generate` as usual — Step 2.1 builds and queries the index for you, gap-triggered
   off Step 2's How-L2 check.

If your corpus uses a different clause-numbering or cross-reference convention, write your own
pattern-pack — copy `.github/skills/ult-context-generate/scripts/profiles/generic.json` (or
`ieee.json`, closer to IEEE house style with `§9.3.2`-form cross-refs) as a starting point and adjust
`clause_id_regex` / `cross_ref_patterns` to match your source's conventions, then pass its name via
`md_index_profile`.

**Leave `how_l1.enabled: false` in production use until you've run this against your own corpus and
confirmed the results look right** — this demo is a smoke test of the mechanism, not a substitute for
verifying it against your actual process documents. See `ROADMAP.md`'s "Comprehensive How-L1
validation (pre-1.0 gate)" item for what a fuller validation pass still needs to cover.
