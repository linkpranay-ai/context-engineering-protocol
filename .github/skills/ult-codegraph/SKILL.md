---
name: codegraph
description: Generate a codebase knowledge graph with `graphify` at `graphify-out/` so spw-* skills can query cross-file relationships before touching code. Do NOT use for runtime profiling.
namespace: ult
version: 0.1.0
origin: ground-up
author: Pranay Mishra
maintainer: Pranay Mishra
adapted_from: ~
upstream_version: ~
released: 2026-06-08
tags: [utility, code-graph, graphify, codebase-analysis, pilot]
bundle: utilities
tier: read
dependencies:
  runtime: [python >= 3.10, "uv or pipx"]
  external_tool: graphifyy
---

# Codebase Graph (graphify wrapper)

Wraps the external `graphify` CLI (https://github.com/safishamsi/graphify, MIT
license, distributed as the PyPI package `graphifyy`) to build a knowledge
graph of a codebase — files, functions, classes, and their
`calls`/`imports`/`uses`/`inherits` relationships — at graphify's own fixed
output location, `graphify-out/`, where other skills query it directly.

> **Status: piloting.** Validated on a real ~40 KSLOC FastAPI codebase
> (a structural lead — `seed_release_links.py → EntryMetricValue`, the
> bridge between two otherwise-separate subsystems — that a textual `grep`
> could not find, since the bridging file never mentions the target term)
> before this migration. Now rolling out to a small set of engineering
> volunteers piloting it on substantially larger codebases (500 KSLOC+),
> where `graph.json` itself can run to tens of MB and the scoped-query
> pattern below stops being optional and starts being the only thing that
> scales. Report findings (works well / doesn't / surprises) back to the
> RadiSys Skills Guild so this can graduate out of pilot status or be
> reworked.

## How to generate / refresh the graph

### Step 0 — scope the index (first run only)

Before running `graphify update` on the whole repo, take a quick look at
what's actually there:

```bash
# Top-level dirs by file count — surfaces generated/vendored/other-language subtrees
for d in */; do n=$(find "$d" -type f | wc -l); echo "$n $d"; done | sort -rn | head -10
```

Then ask: **is there one directory that holds essentially all the source you
care about**, separate from generated code, vendored third-party libraries,
or bindings for other languages?

- **Yes** — point `graphify update` at that directory instead of `.` (e.g.
  `graphify update src/ --no-cluster`). Smaller, cleaner graph; less
  cross-language noise in `affected`/`explain` results.
- **No** (everything's genuinely mixed) — run `graphify update . --no-cluster`
  on the repo root. Validated on a real ~300 KSLOC, 8-language, 2425-file
  monorepo (google/protobuf): completed in 5m28s, 73K nodes / 254K edges,
  with `affected`/`explain` queries returning in ~3s — an unscoped run on a
  messy repo is workable, just expect occasional cross-language results.

**Don't** try to index multiple separate directories and combine them with
`graphify merge-graphs` — it crashes on real graphs (`NetworkXError: All
graphs must be graphs or multigraphs`, a `DiGraph`/`MultiDiGraph` mismatch
because `graph.json` doesn't persist directed/multigraph metadata and
graphify infers it per-file from edge data). Pick one root instead.

```bash
# Install (idempotent — safe to run multiple times)
uv tool install graphifyy
# or: pipx install graphifyy

# Generate / re-extract (no LLM needed — ~10-15s for a ~40 KSLOC codebase,
# scales roughly linearly; incremental on subsequent runs; ~5.5 min at
# ~300 KSLOC). Use your Step 0 directory in place of `.` if you scoped.
graphify update . --no-cluster

# Optional: cluster into communities + generate the human-readable report.
# Community *names* require GEMINI_API_KEY/GOOGLE_API_KEY — without one they
# stay generic ("Community 0", "Community 1", ...). The underlying graph.json
# is unaffected either way; the report's other sections (God Nodes, Surprising
# Connections, Import Cycles) are useful with no LLM at all.
graphify cluster-only . --no-label
```

This writes `graphify-out/{graph.json, GRAPH_REPORT.md, graph.html,
manifest.json, cache/}` at the project root — `graphify`'s fixed working
location. It has no `--output` flag; `graphify update`/`query`/`path`/`explain`
all default-read from `graphify-out/` relative to the path you point them at,
so this directory must stay where the tool expects it for incremental updates
and queries to work.

## No normalization step — consume `graphify-out/` directly

Don't copy `graph.json`/`GRAPH_REPORT.md` to a "standard location" elsewhere
in the repo (e.g. a `starter_kit/<topic>/` folder, the colocation convention
used for `compiling-project-guidelines`'s output). A live spike
(`graphify vscode install`, inspecting the config it generates, then
`graphify vscode uninstall` to revert cleanly) showed that graphify's own
generated assistant instructions point straight at `graphify-out/graph.json`
— never at a copy. `graphify-out/` is *already* a fixed, predictable,
tool-maintained path, so copying it would only:

- duplicate a large, regenerating artifact (tens of MB at the 500 KSLOC+
  scale this pilot targets),
- risk drift between the live, incrementally-updated original and a stale
  copy nobody remembers to refresh, and
- fight the tool's own incremental-update model, which depends on
  `graphify-out/` staying exactly where `graphify` put it.

So: **`spw-*` skills read `graphify-out/graph.json` and
`graphify-out/GRAPH_REPORT.md` directly** — no copy, no second location.
See `CONSUMING-CODE-GRAPH.md` in this folder for the consumption contract
(which also explains *how* to consume it: prefer scoped `graphify query`
over reading the full files).

`graphify-out/` should be gitignored in the consuming project — it's
regeneratable, includes a large dependency cache, and ships an interactive
`graph.html` (often 1MB+). Each engineer (or CI step) regenerates it
locally with `graphify update .`.

## Refreshing after code changes

Re-run `graphify update .` (incremental — it only re-parses changed files).
Nothing to re-copy: `graphify-out/graph.json` updates in place.
`GRAPH_REPORT.md`'s "Graph Freshness" section records the commit the graph
was built from; compare it against `git rev-parse HEAD` to spot staleness.

## Measuring impact (optional, run once)

After your first `graphify update .`, you can optionally run
`graphify benchmark` — it measures token reduction vs. a naive
full-corpus-read approach on *that* codebase, giving a concrete number
("N% fewer tokens than reading every file") instead of relying on anecdote.
Worth running once per pilot codebase and including the result when
reporting findings back to the Guild — exactly the kind of evidence a
graduation-from-pilot decision wants. It's a one-off measurement, not part
of the regular query loop — no need to re-run it routinely.

## Going deeper: `--mode deep` (optional escalation — has real costs, gated)

The default `graphify update .` is AST-only: free, instant, no LLM. graphify
also offers `graphify extract . --mode deep --backend <gemini|claude|openai|
deepseek|kimi|ollama>` — "aggressive INFERRED-edge semantic extraction" that
uses an LLM to surface *conceptual* relationships the AST pass structurally
cannot see (no `calls`/`imports`/`uses` edge exists — e.g. two modules
implementing the same pattern under different names).

This is a **one-time enrichment of the persistent graph, not a per-query
cost**: it writes `[INFERRED]` edges into `graphify-out/graph.json` itself —
the same fixed location `update` writes to — so every `query`/`path`/
`explain`/`affected` afterward stays exactly as free and instant as today,
just over a richer graph. (Whether a later plain `update` preserves those
edges across a refactor, or deep mode needs re-running to refresh them, is
untested — worth checking live the first time it becomes relevant on a pilot
codebase, and reporting back what you find.)

But it costs real LLM API usage, takes meaningfully longer than the default
build, and requires a configured backend — the opposite of the "free and
instant, no API key" baseline this skill is built on. **It must never run
silently — and it must never even be offered as something a team can "just
try," because a usable backend is itself a real infrastructure decision**
(API keys plus likely a data-governance review for cloud backends, or
standing up a local Ollama on capable hardware — exactly the kind of
lab-GPU-and-maintenance question worth a separate discussion before this is
reachable at all). `CONSUMING-CODE-GRAPH.md` step 5 spells out the required
gate: check whether a usable backend is even configured *before* saying
anything actionable (if not, a one-line FYI only — never an offer), then
offer → explicit re-confirm only once one exists — the same "are you sure,
here's exactly what this costs" shape used for irreversible deletes.

## Skill folder contents

| File | Purpose |
|------|---------|
| `SKILL.md` | This instruction file |
| `CONSUMING-CODE-GRAPH.md` | Consumer-contract other skills are pointed at |

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Python** | 3.10+ | Required runtime for `graphify` |
| **uv or pipx** | any | Installs `graphifyy` as an isolated tool |
| **`graphifyy`** | latest | PyPI package providing the `graphify` CLI |

No project dependency changes — `graphify` is installed as a standalone tool
via `uv tool install` / `pipx install`, not added to the project's own
dependency manifest.

## Why wrap rather than vendor

`graphify` stays an external dependency (installed per-machine via
`uv tool install graphifyy`), not a vendored copy in this library. It's
MIT-licensed and small to fork if it ever goes unmaintained, and wrapping
keeps this skill thin: install guidance + a fixed-output-location contract,
nothing to maintain when upstream changes its internals.

`graphify` is also not the only possible backend for this contract — see
`CONSUMING-CODE-GRAPH.md`'s "Provider contract (for alternative backends)"
section for the abstract `query`/`path`/`explain`/`affected` interface a
tree-sitter- or clangd-based provider could implement as a drop-in swap.
