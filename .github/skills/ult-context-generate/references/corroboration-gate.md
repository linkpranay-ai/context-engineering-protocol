# Step 4 — Corroboration Gate (D16)

Read this now, before recording `l3_coverage[aspect.aspect_id] = true` for any
aspect in Step 4.

**Corroboration before crediting coverage (D16 — required before recording
`l3_coverage[aspect.aspect_id] = true`):** a `graphify query` hit means the query's
BFS *reached* a node starting from one of the aspect's search terms — it does
not by itself mean that node's functionality matches the aspect. Generic
search terms routinely collide with unrelated symbols that merely contain the
term (e.g. an aspect about grouping constructs matching `PrintGroup()`/Unicode
character-class internals via "group"; an aspect about state/incremental
matching surfacing an unrelated `DFA::State` struct via "state"). Before
crediting **any** returned What-L3 node toward `l3_coverage[aspect.aspect_id] =
true`, confirm at least one of:

- (a) the node's own label/symbol name substantively matches one of the
  aspect's `search_terms` — not merely a generic word it happens to share with
  an unrelated symbol — or
- (b) a **deterministic lexical corroboration grep**, derived mechanically (no
  per-run judgment call) from `aspect.search_terms`:
  1. Drop any `search_terms` entry ≤4 characters — a cheap pre-filter for the
     very shortest terms only. Length alone does not guarantee specificity:
     "state" is 5 characters but is generic DFA/state-machine vocabulary
     pervasive throughout a matching-engine codebase (the same `DFA::State`
     collision as the example above) — step 4 below catches terms like this
     that survive the length filter.
  2. Regex-escape and OR-join the remaining terms into one pattern:
     `grep -rniE "<term1>|<term2>|..." <what_l3.path>`.
  3. If step 1 drops **every** term (the aspect is too generic for lexical
     corroboration), skip (b) entirely — the gate rests on (a) alone.
  4. The grep "passes" only if **both**: (i) it returns a real implementation
     hit — not just a comment/doc describing the construct's *absence*; and
     (ii) the matched hit's own construct substantively relates to the
     aspect, applying the **same** "not merely a generic word it happens to
     share with an unrelated symbol" test as (a). A term whose hits are
     spread across most of `what_l3.path` regardless of file/module (a
     "flood") is itself evidence of genericness — treat a flood as a failed
     (b), not a pass.

If neither (a) nor (b) holds — or (b) was skipped per step 3 and (a) fails —
the result was a keyword collision, not coverage evidence: set
`l3_coverage[aspect.aspect_id] = false`. Record the collision and the corroborating
grep result/pattern as a one-line note (useful context for Step 7.5/7.6 and the
audit trail) but do not add it as a `context_items` entry.

**False-negative risk (Step 9 escalation):** lexical corroboration can produce
a false *negative* if the codebase uses different vocabulary than
`search_terms` (e.g. code says "atomic" where the user said "possessive"). If
`l3_coverage[aspect.aspect_id]` was just set to `false` by this gate, but earlier
exploration (Step 4's own results, Step 4.5, or general familiarity with the
codebase) gives independent reason to suspect coverage exists under different
terminology, do **not** treat this as a normal gap — add a Step-9 note:
"corroboration failed for `<aspect.name>` but `<reason>` — please
double-check." This keeps the vocabulary-mismatch judgment call with the human
reviewer (Step 9), not buried in Step 4's mechanical gate.

Return to `SKILL.md` Step 4's "Record coverage" instruction once this gate has
been applied to every returned node.
