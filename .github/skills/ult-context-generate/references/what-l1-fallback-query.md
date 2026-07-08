# Step 7.1 — What-L1 Fallback Query (gap-triggered, D2/D13/D14)

Read this in full when Step 7 hands you one or more both-layers-gap candidate
aspects. For each such aspect, attempt to close the gap — first with external
reference material (if configured), then with a disclosed training-knowledge offer
(step 5a, Q3) — before falling back to D8 (Step 7.2).

**If there are no both-layers-gap candidate aspects:** nothing to do here — Step 7.2
will also have nothing to do.

**If `context-config.yaml` has `what_l1.enabled: false` (or the `what_l1` block is
absent):** there is no external corpus to query. For each candidate aspect, skip
steps 1–5 below and go directly to **step 5a**, as if step 5 had returned no results
for that aspect.

**Otherwise (`what_l1.enabled: true`):**

1. **Build (or refresh) the structural index — once per run, not per aspect.**
   Run:
   ```
   python scripts/md_index.py index <what_l1.path> -o <what_l1.index_path> --profile <what_l1.md_index_profile> --stale-check
   ```
   using the configured (or default) values: `what_l1.path` = `specs/external/`,
   `what_l1.index_path` = `specs-out/index.json`, `what_l1.md_index_profile` =
   `generic`. `--stale-check` exits immediately without rewriting if the index
   is already current (same profile, no input file under `what_l1.path` newer
   than the index) — cheap to call every run, the same build-once contract
   `graphify update` uses for the code graph. **No `.md` file content enters
   the agent's context during this step** — it's a single subprocess call.

   **If the build/refresh fails** (e.g. `what_l1.path` doesn't exist or
   contains no `.md` files): treat as "What-L1 returns nothing" for every
   both-layers-gap candidate aspect this run — for each, go directly to step
   5a below.

2. **Query the index, once per candidate aspect.** For each both-layers-gap
   candidate aspect, run:
   ```
   python scripts/md_index.py query <what_l1.index_path> "<aspect.search_terms + 2-4 curated synonyms>" --top 10
   ```
   Curate 2-4 domain synonyms per aspect — terminology in external specs may
   differ from the gap aspect's own wording (e.g. for "session inactivity
   timeout", also try "re-keying", "periodic (local) authentication",
   "refresh", "expir*"). The query is an OR-of-terms match over each section's
   content and title, ranked by match count — the same intent this step has
   always had, now executed by the indexer instead of agent-simulated.

   For runs with many both-layers-gap candidate aspects, `query-batch` (R18)
   can run all of these per-aspect queries in one subprocess instead of
   one-per-aspect — see `scripts/README.md` "query-batch". This per-aspect
   `query` invocation remains the default; `query-batch` is an optional
   convenience, not a documented token-reduction.

   The result is a JSON array of `{file, clause_id, title, heading_id, line,
   section_bounds, match_count, cross_refs}` entries, already ranked, with
   TOC-flagged headings excluded.

3. **Read the matched sections — and only the matched sections.** For each
   result returned (up to `what_l1.graphify_budget` line-ranges total for this
   aspect), `Read` lines `section_bounds[0]`–`section_bounds[1]` of `file`
   (resolved relative to `what_l1.path`). `section_bounds` is already the exact
   content range for that heading, computed by the indexer — never read the
   whole file.

4. **Citation-following (D14, single-hop, deterministic).** Each result's
   `cross_refs` are already resolved by the indexer. For each cross-ref with
   `resolved: true` whose `resolved_heading_id` is **not** one of this aspect's
   step-2 matched headings: look up that `heading_id` in the same file's
   `headings` array in `<what_l1.index_path>`, and `Read` its `section_bounds`
   too. Record it as an additional context item (below), noting in its summary
   `Found via citation-following from <source clause id or heading title>.`
   Cross-refs with `resolved: false` are dropped — do not guess or read an
   unrelated section. Citation-following is single-hop only — do not chase
   `cross_refs` belonging to a citation-followed heading's own entry.

5. **If the query returns no results for an aspect** (or the index
   build/refresh failed in step 1): record a `gaps_detected` entry with
   `layers_checked: [what-l2, what-l3, what-l1]` and
   `what_l1_fallback_used: false` — then go to **step 5a** for this aspect.

5a. **Disclosed external-knowledge offer — optional web fallback (D18) first,
    then Q3 training-knowledge (one at a time, same pattern as Step 7.6).**
    For this aspect:

    **Web fallback (D18, opt-in via `what_l1.allow_web_fallback: true`).** If
    `allow_web_fallback` is `false` or absent (the default): skip straight to
    the Q3 offer below — a silent, transparent fall-through, not an error. If
    `true`: attempt ONE scoped lookup — a single `WebSearch`/`WebFetch` for
    `<aspect.name> specification` (or `standard`, whichever phrasing fits the
    domain). If it errors or returns nothing usable, also fall through to Q3
    below unchanged.

    If the lookup returns something usable, offer it:

    > "No What-L2/L3/L1 coverage found for **<aspect.name>**. A web search
    > (retrieved <ISO timestamp>) found this[, from <source name/URL> if
    > identifiable]:
    > `<2-4 sentence summary>`.
    > This is unverified against this project's own conventions or
    > implementation — please confirm it's relevant before I add it.
    > Add to context? (y) Yes / (n) No / (e) Edit first"

    **If yes or edit:** add a context item (see schema in `references/context-package-schema.md`):
    ```yaml
    - id: ctx_<NNN>
      layer: what-l1
      source: "web_search(<query>) retrieved_at: <ISO timestamp>"
      type: domain-spec
      confidence: SUGGESTED
      aspect_id: <aspect.aspect_id>
      aspect: <aspect.name>
      summary: >
        <the web result content, including the unverified-against-project
        caveat from the prompt above>
      what_l1_fallback: true
    ```
    Increment `web_fallback_count`. Update this aspect's `gaps_detected`
    entry: `what_l1_fallback_used: false`, `web_fallback_used: true`,
    `llm_knowledge_used: false`. **This aspect is no longer a complete gap —
    do not pass it to Step 7.2, and skip the Q3 offer below.**

    **If no, or the web fallback was skipped/disabled/declined/empty:**
    continue to the Q3 offer — an item drawn from the model's own training
    knowledge:

    > "No external reference found for **<aspect.name>**. From my training
    > knowledge (cutoff: <model's knowledge-cutoff date>), here's what I know
    > about this[, from <spec/standard name> if identifiable]:
    > `<2-4 sentence summary>`.
    > This reflects training data only — it is not verified against current
    > spec text, and anything published or amended after <cutoff date> would
    > be missing.
    > Add to context? (y) Yes / (n) No / (e) Edit first"

    **If yes or edit:** add a context item (see schema in `references/context-package-schema.md`):
    ```yaml
    - id: ctx_<NNN>
      layer: what-l1
      source: "llm_training_knowledge (<spec/standard name if identifiable, else 'general domain knowledge'>)"
      type: domain-spec
      confidence: SUGGESTED
      knowledge_cutoff: <model knowledge-cutoff date, e.g. 2025-08>
      aspect_id: <aspect.aspect_id>
      aspect: <aspect.name>
      summary: >
        <the training-knowledge content, including the unverified-against-current-spec
        caveat from the prompt above>
      what_l1_fallback: true
    ```
    Increment `llm_knowledge_count`. Update this aspect's `gaps_detected`
    entry: `what_l1_fallback_used: false`, `llm_knowledge_used: true`. **This
    aspect is no longer a complete gap — do not pass it to Step 7.2.**

    **If no:** leave the `gaps_detected` entry from step 5 as-is
    (`llm_knowledge_used: false`, `web_fallback_used: false`) — this aspect
    passes to Step 7.2.

**Zero-LLM extraction, not zero-cost — see D13/D14.** Heading detection,
clause-id parsing, section-bounds computation, and cross-reference resolution
all happen inside the `md_index.py` subprocess (stdlib Python, no LLM call) —
the agent never reads raw `.md` content to *find* structure. The agent's token
cost is the index build (once per run, amortized via `--stale-check`) plus
exactly the `section_bounds` line-ranges it `Read`s — proportional to what's
relevant, not to the size of the corpus under `what_l1.path`.

For each section read in steps 3 and 4, record a context item:
```yaml
- id: ctx_<NNN>
  layer: what-l1
  source: "<file path> (<clause_id or title>)"
  type: domain-spec
  confidence: EXTRACTED
  aspect_id: <aspect.aspect_id>
  aspect: <aspect.name>
  summary: >
    <the external guidance, faithfully paraphrased — note that product
    applicability has not been confirmed>. <If found via step 4: "Found via
    citation-following from <source clause id or heading title>.">
  what_l1_fallback: true
```

Increment `what_l1_fallback_count` once per context item, including
citation-followed ones. Record in `gaps_detected`:
`layers_checked: [what-l2, what-l3, what-l1]`, `what_l1_fallback_used: true`,
`llm_knowledge_used: false`, with a note on what L2/L3 lacked, what the L1
item(s) suggest, and whether any were found via citation-following. **This
aspect is no longer a complete gap — do not pass it to Step 7.2.**

When done with all candidate aspects, return to `SKILL.md` Step 7.2.
