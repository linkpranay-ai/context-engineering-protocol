# Telecom What-L1 demo: indexing a 3GPP-style spec corpus

This is a worked example of the **What-L1** layer (external reference ingestion) described in
[`PROTOCOL.md`](../../PROTOCOL.md#2-the-layer-model) — status "piloting" — using a telecom/3GPP
corpus, because clause-numbered spec documents (`7.2.9.2`, `Annex A.3`, `(see clause 7.5)`) are
exactly the kind of structured external reference this mechanism was built for.

## What's real here, and what isn't

- **The corpus is synthetic.** [`corpus/sample-3gpp-style-spec.md`](corpus/sample-3gpp-style-spec.md)
  is a hand-authored fixture describing a fictional "Enhanced Synchronized Beacon Procedure"
  (ESBP) — it is **not** real 3GPP spec text. Real 3GPP text (even via datasets like
  Hugging Face's TSpec-LLM) is gated/copyrighted and isn't freely redistributable into this
  Apache-2.0 public repo — the same call this repo already made once, in
  `.github/skills/ult-codegraph/scripts/IMPLEMENTATION-NOTES.md`, for a different validation
  corpus. The fixture imitates real 3GPP/ETSI clause-numbering and cross-reference *conventions*
  faithfully, so the mechanics below are representative — but treat the *content* as demo-only.
- **The commands and output are real.** Every command below was actually run against the fixture
  in this repo, using the actual `scripts/md_index.py` and the actual bundled `3gpp` profile
  (`.github/skills/ult-context-generate/scripts/profiles/3gpp.json`). Nothing here is fabricated
  output.

## Step 1 — build the index

```
$ python .github/skills/ult-context-generate/scripts/md_index.py index \
    examples/telecom-what-l1-demo/corpus \
    -o examples/telecom-what-l1-demo/specs-out/index.json \
    --profile 3gpp

Indexed 1 file(s), 31 heading(s) -> examples/telecom-what-l1-demo/specs-out/index.json (profile=3gpp)
```

`specs-out/index.json` is a build artifact, not checked into this repo — it embeds an absolute
filesystem path (`root`) that's specific to whoever generates it, so it's gitignored like every
other `specs-out/*.json` (see `starter_kits/context_engineering/context-config.yaml.template`).
Run the command above yourself to regenerate it locally.

The `3gpp` profile (see its pattern-pack above) tells the indexer two things: how to recognize a
clause id at the start of a heading (`7.2.9.2`, `A.3`, `5.3.4a`), and how to recognize cross-refs
in body text (`clause 7.5`, `Annex A.3`, `(see clause 7.4)`). Against the 31 headings in the demo
corpus, it correctly parsed clause ids at every depth used — top-level (`7`), two levels
(`7.2`), three levels (`7.2.9`), and four levels (`7.2.9.2`) — plus the two annexes (`A`, `A.3`).

## Step 2 — query the index

```
$ python .github/skills/ult-context-generate/scripts/md_index.py query \
    examples/telecom-what-l1-demo/specs-out/index.json \
    "drift correction" --top 3
```

Real output (trimmed — the full run returns a resolved `cross_refs` list per match; shown in full
for the second and third ranked results below):

```json
[
  {
    "clause_id": null,
    "title": "TS XX.999: Synthetic Demo Specification for Enhanced Synchronized Beacon Procedure (ESBP)",
    "line": 15,
    "match_count": 40,
    "...": "(whole-document root section — always ranks first; match counts aggregate hierarchically)"
  },
  {
    "clause_id": "7",
    "title": "7 Detailed procedures",
    "heading_id": "h_0014",
    "line": 87,
    "section_bounds": [88, 146],
    "match_count": 23,
    "cross_refs": [
      {"raw": "clauses 4", "kind": "clause", "target_clause": "4", "resolved_heading_id": "h_0006", "resolved": true},
      {"raw": "clause 7.2.9.1", "kind": "clause", "target_clause": "7.2.9.1", "resolved_heading_id": "h_0019", "resolved": true},
      {"raw": "clause 5.2", "kind": "clause", "target_clause": "5.2", "resolved_heading_id": "h_0010", "resolved": true},
      {"raw": "clause 7.3", "kind": "clause", "target_clause": "7.3", "resolved_heading_id": "h_0021", "resolved": true},
      {"raw": "clause 7.4", "kind": "clause", "target_clause": "7.4", "resolved_heading_id": "h_0022", "resolved": true},
      {"raw": "clause 7.2", "kind": "clause", "target_clause": "7.2", "resolved_heading_id": "h_0016", "resolved": true}
    ]
  },
  {
    "clause_id": "7.5",
    "title": "7.5 Drift correction",
    "heading_id": "h_0023",
    "line": 132,
    "section_bounds": [133, 146],
    "match_count": 15,
    "cross_refs": [
      {"raw": "clause 7.3", "kind": "clause", "target_clause": "7.3", "resolved_heading_id": "h_0021", "resolved": true},
      {"raw": "clause 7.4", "kind": "clause", "target_clause": "7.4", "resolved_heading_id": "h_0022", "resolved": true}
    ]
  }
]
```

Two things worth noticing in this real output:

1. **`clause_id` is parsed structurally, not guessed.** `"7.5 Drift correction"` becomes
   `clause_id: "7.5"` with a clean display title — the indexer never touches an LLM to do this.
2. **Cross-refs resolve to concrete headings.** `"clause 7.3"` inside clause `7.5`'s body text
   resolves to `resolved_heading_id: "h_0021"` — the indexer can hop from one clause to another
   it cites, which is exactly what "clause 7.5 references clause 7.3's drift measurement" means
   in the source text. (This resolution is single-hop and same-file today — see
   [`ROADMAP.md`](../../ROADMAP.md) for cross-file/multi-hop resolution status.)

## Step 3 — how this feeds `ult-context-generate`

This indexed query isn't meant to be run by hand during normal use — `ult-context-generate`'s
Step 7.1 runs it automatically, but **only for aspects that are a "both-layers-gap candidate"**
(no What-L2 requirements coverage and no What-L3 code coverage for that aspect). If your feature
touches something your own requirements docs and code graph are silent on, and it's plausibly
covered by the corpus you pointed `what_l1.path` at, this indexer is queried and any match
becomes a `context_items` entry tagged `what_l1_fallback: true`.

Every one of those items is then surfaced in its own reviewer block —
`[L1 FALLBACK ITEMS — REVIEW]` — at the human-approval step. Nothing from this layer enters an
approved context package silently: a human confirms or rejects each suggested item, because a
match from an external spec describes what the *industry* (or in this demo, a fictional
standard) says, not necessarily what *your product* actually does or requires.

## Using your own real corpus

Everything above works identically against real, properly-licensed spec content — no code
changes, same commands:

1. Get a corpus you're licensed to use — your org's internal specs, or a properly licensed
   external standard (e.g. one you've downloaded and accepted the license terms for).
2. Drop `.md` excerpts under a directory of your choosing (e.g. `specs/external/`).
3. In your project's `context-config.yaml`:
   ```yaml
   what_l1:
     enabled: true
     path: specs/external/
     md_index_profile: 3gpp   # or: generic | rfc | ieee | <your-own-profile>.json
     index_path: specs-out/index.json
     graphify_budget: 20
   ```
4. Run `/ult-context-generate` as usual — Step 7.1 builds and queries the index for you.

If your corpus uses a different clause-numbering or cross-reference convention than 3GPP/ETSI,
write your own pattern-pack — copy
`.github/skills/ult-context-generate/scripts/profiles/3gpp.json` as a starting point and adjust
`clause_id_regex` / `cross_ref_patterns` to match your source's conventions, then pass its name
via `md_index_profile`.
