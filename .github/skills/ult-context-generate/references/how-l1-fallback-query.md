# Step 2.1 — How-L1 Fallback Query (gap-triggered, task-type-scoped, D13/D14)

Read this in full when Step 2's How-L2 org convention check finds no relevant content under
`org/` (or the configured `how_l2.path`) for this task type — the same "D8 gap" branch Step 2
already has. This step runs **once per package, not once per aspect** — How-L1 answers "what does
this organization's process require of this task type," not a per-aspect question.

**If there are no gaps** (How-L2 covered the task type): nothing to do here — proceed with Step 2
as normal.

**If `context-config.yaml` has `how_l1.enabled: false` (or the `how_l1` block is absent):** there
is no external corpus to query. Skip straight to Step 2's existing D8 branch — (a) LLM-suggested
best-practice template, or (b) user-provided template — as if step 4 below had returned no
results.

**Otherwise (`how_l1.enabled: true`):**

0. **Mirror configured MCP sources (only if `how_l1.mcp_source` is set and non-empty) — once per
   run, before the index build below.** Same mechanism as What-L1's Step 7.1 step 0. If
   `how_l1.mcp_source` is absent or an empty list (the default), skip this step entirely and go
   straight to step 1 — How-L1 behaves exactly as it does today, reading only hand-dropped `.md`
   files under `how_l1.path`.

   Otherwise, for each entry in `how_l1.mcp_source` (`id`, `server`, `tool`, `identifier`,
   `mirror_filename`):
   1. Call the entry's MCP tool (`<entry.server>`'s `<entry.tool>`) with `<entry.identifier>`,
      exactly like any other in-session MCP tool call.
   2. Write the fetched text to a scratchpad JSON file shaped `{"body": "<fetched text>"}`.
   3. If the tool call errors or returns nothing usable: skip mirroring this one entry (note it),
      and continue with the rest — do not fail this step. `md_index.py` will index whatever mirror
      files already exist from a prior successful run for that entry (or none, if this is the
      first run and it failed) — same as if the entry weren't configured this run.

   Once every entry has been attempted, build one combined spec file — a JSON array, each entry
   shaped `{"id", "source": {"server", "tool", "identifier"}, "mirror_filename", "content_file"}`,
   with `content_file` pointing at that entry's scratchpad JSON from step 2 above — and run:
   ```
   python scripts/mcp_mirror.py mirror --spec-file <scratchpad spec file> \
       --mirror-dir <how_l1.mcp_mirror_path> --manifest <how_l1.mcp_manifest_path>
   ```
   One subprocess call mirrors/hashes/manifests every entry. `how_l1.mcp_mirror_path` is a
   subdirectory of `how_l1.path` (default `<how_l1.path>/.mcp-mirror/`), so step 1's index build
   below picks up mirrored files automatically — `md_index.py` indexes `how_l1.path` recursively,
   no command change needed. Content is only rewritten (and only then does its mtime advance) when
   its `content_hash8` differs from the last run's recorded hash for that entry — this treats a
   frequently-revised internal org QMS source and an infrequently-revised external standards body
   identically (the mirror simply rewrites more or less often); no separate staleness/attribution
   treatment is needed for the two kinds of source. See `scripts/README.md`'s `mcp_mirror.py`
   section and `examples/mcp-what-l1-demo/WALKTHROUGH.md` for the mechanism and a validated round
   trip (What-L1 example; How-L1 uses the identical mechanism against `how_l1.path`).

1. **Build (or refresh) the structural index — once per run.**
   Run:
   ```
   python scripts/md_index.py index <how_l1.path> -o <how_l1.index_path> --profile <how_l1.md_index_profile> --stale-check
   ```
   using the configured (or default) values: `how_l1.path` = `org/process-standards/`,
   `how_l1.index_path` = `specs-out/how_l1_index.json`, `how_l1.md_index_profile` = `generic`.
   `--stale-check` exits immediately without rewriting if the index is already current — same
   build-once contract as What-L1's Step 7.1 and `graphify update`. **No `.md` file content enters
   the agent's context during this step** — it's a single subprocess call.

   **If the build/refresh fails** (e.g. `how_l1.path` doesn't exist or contains no `.md` files):
   treat as "How-L1 returns nothing" — go directly to Step 2's existing D8 branch.

2. **Query the index, once for this task type.** Run:
   ```
   python scripts/md_index.py query <how_l1.index_path> "<task_type + 2-4 curated process synonyms>" --top 10
   ```
   Curate 2-4 process-terminology synonyms for the task type — a CMMI/ISO/IEEE document's
   vocabulary for "code review" may be "peer review" or "verification," for "design doc" may be
   "design description" or "architecture record". The query is an OR-of-terms match over each
   section's content and title, ranked by match count, same as What-L1's Step 7.1 step 2.

   The result is a JSON array of `{file, clause_id, title, heading_id, line, section_bounds,
   match_count, cross_refs}` entries, already ranked, with TOC-flagged headings excluded.

3. **Read the matched sections — and only the matched sections.** For each result returned (up to
   `how_l1.graphify_budget` line-ranges total), `Read` lines `section_bounds[0]`–`section_bounds[1]`
   of `file` (resolved relative to `how_l1.path`). `section_bounds` is already the exact content
   range for that heading, computed by the indexer — never read the whole file.

4. **Citation-following (D14, single-hop, deterministic).** Each result's `cross_refs` are already
   resolved by the indexer. For each cross-ref with `resolved: true` whose `resolved_heading_id`
   is **not** one of this query's step-2 matched headings: look up that `heading_id` in the same
   file's `headings` array in `<how_l1.index_path>`, and `Read` its `section_bounds` too. Record it
   as an additional context item (below), noting in its summary `Found via citation-following from
   <source clause id or heading title>.` Cross-refs with `resolved: false` are dropped — do not
   guess or read an unrelated section. Citation-following is single-hop only — do not chase
   `cross_refs` belonging to a citation-followed heading's own entry.

5. **If the query returns no results** (or the index build/refresh failed in step 1): set
   `how_l1_covered: false` and go directly to Step 2's existing D8 branch — no separate
   web-search or training-knowledge offer here. Step 2's D8 prompt (LLM-suggested template vs.
   user-provided template) already gives the human an equivalent decision point; a second fallback
   chain in front of it would be redundant, not a faithful mirror of What-L1's design intent.

**If the query returns one or more results:** for each section read in steps 3 and 4, record a
context item:
```yaml
- id: ctx_<NNN>
  layer: how-l1
  source: "<file path> (<clause_id or title>)"
  type: process-standard
  confidence: EXTRACTED
  summary: >
    <the process-standard guidance, faithfully paraphrased — note that org-QMS applicability
    has not been confirmed>. <If found via step 4: "Found via citation-following from <source
    clause id or heading title>.">
  how_l1_fallback: true
```
Note this item has no `aspect_id`/`aspect` — How-L1 is task-type-scoped, not aspect-scoped (see
`references/context-package-schema.md`'s `how-l1` example).

Increment `how_l1_fallback_count` once per context item, including citation-followed ones. Set
`how_l1_covered: true`. **Do not pass this task type to Step 2's D8 branch — How-L1 coverage
found is treated as an informative, human-reviewable candidate for the gap, gated at Step 9's
`[HOW-L1 FALLBACK ITEMS — REVIEW]` block, same as What-L1 items are gated for the What dimension.**

**Zero-LLM extraction, not zero-cost — see D13/D14.** Heading detection, clause-id parsing,
section-bounds computation, and cross-reference resolution all happen inside the `md_index.py`
subprocess (stdlib Python, no LLM call) — the agent never reads raw `.md` content to *find*
structure. The agent's token cost is the index build (once per run, amortized via `--stale-check`)
plus exactly the `section_bounds` line-ranges it `Read`s — proportional to what's relevant, not to
the size of the corpus under `how_l1.path`.

When done, return to `SKILL.md` Step 2.
