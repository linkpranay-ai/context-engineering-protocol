---
name: codegraph
description: Generate a codebase knowledge graph with `graphify` at `graphify-out/` so other skills can query cross-file relationships before touching code. Do NOT use for runtime profiling.
namespace: ult
version: 0.2.0
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
  external_tool: "graphifyy >= 0.9.11"
---

# Codebase Graph (graphify wrapper)

Wraps the external `graphify` CLI (https://github.com/safishamsi/graphify, MIT
license, distributed as the PyPI package `graphifyy`) to build a knowledge
graph of a codebase — files, functions, classes, and their
`calls`/`imports`/`uses`/`inherits` relationships — at graphify's own fixed
output location, `graphify-out/`, where other skills query it directly.

> **Status: piloting.** Validated on a real ~40 KSLOC FastAPI codebase
> (a structural lead — `webhook_dispatcher.py → RetryPolicy`, the bridge
> between two otherwise-separate subsystems — that a textual `grep` could
> not find, since the bridging file never mentions the target term)
> before this migration. Now rolling out to a small set of engineering
> volunteers piloting it on substantially larger codebases (500 KSLOC+),
> where `graph.json` itself can run to tens of MB and the scoped-query
> pattern below stops being optional and starts being the only thing that
> scales. Report findings (works well / doesn't / surprises) as an issue in
> this repo so this can graduate out of pilot status or be reworked.

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
- **No, but multiple genuinely independent roots** (e.g. sibling repos or
  workspace directories with no shared parent worth scoping to) — index each
  root separately, then combine:

  ```bash
  graphify update root-a/ --no-cluster
  graphify update root-b/ --no-cluster
  graphify merge-graphs root-a/graphify-out/graph.json \
    root-b/graphify-out/graph.json --out merged.json
  ```

  Node IDs are repo-tag-prefixed (`root-a::foo`, `root-b::bar`) so there's no
  collision risk. `merged.json` isn't under a `graphify-out/` directory, so
  point every query command at it explicitly with `--graph`:
  `graphify query "..." --graph merged.json`,
  `graphify explain "X" --graph merged.json`, same for `path`/`affected`.
  **Requires `graphifyy >= 0.9.11`** — verified broken on 0.8.35
  (`NetworkXError: All graphs must be graphs or multigraphs`, because that
  `graph.json` carried no `directed`/`multigraph` keys at all; 0.9.11's does).
  Upgrade first (`uv tool install --force graphifyy`) if you hit that error.

**If this repo has itself consumed CEP** (i.e. it was set up with
`install.ps1`/`install.sh` from this library), a `.cep-install.json` file
sits at the repo root recording exactly which paths CEP installed
(`owned_paths`) — that's CEP's own tooling content, not the codebase you're
trying to graph, and indexing it just adds noise to `query`/`explain`
results (and, worse, inflates in-degree/tier numbers for whatever real
modules happen to sit near CEP's installed paths — `ult-autoscaffold-content`
warns about exactly this if it slips through). Before your first
`graphify update`, check for that file and, if present, merge its
`owned_paths` into `.graphifyignore` — one entry per line.

No CLI flag is needed to enable this: `.graphifyignore` is auto-discovered
next to the directory you point `graphify update` at, the same way
`.gitignore` is, and is evaluated after `.gitignore` (confirmed against the
published `graphifyy` package docs, 2026-08-31). `graphify --help` not
listing an ignore-file option is expected — it's not a sign the file is
being ignored.

`.graphifyignore` is a file the adopter may also want to write in
themselves (build output, fixture trees, anything else they never want
indexed), so this recipe **must not regenerate the whole file**. Write the
manifest-derived entries into a marked block instead, exactly the way the
installer maintains its block inside `AGENTS.md`: everything between the
BEGIN/END markers is CEP's to rewrite on every run, everything outside them
is the adopter's and is left byte-for-byte alone. That covers all three
states — no `.graphifyignore` yet (create it holding just the block), one
that exists without the block (append the block, keep the existing lines),
one that already has the block (replace only the block in place, keeping the
lines before and after it in their original order).

```bash
BEGIN_MARK='# --- BEGIN CEP-managed entries (auto-generated, do not edit) ---'
END_MARK='# --- END CEP-managed entries ---'

if [ -f .cep-install.json ]; then
  {
    printf '%s\n' "$BEGIN_MARK"
    python3 -c "import json; [print(p) for p in json.load(open('.cep-install.json')).get('owned_paths', [])]"
    printf '%s\n' "$END_MARK"
  } > .cep-block.tmp

  if [ -f .graphifyignore ] && grep -qF "$BEGIN_MARK" .graphifyignore; then
    awk -v b="$BEGIN_MARK" 'index($0,b)==1{exit} {print}' .graphifyignore > .cep-before.tmp
    awk -v e="$END_MARK" 'f{print} index($0,e)==1{f=1}' .graphifyignore > .cep-after.tmp
    cat .cep-before.tmp .cep-block.tmp .cep-after.tmp > .graphifyignore.new
    mv .graphifyignore.new .graphifyignore
    rm -f .cep-before.tmp .cep-after.tmp
  elif [ -f .graphifyignore ]; then
    { cat .graphifyignore; printf '\n'; cat .cep-block.tmp; } > .graphifyignore.new
    mv .graphifyignore.new .graphifyignore
  else
    cp .cep-block.tmp .graphifyignore
  fi
  rm -f .cep-block.tmp
fi
```

```powershell
$beginMark = '# --- BEGIN CEP-managed entries (auto-generated, do not edit) ---'
$endMark   = '# --- END CEP-managed entries ---'

if (Test-Path -LiteralPath .cep-install.json) {
    $owned = (Get-Content -LiteralPath .cep-install.json -Raw | ConvertFrom-Json).owned_paths
    $block = (@($beginMark) + @($owned) + @($endMark)) -join "`n"

    if (Test-Path -LiteralPath .graphifyignore) {
        $current = Get-Content -LiteralPath .graphifyignore -Raw
        if ($current.Contains($beginMark)) {
            $pattern = [regex]::Escape($beginMark) + "[\s\S]*?" + [regex]::Escape($endMark)
            $evaluator = { param($match) $block }
            $new = [regex]::Replace($current, $pattern, $evaluator)
        }
        else {
            $new = $current.TrimEnd("`r", "`n") + "`n`n$block`n"
        }
    }
    else {
        $new = "$block`n"
    }
    Set-Content -LiteralPath .graphifyignore -Value $new -NoNewline
}
```

Confirm the exact syntax your installed `graphifyy` version expects via
`graphify --help` — ignore-file handling has evolved across releases,
including whether `#` comment lines are tolerated; if this version rejects
them, keep the same merge shape and pick marker lines it does accept. But
the source of truth for *what* goes inside the block is always the
manifest's `owned_paths`, never a hand-maintained list — and anything the
adopter put outside the block stays theirs.

```bash
# Install (idempotent — safe to run multiple times)
uv tool install graphifyy
# or: pipx install graphifyy

# Generate / re-extract (no LLM needed — ~10-15s for a ~40 KSLOC codebase,
# scales roughly linearly; incremental on subsequent runs; ~5.5 min at
# ~300 KSLOC). Use your Step 0 directory in place of `.` if you scoped.
graphify update . --no-cluster

# Verify the run actually produced a graph (the 2026-08-31 Round-2 evaluation's finding on the codegraph sanity-check invocation not being runnable as documented,
# 2026-08-31) — see the paragraph below the "Together, these write..." note.
# Treat a nonzero exit here the same as `graphify update` itself failing.
python scripts/check_graphify_output.py .

# Optional: cluster into communities + generate the human-readable report.
# Community *names* require GEMINI_API_KEY/GOOGLE_API_KEY — without one they
# stay generic ("Community 0", "Community 1", ...). The underlying graph.json
# is unaffected either way; the report's other sections (God Nodes, Surprising
# Connections, Import Cycles) are useful with no LLM at all.
graphify cluster-only . --no-label
```

Together, these write `graphify-out/{graph.json, GRAPH_REPORT.md, graph.html,
manifest.json, cache/}` at the project root — `graphify`'s fixed working
location. It has no `--output` flag; `graphify update`/`query`/`path`/`explain`
all default-read from `graphify-out/` relative to the path you point them at,
so this directory must stay where the tool expects it for incremental updates
and queries to work.

**Always run `check_graphify_output.py` immediately after `graphify
update`.** On Windows specifically, `graphify update`'s internal watch/
rebuild step has been observed to fail with `[WinError 5] Access is denied`
while giving no further detail at all — no path naming which file it
couldn't access, no retry, and no exit-code/console signal reliably
distinguishing "ran to completion" from "silently gave up after creating an
empty `graphify-out/cache/`." `check_graphify_output.py` (stdlib-only, no
new dependency) distinguishes four states — never ran, partial failure
(`graphify-out/cache/` exists, `graph.json` doesn't — the exact repro above),
present but empty/corrupt, and genuinely ok — and exits nonzero with
Windows-specific troubleshooting for the first three. Don't proceed to
`graphify query`/`path`/`explain`/`affected` on a graph this check flags as
failed; treat it the same as `graphify update` itself having failed.

**`GRAPH_REPORT.md`/`graph.html` are produced by the `cluster-only` step, not
by `graphify update . --no-cluster` alone.** If a consuming skill's flow only
ran the first command (`--no-cluster` skips clustering by design), those two
files won't exist yet — treat their absence as expected, not an error, and
fall back to `graph.json` directly (or suggest running `graphify cluster-only`
if a report is actually needed).

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

So: **consuming skills read `graphify-out/graph.json` and, when present,
`graphify-out/GRAPH_REPORT.md` directly** — no copy, no second location.
`GRAPH_REPORT.md` isn't produced under `--no-cluster` (the default
invocation above); treat its absence as expected, not an error. See
`CONSUMING-CODE-GRAPH.md` in this folder for the consumption contract
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
If `GRAPH_REPORT.md` isn't present (`--no-cluster` was used without a
follow-up `cluster-only` run), skip the staleness nudge rather than treating
its absence as an error.

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
| `scripts/check_graphify_output.py` | Post-`graphify update` sanity check — run it every time (see "How to run" above) |

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Python** | 3.10+ | Required runtime for `graphify` |
| **uv or pipx** | any | Installs `graphifyy` as an isolated tool |
| **`graphifyy`** | >= 0.9.11 | PyPI package providing the `graphify` CLI — older versions (verified through 0.8.35) crash on `graphify merge-graphs` |

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
