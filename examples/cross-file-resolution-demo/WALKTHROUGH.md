# Cross-file citation resolution demo

This is a **light** worked example of cross-file `cross_refs` resolution (R9, Phase B):
a citation like "IEEE 802.11-2020 §9.3.2" written in one file resolves to a heading in a
*different* file, joined via that file's `doc_id` front matter and looked up in
`index.json`'s corpus-wide view — never guessed. It mirrors
[`examples/how-l1-dogfood-demo/`](../how-l1-dogfood-demo/WALKTHROUGH.md)'s pattern: a
synthetic corpus proving the mechanism works end-to-end, not a comprehensive validation
against a real multi-spec corpus.

## What's real here, and what isn't

- **The corpus is synthetic.** [`corpus/spec-802-11-mac.md`](corpus/spec-802-11-mac.md)
  and [`corpus/spec-802-1x-auth.md`](corpus/spec-802-1x-auth.md) are hand-authored
  fixtures that imitate IEEE house style (dotted-numeric clauses, `§`-form cross-refs,
  a document designator like "IEEE 802.11-2020") — they are **not** derived from the
  real IEEE 802.11-2020 or 802.1X-2020 standards. Treat the *content* as demo-only.
- **The commands and output are real.** Every command and JSON block below was actually
  run against these two fixtures, using the actual `scripts/md_index.py` and the actual
  bundled `ieee` profile. Nothing here is fabricated output.

## The corpus

Two files, joined by a `doc_id` front-matter field:

- `spec-802-11-mac.md` — `doc_id: IEEE 802.11-2020`, defines clause `9.3.2 Frame Format`.
- `spec-802-1x-auth.md` — `doc_id: IEEE 802.1X-2020`, clause `12.4 EAPOL frame
  considerations` cites all three resolution outcomes at once:
  1. `IEEE 802.11-2020 §9.3.2` — a genuine **cross-file** reference, resolvable because
     the other file's `doc_id` matches exactly.
  2. `§12.4.1` — a bare, same-file reference (no designator) — resolves exactly as
     same-file citations always have, unaffected by Phase B.
  3. `IEEE 802.16-2017 §5.1` — a designator for a document that **isn't in this corpus**
     — correctly left unresolved rather than guessed.

## Step 1 — build the index

```
$ python .github/skills/ult-context-generate/scripts/md_index.py index \
    examples/cross-file-resolution-demo/corpus \
    -o examples/cross-file-resolution-demo/specs-out/index.json \
    --profile ieee

Indexed 2 file(s), 8 heading(s) -> examples/cross-file-resolution-demo/specs-out/index.json (profile=ieee)
```

`specs-out/index.json` is a build artifact, gitignored like every other `specs-out/*.json`
— regenerate it locally with the command above.

## Step 2 — query the index

```
$ python .github/skills/ult-context-generate/scripts/md_index.py query \
    examples/cross-file-resolution-demo/specs-out/index.json \
    "EAPOL frame encapsulation timer" --top 1
```

Real output:

```json
[
  {
    "file": "spec-802-1x-auth.md",
    "clause_id": "12",
    "title": "12 Port-based network access control",
    "heading_id": "h_0001",
    "line": 9,
    "section_bounds": [10, 20],
    "match_count": 9,
    "cross_refs": [
      {
        "raw": "IEEE 802.11-2020 §9.3.2",
        "kind": "section",
        "target_doc": "IEEE 802.11-2020",
        "target_clause": "9.3.2",
        "resolved_file": "spec-802-11-mac.md",
        "resolved_heading_id": "h_0003",
        "resolved": true,
        "resolution_status": "resolved"
      },
      {
        "raw": "§12.4.1",
        "kind": "section",
        "target_doc": null,
        "target_clause": "12.4.1",
        "resolved_file": null,
        "resolved_heading_id": "h_0003",
        "resolved": true,
        "resolution_status": "resolved"
      }
    ]
  }
]
```

The first `cross_refs` entry is the cross-file case: `target_doc` was matched against
`spec-802-11-mac.md`'s `doc_id`, and `resolved_file`/`resolved_heading_id` point at that
*other* file's clause `9.3.2` heading — a lookup across the corpus index, not a parsing
change, exactly as R9 specified. The second entry shows a same-file ref resolving exactly
as it did before Phase B (`target_doc: null`).

## Step 3 — the deliberately-unresolved case

The corpus's third citation, `IEEE 802.16-2017 §5.1`, doesn't appear via `query` above —
`query_index()` only surfaces `cross_refs` with `resolved: true` (by design, so a
gap-triggered agent never chases a dangling citation). It's still in the full
`index.json`, unresolved rather than dropped, per R9's "never guess":

```
$ python -c "import json; d = json.load(open('examples/cross-file-resolution-demo/specs-out/index.json', encoding='utf-8')); \
refs = [c for f in d['files'] for h in f['headings'] for c in h['cross_refs'] if c['target_clause'] == '5.1']; \
print(json.dumps(refs[0], indent=2, ensure_ascii=False))"
```

Real output (the ref appears once per heading whose section body contains it — clause
`12` and its child `12.4` both scan over the same body text, so it shows up twice in the
raw index; deduped here to one representative entry):

```json
{
  "raw": "IEEE 802.16-2017 §5.1",
  "kind": "section",
  "target_doc": "IEEE 802.16-2017",
  "target_clause": "5.1",
  "resolved_file": null,
  "resolved_heading_id": null,
  "resolved": false,
  "resolution_status": "unresolved-doc-not-found"
}
```

No file in this corpus has `doc_id: IEEE 802.16-2017` — resolution correctly stops at
`unresolved-doc-not-found` instead of picking some other file. Two more "never guess"
outcomes exist and are covered by unit tests
(`tests/test_md_index.py::TestCrossFileResolution`), not this demo, since they need a
3rd/4th synthetic file to trigger: `unresolved-doc-ambiguous` (two files share the same
`doc_id`) and the existing same-file `unresolved-ambiguous` applied after a cross-file
`doc_id` match (the matched file itself has a duplicated clause id).

## Using your own real corpus

Everything above works identically against real, properly-licensed multi-document
content — no code changes, same commands:

1. Get a corpus you're licensed to use (e.g. related IEEE, 3GPP, or RFC documents that
   cross-cite each other).
2. Add a `doc_id: <identifier>` line to each file's front matter, matching the identifier
   convention your documents actually cite each other by.
3. If your cross-reference convention isn't already covered by a bundled profile, add an
   optional `(?P<doc>...)` named group to its `cross_ref_patterns` regex alongside
   `(?P<clause>...)` — see `.github/skills/ult-context-generate/scripts/profiles/ieee.json`
   for a worked example, and the "Profile schema" section of `scripts/README.md`.
4. Run `md_index.py index <dir> --profile <yours>` over the whole corpus directory (not
   per-file) so `resolve_cross_file_refs()` has every file's `doc_id` to join against.

As with How-L1/What-L1, verify results against your own corpus before relying on
cross-file resolution in production use — this demo is a smoke test of the mechanism.
