# `md_index.py` — Implementation Notes (R1 + R3)

Companion to `README.md`. Covers: validation results against the acceptance bar, known
limitations / work explicitly deferred to R2 and R3, and what the follow-on Sonnet
session needs to rewrite Step 7.1 (R4).

---

## 1. Validation results (acceptance bar)

Run against the two real files the deleted prototype was validated on:

- `corpus/3gpp-ts33401-security-architecture-rel17.md`
  (real TS 33.401, 12,018 lines, 524,635 bytes, `--profile 3gpp`)
- `corpus/session-management.md`
  (53-line NIST SP 800-63B excerpt, `--profile generic`)

| # | Acceptance check | Expected (D14) | Produced | Verdict |
|---|---|---|---|---|
| 1 | ATX / Setext heading counts on TS 33.401 | 125 ATX + 124 Setext | **125 ATX**, **124 Setext-H2**, +73 Setext-H1, 1 TOC | **PASS** (principled diff, see below) |
| 2 | §7.2.9.2 (ATX L4 "KeNB re-keying") bound | `[3509,3577]` | `line:3509`, `section_bounds:[3510,3577]` | **PASS** (line/bounds separated) |
| 3 | Annex E.2.7 (Setext L2) bound — the key C2 regression | correct `[…,…]` = **14 lines**, NOT wrong 28 | `line:10091`, `section_bounds:[10093,10106]` = **14 lines** | **PASS** (the critical one) |
| 4 | E.2.7 body cites "clause 7.5" → resolves to §7.5 | resolves | `clause 7.5` → `target 7.5` → `h_0107` ("7.5 Signalling procedure for periodic local authentication"), `resolved:true` | **PASS** |
| 5 | NIST: §7.1.1 & §7.3 found; gap-topic query surfaces §7.2 via citation-following | yes | query returns §7.1.1, §7.3 (and §7.2 directly); both §7.1.1 and §7.3 carry resolved `cross_refs` → `h_0003` "7.2 Session Termination" | **PASS** |

### Detail on check #1 (the one principled difference)

D14's headline "125 ATX + 124 Setext" counts **only the Setext H2 underlines** (its
`sanity_check.py` counted "124 Setext H2 candidates"). My indexer reports **125 ATX +
124 Setext-H2 — an exact match on both** — and *additionally* surfaces **73 Setext H1**
headings (`Foreword`, `1 Scope`, `2 References`, `3 Definitions…`, etc.) plus the
`Contents` TOC heading, because they are genuine top-level headings the index must carry
to compute correct section bounds for everything beneath them. The review's own disk
audit corroborates this: it found "197 lines of pure `=`/`-` underline candidates" in the
file — and 197 = 124 H2 + 73 H1, exactly my Setext total. So the 322-heading total
(125 ATX + 197 Setext) is **not** an over-count; D14's "124" was an undercount of one
underline subclass. No bug — the difference is fully explained and is the *more* complete
answer.

### Detail on check #3 (the C2 proof)

This is the single most important regression. The old LLM-manual method produced
`[10085,10119]` (28 lines) for E.2.7; the deleted script produced the correct 14-line
bound; that script was then deleted, so the framework shipped the method that got it
**wrong**. This script reproduces the **correct 14-line** bound deterministically:
`section_bounds:[10093,10106]`, `10106−10093+1 = 14`. (D14 phrased it `[10092,10106]`
starting at the Setext underline; this schema starts one line later at the first body
line — same 14-line section, see README "Reconciliation with D14".)

### Cross-ref bonus correctness vs. D14

For §7.2.9.2, D14 reported the two Annex refs (A.3/A.4) as "unresolved and correctly
dropped." This indexer instead **resolves** `Annex A.3`, `Annex A.4`, and `clause A.5`
to real headings (`h_0164/h_0165/h_0166`) because those annex headings *do* exist in the
file and the `3gpp` profile's clause regex now parses annex-letter ids (`A.3`, `E.2.7`).
This is a correctness improvement over D14's prototype, not a regression — the refs are
genuinely resolvable, and unresolved refs are kept with `resolved:false` rather than
dropped, so nothing is silently lost.

### Edge-case smoke test (not in the two real files)

The two real files exercise *none* of the hard exclusions (TS 33.401 has zero code
fences, zero pipe-table separators, zero alignment-colon tables, zero YAML front matter;
its only front matter is the HTML-comment header, which **is** detected → `[1,10]`). A
throwaway fixture combining YAML front matter, a fenced code block containing
`# not a heading` / `---` / `|:--|--:|`, an alignment-colon table, an indented code
block, and a real Setext heading was indexed: **exactly the 3 real headings were found,
none of the code/table/front-matter lines leaked in.** This confirms the exclusion logic
works, but a *persisted* fixture suite is R2's job (below).

---

## 2. Known limitations / explicitly deferred

### R2 (fixture test suite — `scripts/tests/`) — DONE

`tests/test_md_index.py` (stdlib `unittest`, 22 tests, all passing) plus
`tests/fixtures/*.md` cover all six edge cases originally deferred here:

1. `mixed_atx_setext.md` — ATX subclauses under Setext top-level clauses + a `Contents`
   Setext H1, `is_toc`-flagged; cross-ref resolves across the style switch.
2. `front_matter_and_code_fences.md` — YAML `---` front matter; a fence containing `#`,
   `---`, `|---|---|`, none detected as structure.
3. `non_3gpp_numbering.md` — a trailing-period RFC heading (`5.2.2.  Title`) parses its
   clause id **only** under `rfc`; `generic`/`3gpp`/`ieee` correctly return `null`. A
   plain dotted-numeric heading parses under all four profiles.
4. `alignment_colon_tables.md` — `|:--|--:|` and a table-separator row immediately
   followed by a bare `---` never become headings.
5. `cross_refs.md` — in-file `clause X` / `Annex Y.Z` / `(see W)` plus a **dangling**
   ref to a non-existent clause (`clause 9.9`); resolved ones link, the dangling one is
   kept with `resolved:false` (this script keeps dangling refs visible rather than
   dropping them — the slight contract difference from D14's "drop" wording is
   documented in the README).
6. `deep_nesting.md` — `7.2.9.2.1.3`-depth ids parse and bounds don't collapse at depth.

Plus `golden_session_management.md` (verbatim copy of the real `session-management.md`)
as a full-snapshot golden regression input. The real TS 33.401 file is not vendored
(external 3GPP copyright, 524 KB); `mixed_atx_setext.md` captures the same structural
shape, and the full-file run against the real spec is recorded in §1 above.

### R3 follow-up (additional profiles) — DONE

`rfc.json` and `ieee.json` now ship alongside `generic`/`3gpp` (4 profiles total),
exercised by `non_3gpp_numbering.md`. `context-config.yaml.template`'s `what_l1` block
now documents `md_index_profile` and `index_path`. The profile loader (`load_profile`)
and schema were already final from R1/R3.

### Genuine limitations (by design, for v1)

- **Single-file, single-hop cross-ref resolution only.** Refs resolve against the same
  file's clause table; cross-FILE refs ("see TS 38.214 clause 5.2.2") are unresolved
  (`resolved:false`). This is R9 future work — the index already has every file's clause
  table, so corpus-wide resolution is a later lookup change, not a parser change.
- **Indented-code detection is a CommonMark approximation** (4-space indent preceded by a
  blank line). Pathological mixes of lazy-continuation paragraphs and 4-space indents
  could in theory mis-mask, but TS 33.401's headings are never indented so this is safe
  for spec-style inputs; R2 should add a fixture if a real corpus shows otherwise.
- **`query` ranks by raw match count** (term frequency), not TF-IDF or proximity. This is
  the same "OR-terms grep, ranked by hits" behaviour Step 7.1 has today — intentionally
  simple. The review's M5 notes ranking is "a scoring tweak, not an LLM-router research
  question"; tune later if needed.
- **No `.md` BOM stripping beyond UTF-8 decode.** Files are read as UTF-8 with
  `errors="replace"`; the validated files are clean UTF-8. (The em-dash in the NIST
  title is stored correctly as UTF-8 in the JSON; any `?`/box glyph seen when printing is
  a Windows console code-page artifact, not data corruption — verified at the byte level.)

---

## 3. What the R4 session needs (rewriting `ult-context-generate` Step 7.1)

Do **not** modify any existing file for R1/R3 — this deliverable is purely additive under
`scripts/`. R4 is where Step 7.1 changes. The contract to wire against:

1. **Build-once / stale-check.** Before querying, run:
   ```
   python scripts/md_index.py index <what_l1.path> -o specs-out/index.json \
       --profile <context-config: what_l1.md_index_profile, default generic> --stale-check
   ```
   `--stale-check` exits 0 and skips the rebuild when the index is current (newer than all
   inputs AND same profile), so this is cheap to call every run — like `graphify update`.
   One subprocess; **no source file content enters the agent's context** during indexing.

2. **Query per gap topic.** For each both-layers-gap topic:
   ```
   python scripts/md_index.py query specs-out/index.json "<topic> <2-4 curated synonyms>" --top 10
   ```
   The script returns a JSON array of `{file, clause_id, title, heading_id, line,
   section_bounds, match_count, cross_refs}`. The agent then `Read`s **only** each
   match's `section_bounds` line range from `file` — never the whole file. *This* is what
   makes the "0.5–2K tokens / topic" claim in the SKILL honest (resolves C1): the heavy
   heading-tree build and cross-ref resolution happen in the subprocess, not in-context.

3. **Citation-following (D14), now deterministic.** Each query result already carries its
   section's **resolved** `cross_refs`. For single-hop citation-following, the agent reads
   the `section_bounds` of each `resolved_heading_id` (look it up in `index.json` by `id`).
   Same semantics as today (single-hop, same-file, unresolved refs not chased) but no
   LLM "parsing in its head." On the NIST example this is exactly how §7.2 "Session
   Termination" is recovered from §7.1.1/§7.3 — both cite `7.2` and it resolves to
   `h_0003`.

4. **Downstream unchanged.** The `what-l1` `context_item` shape, `what_l1_fallback:true`,
   the "Found via citation-following from `<clause>`" summary note, and the Step 9 human
   gate are all unchanged.

5. **Config (R3 wiring, for the R4 session to add to `context-config.yaml.template`):**
   ```yaml
   what_l1:
     enabled: false
     path: specs/external/
     md_index_profile: generic   # generic | 3gpp | <your-profile>
   ```

6. **Honesty fix (C1).** When R4 edits the SKILL header / D13 / D14 callouts, replace
   "zero-LLM, zero-graphify" with "zero-LLM **extraction** (a stdlib subprocess builds the
   index; the agent only reads matched line-ranges)" — and drop any implication that the
   *agent-simulated* parser was ever zero-token.

### Generated-output note

`specs-out/ts33401.json` and `specs-out/session.json` are example indexes left in place
from validation. They are regenerable build artifacts (like `graphify-out/graph.json`),
not source — R4 may want `specs-out/` gitignored in real projects.
