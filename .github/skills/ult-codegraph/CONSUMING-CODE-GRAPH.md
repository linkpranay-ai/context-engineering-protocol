# How a consuming skill should consume the code graph

> **Status: piloting** — this contract is being validated on large
> codebases (500 KSLOC+), where `graph.json` itself can be tens of MB.
> Report findings as an issue in this repo so this can graduate out of
> pilot status.

Any skill that reads, writes, modifies, reviews, or judges project code/tests
should follow this before doing that work:

1. Check whether `graphify-out/graph.json` exists (graphify's own fixed
   output location at the project root — there is no normalized copy; see
   `ult-codegraph/SKILL.md` for why).
   - **Not present:** proceed exactly as you normally would. Don't ask the
     user to generate one — this is an optional aid, not a requirement.
   - **Present:** continue to step 2.

2. **Prefer scoped runtime queries over reading the full graph.** Run
   `graphify query "<question>" --budget N` (a budget-capped traversal that
   returns a small, relevant slice of the graph — much cheaper than loading
   `graph.json` wholesale, and the only approach that scales once a codebase
   is large enough that `graph.json` is tens of MB). Use
   `graphify path "<A>" "<B>"` for "how does A relate to B" relationship
   questions, `graphify explain "<concept>"` for focused-concept lookups, and
   `graphify affected "<X>" --depth N` for "what depends on this" / blast-radius
   questions — a reverse traversal from a symbol to everything that would be
   impacted by changing it (use before modifying or removing something
   widely-used, or when checking whether a change's stated impact is complete).
   These four are your **first action** once you know the graph exists —
   try them before reading any file.

   Triggers for reaching for these commands: "how do I…", "where is…",
   "what does … do", "add/modify a `<component>`", "explain the
   architecture", or anything that depends on how files, functions, or
   classes relate to each other — exactly the kind of question a `grep`
   across raw source can miss (it finds text matches, not structural edges
   like `calls`/`imports`/`uses`/`inherits`).

   A practical note on which command to reach for: `graphify path`/
   `graphify explain` are sharper and cheaper when you can already name the
   symbols or files involved — they return a precise, scoped answer in a
   single hop with no noise. Free-text `graphify query "<question>"` is for
   when you can't yet name the symbols; expect to iterate on phrasing, add
   `--budget`/`context_filter`/`--dfs`, or fall through to the options below
   if the traversal anchors on the wrong start nodes (e.g. documentation
   headings instead of code) or gets truncated by the budget before reaching
   anything useful.

   Fall back, in order, only when the scoped query doesn't surface enough:
   - `graphify-out/wiki/index.md`, if present, for broad navigation.
   - `graphify-out/GRAPH_REPORT.md` for a broad architecture review (God
     Nodes, Surprising Connections, Import Cycles, community groupings) —
     read this when the question is bigger than a scoped query can answer,
     not as a routine first step.
   - Raw source files — read these when (a) you're modifying or debugging
     specific code and need the actual implementation, (b) the graph lacks
     the detail you need, or (c) the graph is missing or stale (see step 4).

   Treat edges marked `[INFERRED]` (lower confidence, called out in
   `GRAPH_REPORT.md`'s "Surprising Connections") as worth a second look,
   not as ground truth.

3. State, in one line, which mode you used:
   "Code graph consulted: `graphify query \"<question>\"` returned `<N>`
   related nodes for `<paths>`" — or "No code graph found — proceeding
   without it" if `graphify-out/graph.json` is absent.

4. Staleness nudge (cheap, non-blocking): `graphify-out/GRAPH_REPORT.md`'s
   "Graph Freshness" section records the commit the graph was built from.
   If `git rev-parse HEAD` differs, mention it in one line ("the code graph
   looks stale — built from `<old-commit>`, current is `<head>`; consider
   re-running `/ult-codegraph`") and continue — don't block on it.

5. **Going deeper, only when steps 2–4 still come up empty (gated — ask,
   never run silently).** If you suspect a relationship exists that the
   scoped queries, report, and source all miss — and it feels *conceptual /
   semantic* rather than *structural* (no `calls`/`imports`/`uses`/`inherits`
   edge would capture it; e.g. "these two modules implement the same retry
   pattern under different names") — graphify can run a deeper, LLM-backed
   extraction that infers exactly these edges:
   `graphify extract . --mode deep --backend <gemini|claude|openai|deepseek|
   kimi|ollama>`. It bakes the result into `graphify-out/graph.json` itself
   as `[INFERRED]` edges — a **one-time enrichment of the persistent graph**,
   not a per-question cost. Every `query`/`path`/`explain`/`affected`
   afterward stays exactly as free and instant as today, just over a richer
   graph. (Whether a later plain `graphify update` preserves those edges
   across a refactor, or deep mode needs re-running to refresh them, is
   untested — treat it as an open question worth noting the first time it's
   relevant, not an assumed fact.)

   But it costs real LLM API usage, takes meaningfully longer than the
   default free build, and requires a backend configured (API key, or a
   local Ollama) — the opposite of the "free and instant" baseline this
   skill is built on. **Gate it behind a check-then-confirm sequence — the
   same shape you'd use to confirm an irreversible delete, plus a
   precondition check first so the option is never dangled unusably:**
   - **Stage 0 — check before offering:** look for a usable backend (an env
     var like `GEMINI_API_KEY`/`GOOGLE_API_KEY`/`OPENAI_API_KEY`/
     `ANTHROPIC_API_KEY`/etc., or a running local `ollama`).
     - **None configured:** don't offer it as an actionable option — that
       would dangle a feature the team can't use yet. Mention it once, in
       passing, as an FYI only — *"there's a deeper extraction mode for
       cases like this, but it needs an LLM backend configured first —
       that's a team-level infrastructure decision (API keys plus a likely
       data-governance review for cloud backends, or standing up a local
       Ollama), not something to set up inline"* — then continue with what
       you already have. Don't dwell on it or re-raise it later.
     - **A backend is configured:** continue to Stage 1.
   - **Stage 1 — offer:** explain *why* (the cheap graph came up empty and
     this looks semantic, not structural) and *what it costs* (LLM API
     calls, several minutes, the backend that's configured) — then ask if
     they'd like you to try it.
   - **Stage 2 — confirm:** only if they say yes, restate concretely what's
     about to happen — *"this will call `<backend>` across chunks of the
     codebase, cost real API usage, take several minutes, and rewrite
     `graphify-out/graph.json` with the enriched result — proceed?"* — and
     wait for a second, explicit yes.
   - Run it only after that second yes. If they decline at Stage 1 or
     Stage 2, drop it, continue with what the cheap graph + source already
     gave you, and don't re-offer later in the same session.

---

This file is the single source of truth for "how does a consuming skill
consult the generated code graph." It is referenced by a one-line pointer
from each consuming skill's `.prompt.md`/`SKILL.md` — not copied into each
one — so the protocol is written, reviewed, and updated in exactly one
place. The contract's own trigger (step 1: "any skill that reads, writes,
modifies, reviews, or judges project code/tests") is broad; during a pilot
rollout, a maintainer may choose to wire in only a deliberately-limited
subset of consuming skills first, so the pattern stays trivial to revert
or adjust before it earns a wider rollout.

Candidates worth wiring in first, and why: a skill that plans a change or
diagnoses a problem (helped directly by a structural map); a skill that
answers "is this a new feature or an extension of something that already
exists" (a scoped `graphify query`/`explain` on the proposed feature's
domain concepts can answer this even when naming differs enough that grep
would miss the overlap); a skill that surfaces a change's blast radius
before write-up, or checks whether a reviewer claim like "this might break
X" is structurally grounded (both the same "what depends on this"
question, just from opposite sides of the loop). Skills whose core loop
centers on an immediate function/task rather than codebase-wide structure
are natural candidates to wire in later, once the pilot validates the
pattern more broadly — the value there is less obvious to assess up front.

It is colocated with `ult-codegraph/SKILL.md` — the skill that produces the
artifact this file describes how to consume — so anyone changing one sees the
other and keeps them in sync. This mirrors the
`compiling-project-guidelines/CONSUMING-COMPILED-GUIDELINES.md` pattern
(same shape: fixed standard location, non-blocking optional check, one-line
attribution, cheap staleness nudge) deliberately, for the same reason that
pattern was chosen there: predictable, reviewable, and trivial to extend or
revert without touching the skills that consume it.

The "prefer scoped queries first" guidance in step 2 is adapted from
graphify's own generated assistant config (observed live via
`graphify vscode install`, then cleanly reverted with `graphify vscode
uninstall`) — its own `## graphify` instructions tell the assistant to run
`graphify query "<question>"` as the first action and fall back to the
report or raw files only when that doesn't surface enough. We follow the
same consumption shape here, wired through our own governed skill/contract
files and bundle system instead of graphify's global, ungoverned
platform-installer output (which writes outside any project's bundle,
catalog, or distribution mechanism).

---

## Provider contract (for alternative backends)

The four verbs used in step 2 — `query`, `path`, `explain`, `affected` — are
the **abstract interface** every consuming skill in this contract depends on.
`graphify` is the current reference implementation (an external MIT-licensed
CLI, installed via `uv tool install graphifyy` — see `ult-codegraph/SKILL.md`
"Why wrap rather than vendor"). A different backend — e.g. a tree-sitter- or
clangd-based indexer — could be substituted with **no changes to any
consuming skill**, as long as it implements this same CLI shape and output
fields. This section documents that shape as a swap point; it does not build
an alternative.

### `graphify query "<question>" [--budget N] [--dfs] [--context_filter ...]`

- **Input:** free-text question or symbol/concept name.
- **Behavior:** BFS (default) or DFS traversal from nodes matching the query
  text, capped at `--budget` nodes (default 2000). Returns a node list with a
  truncation note ("... N more nodes cut") if the budget was exhausted before
  the traversal completed.
- **Output fields per node:** label, `src=<file>:<line>` (absent for
  non-code nodes, e.g. doc headings), and any edges discovered during the
  traversal, each tagged `[EXTRACTED]` (AST-derived, high confidence) or
  `[INFERRED]` (heuristic or LLM-derived, lower confidence — see the deep
  extraction section of `ult-codegraph/SKILL.md`).
- **Consumer expectation:** pick a budget large enough that the truncation
  note doesn't cover symbols you actually care about; re-run higher if it
  does (`CONTEXT-ENGINEERING-DESIGN.md` D16).

### `graphify path "<A>" "<B>"`

- **Input:** two node labels.
- **Behavior:** finds a relationship path between A and B through the
  graph's edges.
- **Output:** the path as a sequence of nodes/edges, or "no path found."
- **Consumer expectation:** use when you can name both endpoints and want to
  know *how* they relate — cheaper and more precise than a free-text `query`.

### `graphify explain "<label>"`

- **Input:** an exact node label. **The `()` suffix on function/method
  labels is significant** — `explain "ClearCache"` and
  `explain "ClearCache()"` are different lookups; only the latter resolves
  for a function (2026-06-11 learning, `learnings.md`).
- **Output:** the node's ID, source location (`file:line`), **degree**
  (edge count — a rough measure of how central/connected the symbol is), and
  its connections, each tagged `[EXTRACTED]`/`[INFERRED]` as above.
- **Consumer expectation:** the standard step before `affected` — resolve the
  exact, `()`-suffixed label here, then pass that label to `affected`.

### `graphify affected "<label>" [--depth N]`

- **Input:** an exact node label (as resolved by `explain`); traversal depth
  bounds how far the reverse traversal goes.
- **Behavior:** reverse traversal — everything that (transitively, up to
  `--depth`) depends on `<label>`, i.e. the blast radius of changing it.
- **Output:** a list of dependent nodes, or "No affected nodes found."
- **Consumer expectation:** "No affected nodes found" for a correctly-resolved
  but **low-degree (≤~5) node is normal, not a dead end** — pivot to a
  higher-degree, structurally-related node (e.g. the class/type the symbol
  belongs to) and re-run `affected` there before concluding "self-contained,
  no dependents" (`CONTEXT-ENGINEERING-DESIGN.md` D16).

### Known limitations of the reference implementation (`graphify`)

Properties of the *current* backend, not the abstract interface — an
alternative provider could improve on these without any consumer-side change:

- **Multi-root merges aren't at the default location.** `graphify merge-graphs`
  works (`graphifyy >= 0.9.11` — see `ult-codegraph/SKILL.md` Step 0), but its
  output isn't under `graphify-out/`, so it isn't picked up by the "present /
  not present" check in step 1 above. If a project has been indexed as
  multiple merged roots, every query command needs an explicit
  `--graph <path>` pointing at the merge output.
- **Cross-file edges are `[INFERRED]` (heuristic symbol-matching), not
  `[EXTRACTED]`** — confirmed correct on real C++ (re2, protobuf), including
  through `#ifdef`/`#if defined(...)` blocks (2026-06-11, `learnings.md`), but
  still a heuristic. Treat `[INFERRED]` edges as "worth a second look," per
  step 2 above.
