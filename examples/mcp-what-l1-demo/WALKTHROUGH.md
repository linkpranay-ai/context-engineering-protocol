# MCP What-L1 demo: mirror-then-index sourcing (ROADMAP items 9 + 11)

This demo walks through `mcp_mirror.py`, the real mechanism `references/what-l1-fallback-query.md`
Step 0 and `references/how-l1-fallback-query.md` Step 0 use to mirror MCP-fetched content into
local `.md` files before the existing `md_index.py` index build. It answers ROADMAP item 9's
original open question — "what does an MCP-fetched source do for source-attribution/content-hash
discipline, given it has no file and no mtime?" — with real, run commands and real output. It
mirrors [`examples/telecom-what-l1-demo/`](../telecom-what-l1-demo/WALKTHROUGH.md)'s worked-example
format.

## What's real here, and what isn't

- **The "MCP fetch" is synthetic.** [`mock-source/page_kb-204.json`](mock-source/page_kb-204.json)
  is a hand-authored fixture (`{"body": "<markdown text>"}`) standing in for what an MCP tool call
  (e.g. a Confluence `confluence_getContent` call) would return, in place of Step 0 actually calling
  an MCP tool. This repo is public OSS, so nothing from a real org's MCP-connected systems
  (Confluence, Drive, etc.) ever touches this repo — the same licensing reason
  `telecom-what-l1-demo` and `how-l1-dogfood-demo` already document for real 3GPP/process-standard
  text. In the real procedure (Step 0 of either fallback-query doc), the agent calls the configured
  MCP tool directly and writes its result to a scratchpad JSON file shaped the same way
  (`{"body": "<fetched text>"}`); this fixture stands in for that scratchpad file.
- **The mirror script and `md_index.py` are real, shipped, and unmodified by this demo.**
  [`../../.github/skills/ult-context-generate/scripts/mcp_mirror.py`](../../.github/skills/ult-context-generate/scripts/mcp_mirror.py)
  is the actual script Step 0 invokes — not a prototype. `md_index.py` itself is **not touched at
  all**, which is the entire point of this design: it doesn't need to be. Every command below was
  actually run against these fixtures; nothing here is fabricated output.

## The design

What-L1 (and How-L1) are 100% mtime-based (`md_index.py index --stale-check` rebuilds only when a
local `.md` file's mtime is newer than the index) and file-path-attributed
(`source: <file>.md (<clause_id>)`). MCP content has neither a file nor an mtime.

The fix: **MCP becomes a way to populate the input directory, not a new content-item type.**
`mcp_mirror.py` reads fetched content (from a scratchpad JSON file the agent just wrote, or —
here — this demo's synthetic fixture standing in for one), computes an 8-hex content hash
(`content_hash8`, reused directly from `content_hash.py`), and compares it against the hash
recorded for that source the last time it ran:

- **Hash unchanged** → the mirror `.md` file is left untouched — its mtime doesn't move.
- **Hash changed (or the file is new)** → the mirror `.md` file is (re)written, which naturally
  bumps its mtime.

Because the only thing `md_index.py --stale-check` ever looks at is mtime, this composes for free:
content-hash comparison decides *whether* a mirror file's mtime moves, and everything downstream —
indexing, querying, citation-following — runs against the mirror directory exactly like any other
local corpus, with zero code changes. The mirror directory itself
(`what_l1.mcp_mirror_path`/`how_l1.mcp_mirror_path`, default `<path>/.mcp-mirror/`) is a
*subdirectory* of `what_l1.path`/`how_l1.path` — `md_index.py`'s `gather_md_files()` already
recurses (`target.rglob("*.md")`), so mirrored files are picked up by the existing single-directory
`md_index.py index <path>` call with no index-command change.

## Step 1 — first fetch and mirror

```
$ python .github/skills/ult-context-generate/scripts/mcp_mirror.py mirror \
    --spec-file examples/mcp-what-l1-demo/fetch-specs.json \
    --mirror-dir examples/mcp-what-l1-demo/mirror \
    --manifest examples/mcp-what-l1-demo/mcp_mirror_manifest.json

written (new): kb-204-sync-config -> kb-204-sync-config.md
```

[`fetch-specs.json`](fetch-specs.json) names one spec: a Confluence-style page (`mock:KB-204`),
its content pointed at by `content_file`, mirrored to `kb-204-sync-config.md`. The mirror file
carries an attribution header comment recording exactly what a `context_items` entry's `source:`
field would need — server, tool, identifier, fetch time, and content hash:

```
<!-- mcp-mirror: server=confluence-dc tool=confluence_getContent identifier=mock:KB-204
     fetched_at=2026-07-09T08:12:41.207713+00:00 content_hash=1955fb5f -->

# KB-204: Beacon Sync Configuration Reference (Engineering Wiki)
...
```

`mcp_mirror_manifest.json` now has one entry recording that same `content_hash8` and `fetched_at`.

## Step 2 — index and query the mirror (md_index.py, completely unmodified)

```
$ python .github/skills/ult-context-generate/scripts/md_index.py index \
    examples/mcp-what-l1-demo/mirror \
    -o examples/mcp-what-l1-demo/specs-out/index.json \
    --profile generic --stale-check

Index stale - rebuilding: examples/mcp-what-l1-demo/specs-out/index.json
Indexed 1 file(s), 5 heading(s) -> examples/mcp-what-l1-demo/specs-out/index.json (profile=generic)

$ python .github/skills/ult-context-generate/scripts/md_index.py query \
    examples/mcp-what-l1-demo/specs-out/index.json \
    "drift correction window" --top 1
```

Real output (trimmed to the top result). Note `cross_refs` now also carries `target_doc`,
`resolved_file`, and `resolution_status` — fields added since this demo was first drafted, by
`md_index.py`'s cross-file citation resolution (ROADMAP item 1 Phase B):

```json
[
  {
    "file": "kb-204-sync-config.md",
    "clause_id": null,
    "title": "KB-204: Beacon Sync Configuration Reference (Engineering Wiki)",
    "heading_id": "h_0000",
    "line": 3,
    "section_bounds": [4, 28],
    "match_count": 15,
    "cross_refs": [
      {"raw": "clause 3.1", "kind": "clause", "target_clause": "3.1", "target_doc": null,
       "resolved_heading_id": "h_0002", "resolved_file": "kb-204-sync-config.md",
       "resolution_status": "resolved_same_file", "resolved": true},
      {"raw": "clause 3.2", "kind": "clause", "target_clause": "3.2", "target_doc": null,
       "resolved_heading_id": "h_0003", "resolved_file": "kb-204-sync-config.md",
       "resolution_status": "resolved_same_file", "resolved": true}
    ]
  }
]
```

Cross-reference resolution (D14, citation-following) works identically to a hand-authored local
corpus — `md_index.py` has no idea (and needs no idea) that `kb-204-sync-config.md` came from an
MCP fetch instead of a human dropping a file into a directory.

## Step 3 — re-fetch with unchanged upstream content: confirm the no-op

```
$ python .github/skills/ult-context-generate/scripts/mcp_mirror.py mirror \
    --spec-file examples/mcp-what-l1-demo/fetch-specs.json \
    --mirror-dir examples/mcp-what-l1-demo/mirror \
    --manifest examples/mcp-what-l1-demo/mcp_mirror_manifest.json

unchanged: kb-204-sync-config -> kb-204-sync-config.md
```

The mirror file's mtime is untouched by this run (the manifest's recorded `content_hash8` matches,
so `mirror_one()` returns `"unchanged"` before ever calling `write_text`). Re-running the index
build confirms the existing `--stale-check` mechanism sees exactly what it expects:

```
$ python .github/skills/ult-context-generate/scripts/md_index.py index \
    examples/mcp-what-l1-demo/mirror \
    -o examples/mcp-what-l1-demo/specs-out/index.json \
    --profile generic --stale-check

Index up to date (profile=generic, 1 inputs): examples/mcp-what-l1-demo/specs-out/index.json
```

## Step 4 — simulate the upstream page actually changing

[`mock-source/page_kb-204.v2.json`](mock-source/page_kb-204.v2.json) is the same page with its
drift-correction window revised from 40 to 60 microseconds — standing in for someone editing the
real wiki page between runs. Copying it over the original fixture and re-running the *same* spec
(same identifier, same command) simulates a live re-fetch that comes back different:

```
$ cp examples/mcp-what-l1-demo/mock-source/page_kb-204.v2.json \
     examples/mcp-what-l1-demo/mock-source/page_kb-204.json
$ python .github/skills/ult-context-generate/scripts/mcp_mirror.py mirror \
    --spec-file examples/mcp-what-l1-demo/fetch-specs.json \
    --mirror-dir examples/mcp-what-l1-demo/mirror \
    --manifest examples/mcp-what-l1-demo/mcp_mirror_manifest.json

written (changed): kb-204-sync-config -> kb-204-sync-config.md
```

The mirror file is rewritten (new `content_hash`, new `fetched_at`, mtime advances), and
`--stale-check` correctly rebuilds — again, with no special-casing:

```
$ python .github/skills/ult-context-generate/scripts/md_index.py index \
    examples/mcp-what-l1-demo/mirror \
    -o examples/mcp-what-l1-demo/specs-out/index.json \
    --profile generic --stale-check

Index stale - rebuilding: examples/mcp-what-l1-demo/specs-out/index.json
Indexed 1 file(s), 5 heading(s) -> examples/mcp-what-l1-demo/specs-out/index.json (profile=generic)
```

Re-querying confirms the indexed content actually changed — the mirrored file now reads:

```
a resynchronization cycle is triggered. The default window was revised to 60
microseconds (up from 40) in the 2026-07 wiki update; values outside 30-90
```

(`mock-source/page_kb-204.json` is restored to its original v1 content after this demo runs, so
re-running Steps 1-4 from a clean checkout reproduces the same sequence.)

## Without `mcp_source` configured: nothing here runs at all

This whole demo exercises `what_l1.mcp_source`/`how_l1.mcp_source`, which default to `[]`. A
project that never sets them never invokes `mcp_mirror.py` — Step 0 of both fallback-query docs
checks for a non-empty list and, finding none, skips straight to the unchanged Step 1 index build
over hand-dropped `.md` files. That path is exactly what
[`telecom-what-l1-demo`](../telecom-what-l1-demo/WALKTHROUGH.md) and
[`how-l1-dogfood-demo`](../how-l1-dogfood-demo/WALKTHROUGH.md) already demonstrate end-to-end, so
it isn't re-derived here — this demo is additive to those, not a replacement.

## What this validates

1. **Zero changes to `md_index.py`.** The existing indexer/query/citation-following machinery
   treats a mirrored file exactly like any other local `.md` file — proven by running it unmodified
   against `mirror/` above.
2. **Content-hash comparison substitutes for mtime as the fetch-layer change signal, and composes
   cleanly with the existing mtime-based `--stale-check` one layer down.** Unchanged content never
   touches the mirror file's mtime; changed content always does.
3. **Source attribution survives the round trip.** The manifest (and the mirror file's own header)
   carries server + tool + identifier + `fetched_at` + `content_hash8` — enough to build a
   `source:` string for a `context_items` entry that is just as traceable as today's
   `source: <file>.md (<clause_id>)` local-file citations.
4. **The `.mcp-mirror/` subdirectory convention needs no index-command change**, because
   `md_index.py`'s `gather_md_files()` already recurses into subdirectories of the path it's given.

## How this plugs into Step 7.1 today

This is no longer a sketch — it's implemented. `references/what-l1-fallback-query.md`'s Step 0 (and
`references/how-l1-fallback-query.md`'s identical Step 0) runs exactly the sequence demonstrated
above, with two differences from this demo:

- Step 1 of that procedure (call the MCP tool, write `{"body": ...}` to a scratchpad file) is a
  real MCP tool call in the live procedure, not a hand-authored fixture.
- The mirror/index/query commands above are otherwise identical to what Step 0 → Step 1 actually
  run, using `what_l1.mcp_mirror_path`/`what_l1.mcp_manifest_path` (or the `how_l1.*` equivalents)
  from `context-config.yaml` in place of this demo's `examples/mcp-what-l1-demo/mirror` and
  `mcp_mirror_manifest.json` paths.

See `context-config.yaml.template`'s `what_l1`/`how_l1` blocks for the `mcp_source` /
`mcp_mirror_path` / `mcp_manifest_path` keys, and `scripts/README.md`'s `mcp_mirror.py` section for
the CLI reference.

## How-L1 works identically

`how_l1.mcp_source` follows the exact same shape and mechanism, mirroring into
`how_l1.mcp_mirror_path` (default `<how_l1.path>/.mcp-mirror/`) instead of `what_l1`'s. There's no
separate demo directory for it — the only difference from everything above is which
`context-config.yaml` block supplies the paths and which fallback-query doc's Step 0 runs it. This
also resolves ROADMAP item 11's original open question about whether an infrequently-revised
external standards body and a frequently-revised internal org QMS source need two different
staleness/attribution treatments: content-hash comparison is agnostic to how often a source
changes — a frequently-revised source just means the mirror rewrites more often — so one mechanism
correctly handles both without special-casing.
