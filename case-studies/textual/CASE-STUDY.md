# Case Study: Textualize/textual

```yaml
case: textual-focus-chain-and-sparkline-baseline
codebase: Textualize/textual, MIT, ~90k LOC Python (TUI framework)
date_run: 2026-07-06 (Run A) / 2026-07-24 (Run B)
author: dogfooding run, context-engineering-oss
negative_control: true
```

This case bundles two independent runs of the same protocol against the same pinned clone of
Textual: **Run A**, an ordinary feature-add task, and **Run B**, a deliberate negative control.
Textual was chosen for the negative-control role specifically *because* Run A had already
established real, deep familiarity with its structure — making it possible to identify a
genuinely self-contained task with confidence rather than guess one cold. Sections below cover
each run in turn; §5–§8 are split A/B where the two runs diverge, and merged where they don't.

## Results at a glance

| Metric | Without CEP (naive keyword search) | With CEP | Kind |
| --- | --- | --- | --- |
| Run A: `focus_chain` exemplar (`screen.py:772`) | Found — `focus_chain` greps clean to the real definition | Found (What-L3) | Measured |
| Run A: `_check_disabled()` integration point (`widget.py:832`) | Not found by keyword — the task's own wording ("disabled widgets shouldn't be focusable") has no term bridging to `_check_disabled`; broadening to `grep "disabled"` matches 10 files, not disambiguating which one | Found (What-L3) | Measured |
| Run A: naive read cost to confirm both real sites | `screen.py`+`widget.py` in full, 23,751 words (~31,668 tokens) | 1,346 words (~1,795 tokens) — the generated context package, ~17.6x fewer tokens | Measured |
| Run B: naive read cost (negative control) | `sparkline.py` alone, 551 words (~735 tokens) | 902 words (~1,203 tokens) — the generated context package | Measured |
| Run B: cheaper path | **Naive wins** — reading the file directly costs ~1.6x fewer tokens than the full CEP package for this self-contained target | — | Measured |
| `graphify benchmark` reduction (whole `src/` corpus) | naive-full-corpus-read baseline | 39.6x fewer tokens/query (20,116 nodes / 59,448 edges) | Measured |

**Retrospective, not blind** (`EVIDENCE-METHODOLOGY.md` §7): the `focus_chain`/`disabled` queries
above are the natural first greps a developer would try from the task's own wording, run after
both runs' real answers were already known — not reverse-engineered from CEP's citations, but not
a controlled blind trial either. Run B's row is the sharpest honest result across all three cases:
this is the one place in the whole program where the naive baseline is cheaper than CEP, not just
competitive — exactly what a negative control is supposed to be able to show.

## 1. Environment

Both runs used the same disposable clone: `Textualize/textual`, tag `v8.2.8`, commit
`1d99508b928a771b51e1a527319c6b87dcff9e05` (2026-06-30), cloned to a sibling directory
(`dogfood-textual/`). CEP commit: the `ult-context-generate` skill and `graphify` CLI as they
stood at the time of each run (`graphifyy` PyPI package, installed via `pipx`). Runtime: no live
interactive coding agent session — both runs were executed directly via `graphify` CLI calls and
manual invocation of `ult-context-generate`'s scripts, with every point that normally asks a human
a question self-answered and explicitly flagged as simulated (see §6).

Setup: `context-config.yaml` hand-edited once for the whole clone —
What-L3 `path: src/` (budget 50), What-L2 `path: docs/guide/` (budget 30, indexed via
`md_index.py` into `specs-out/l2_index.json`, `md_index_profile: generic`), What-L1 disabled,
How-L2 `path: .` cached to `org-conventions/`, `graphify.graph_path: graphify-out/graph.json`.
The code graph (`graphify update`) was built once and reused for both runs: 20,496 nodes / 59,448
links.

## 2. Task

**Run A (ordinary):** Allow a disabled `Button` (and, more generally, disabled widgets) to remain
part of the keyboard focus chain instead of being fully skipped, so a keyboard-only user can Tab
to a disabled control and discover why it's disabled, while keeping it inert to activation.

**Run B (negative control):** Add an optional baseline marker to the `Sparkline` renderable: when
a dataset contains both positive and negative values, draw a visually distinguishable row/column
at the zero value so the sign change is visible at a glance.

Run B's target was not picked arbitrarily. Files under `src/textual/` were ranked by external
in-graph connectivity (incoming references from outside their own file); `Sparkline`
(`src/textual/renderables/sparkline.py`) came out at the low end — 0 external incoming
references, degree 7 overall — making it a plausible candidate for a task where CEP's
context-assembly machinery has little to actually surface.

## 3. Source set

Identical for both runs: What-L3 populated from `src/` (whole-repo scope, no include/exclude
narrowing needed — the corpus is small enough to fit the 50-node budget per query). What-L2
populated from `docs/guide/` (30-file budget), indexed via `md_index.py` rather than direct-read
(corpus exceeds the configured `large_corpus_threshold`). How-L2 populated from
`starter_kit/project_guidelines/COMPILED-GUIDELINES.md`, one `## Global` section plus a single
`tests/snapshot_tests/**` scoped section (not applicable to either task). No `discover`/
`confirm-layers` workflow was needed — `context-config.yaml` was hand-edited once, up front,
since this is a one-off dogfood run rather than an unfamiliar codebase being onboarded.

## 4. Package generation

**Run A:** `ult-context-generate` produced `contexts/disabled-widget-focusable_feature-add_20260706.yaml`.
What-L3 hits: `Screen._focus_chain` (`screen.py:808`), `Widget._check_disabled()` (`widget.py:832`).
What-L2 hit: `docs/guide/input.md:120`. One aspect (a2, the feature itself) was a complete gap in
both layers — expected for a not-yet-built feature.

**Run B:** produced `contexts/sparkline-baseline-marker_feature-add_20260724.yaml`
(`content_hash: 62a9b119`, verified as a stable fixed point by re-running
`scripts/content_hash.py` after the fact). `graphify explain "Sparkline"` resolved the renderable
class unambiguously (degree 7: `rich.style.Style` plus its own four methods). What-L2: zero
matches for "sparkline" anywhere in `docs/guide/`, confirmed independently via both a direct grep
and an `md_index.py` query. `graphify affected` on the resolved renderable node returned "No
affected nodes found" — per the skill's Step 4.5 fallback rule (don't trust an empty result at
face value on a degree-≤5 node), the query was retried against the structurally-related widget
wrapper class (`src/textual/widgets/_sparkline.py`, also degree 7), which returned exactly one
real dependent: the package's shared lazy-import `__getattr__` (`widgets/__init__.py:102`) — a
mechanism every widget goes through, not anything Sparkline-specific.

## 5. Detected gaps, conflicts, staleness

**Run A:** No conflicts — What-L2 and What-L3 agreed on current (pre-change) behavior; `docs/guide/input.md:120`
already documents disabled widgets as non-focusable, so the target feature is a documented-behavior
change, not a silent one. One complete gap (aspect a2), correctly classified as expected for a
feature-add rather than flagged as a tooling miss.

**Run B:** No conflicts — What-L2 has no coverage of `Sparkline` at all, so there is nothing to
contradict. One gap, What-L2-only (not both-layers, since What-L3 is fully covered) — expected for
a small renderable that likely never warranted its own guide page. Nothing here is itself a
finding about the tool; the checks fired correctly and reported an honest "not much here."

One real tooling observation surfaced during Run B, logged separately rather than here per
`TEMPLATE.md`'s instruction to keep tool-defect findings out of this section: `graphify query`'s
broad BFS search for the bare term `"Sparkline"` returns 96 mostly-unrelated nodes, because the
graph's pre-#1504 node-ID scheme collides two distinct classes that share that literal name
(`renderables/sparkline.py` and `widgets/_sparkline.py`). `graphify explain`'s exact-label
resolution was unaffected. Logged as `DEF-001` (Low, deferred) in the governance-side defect log.

## 6. Approval decision

Neither run had a live human reviewer available (disposable dogfood clone, no active development
session). Every Step 9-equivalent approval, along with Step 1 scope clarification, Step 7.2 gap
handling (Run A only), and Step 7.5 open-question resolution, was self-answered by the operator
running the tooling and is explicitly flagged as simulated inside each package's YAML — this is
disclosed here rather than presented as a genuine human-in-the-loop approval. Both packages were
marked `human_approved: true` only in this simulated sense.

## 7. Downstream use

Neither package was handed to a downstream coding agent to actually implement the feature — both
runs stopped at package generation and are reported as such. This case measures the
context-assembly step in isolation, not an end-to-end task completion.

## 8. Outcome

**Run A — partially measured, partially inference:** the package correctly surfaced the two real
code sites that gate focus, and the one real documentation contract that would need updating, for
a task that does have genuine cross-file structure (a DOM-traversal-level implementation detail, a
public widget-level flag, and a documented behavior contract, in three different files). The naive
baseline in "Results at a glance" is now measured: a `focus_chain` grep finds the `screen.py` site
for free but has zero hits in `widget.py`, and the task's own wording gives no keyword bridging to
`_check_disabled()` — confirming both real sites naively costs 23,751 words (~31,668 tokens) versus
the package's 1,346 words (~1,795 tokens), ~17.6x fewer tokens. What remains inference is narrower:
whether that token/precision gap translates into less developer time, which is a judgment call,
not a controlled comparison.

**Run B — measured:** the tool's own outputs are the evidence. `graphify explain` correctly
reported a low-degree, self-contained node; `graphify affected`'s fallback path correctly reported
a single generic (non-feature-specific) dependent after the low-degree pivot; the What-L2 gap
check correctly reported zero documentation coverage. All three are real tool outputs pointing to
the same conclusion: for this task, CEP's context-assembly overhead does not surface anything a
developer opening `sparkline.py` directly wouldn't see in under a minute. Now backed by a real
number, not just the assertion: `sparkline.py` alone is 551 words (~735 tokens) versus the
generated package's 902 words (~1,203 tokens) — reading the file directly is cheaper. This is the
case's deliberate negative-control finding, reported plainly rather than reframed as a success.

## 9. Limitations

Both runs are single-task, single-codebase, no-live-reviewer dogfood runs — they say nothing about
CEP's behavior on a larger or more tangled corpus, on a task type other than feature-add, or with a
real human making the Step 1/7.5/9 decisions instead of an operator self-answering them. The
naive-keyword-search baseline in "Results at a glance" is real but retrospective, not blind — the
`focus_chain`/`disabled`/`sparkline.py` queries reuse this case's own reproduction steps, run after
both runs' answers were already known (`EVIDENCE-METHODOLOGY.md` §7). Run B's
"self-contained" finding is specific to one renderable class chosen for low external connectivity;
it should not be read as "CEP adds nothing for small modules in general" without more negative-
control cases across different codebases.

## 10. Lessons learned

CEP's gap/conflict/blast-radius checks behaved correctly and honestly in both a case where they
had real signal to report (Run A) and a case where they had almost none (Run B) — including
correctly triggering the Step 4.5 fallback rule on Run B's first (empty) `graphify affected`
result rather than accepting it at face value. The one tooling wrinkle observed (`graphify
query`'s same-name-collision noise, `DEF-001`) is a graph-build configuration gap in upstream
`graphify`, not a defect in CEP's own logic, and does not change either run's conclusions since
`graphify explain` was unaffected.

## Reproduction steps

1. Clone the pinned corpus: `git clone https://github.com/Textualize/textual.git dogfood-textual
   && cd dogfood-textual && git checkout v8.2.8` (commit `1d99508b928a771b51e1a527319c6b87dcff9e05`).
2. Copy this repo's `context-engineering-oss` starter kit into the clone (`.github/skills/`,
   `starter_kit/`, `context-config.yaml` per §1 above).
3. Build the code graph: `graphify update . --no-cluster` (from the clone root). Expect roughly
   20,496 nodes / 59,448 links.
4. Build the What-L2 index: `python .github/skills/ult-context-generate/scripts/md_index.py
   build --path docs/guide/ --out specs-out/l2_index.json`.
5. **Run A:** invoke `ult-context-generate` with the task text from §2 (Run A). Expect What-L3
   hits at `screen.py:808` and `widget.py:832`, a What-L2 hit at `docs/guide/input.md:120`, and one
   complete gap on the feature aspect itself.
6. **Run B:** invoke `ult-context-generate` with the task text from §2 (Run B). Expect
   `graphify explain "Sparkline"` to resolve to a degree-7 node; `graphify affected` on that node
   to return empty, requiring the Step 4.5 pivot to the widget wrapper class's node ID to get the
   one real dependent (`widgets/__init__.py:102`); and zero What-L2 matches for "sparkline".
7. Compare your package's `content_hash` against this case's recorded values
   (`sparkline-baseline-marker_feature-add_20260724.yaml`: `62a9b119`) by running
   `python .github/skills/ult-context-generate/scripts/content_hash.py contexts/<id>.yaml` — a
   match confirms a faithful reproduction of Run B's package contents.
