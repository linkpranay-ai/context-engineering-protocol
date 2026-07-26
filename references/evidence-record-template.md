# Evidence Record Template

A structured way to record one measurement, per
[`EVIDENCE-METHODOLOGY.md`](../EVIDENCE-METHODOLOGY.md). Copy the relevant
section below, fill it in with a real run's output, and keep it alongside
wherever your project tracks findings (an issue, a `findings/` file, a report
back to the Guild — this repo does not prescribe a single storage location).

Every record must state whether it is **measured** or **self-reported**
(`EVIDENCE-METHODOLOGY.md` §5) — never leave that field blank or imply a
number is measured when it isn't.

## Token-efficiency record (`graphify benchmark`)

```yaml
kind: token-efficiency
tool: graphify benchmark
measurement_type: measured   # produced by actually running the tool
codebase:
  identity: <name>
  approximate_size: <e.g. "~40 KSLOC" or word/token count from the tool output>
  language(s): <e.g. Python, or "mixed">
date_run: <YYYY-MM-DD>
result:
  reduction: <e.g. "28.6x fewer tokens per query">
  graph_size: <nodes/edges from tool output>
  notes: <anything relevant — e.g. whether the corpus is representative
    per EVIDENCE-METHODOLOGY.md §3, or a small/self-referential run kept
    for illustration only>
```

**Worked example — a real run, not a hypothetical.** This repo's own
`.github/skills/` directory (17 Python scripts across its skill bundles) was
graphed and benchmarked on 2026-07-15 to produce this template's example:

```yaml
kind: token-efficiency
tool: graphify benchmark
measurement_type: measured
codebase:
  identity: context-engineering-oss, .github/skills/ subtree
  approximate_size: "32,750 words (~43,666 estimated naive tokens); 655 nodes, 1,001 edges"
  language(s): Python
date_run: 2026-07-15
result:
  reduction: "28.6x fewer tokens per query (avg ~1,527 tokens/query vs. ~43,666 naive)"
  graph_size: "655 nodes, 1,001 edges"
  notes: >
    Self-referential run against this repo's own scripts/ subtree, not an
    external pilot codebase. Per EVIDENCE-METHODOLOGY.md §3, this does not
    count as a representative-corpus finding (small scale, not the kind of
    target codebase CEP is built to be queried against) — it exists only to
    show this template populated with real tool output instead of an
    invented number. The representative-corpus benchmark this project
    actually needs has since been run for real against three external
    codebases (Open5GS, FastAPI, Textual, 2026-07-24) — see
    `EVIDENCE-METHODOLOGY.md` §2 and each case's own `CASE-STUDY.md`
    "Results at a glance" table in `case-studies/`.
```

## Context-package usage record (`usage_report.py`)

```yaml
kind: context-package-usage
tool: scripts/usage_report.py
measurement_type: measured   # aggregated from real contexts/*.yaml + addenda files
date_run: <YYYY-MM-DD>
result:
  total_context_items: <int>
  cited: <int>
  never_cited: <int, and % >
  token_data: <"Based on N measured run(s): min/max/avg" — OR — "No
    measured runs yet" if no addenda carried a real tokens_used value.
    Never substitute an estimate here.>
```

No packages exist in this repo's `contexts/` directory yet — see
[`reproducibility-guide.md`](reproducibility-guide.md) for the exact command
and its "no packages found" behavior. When a real run does produce a report,
fill this section from `USAGE_REPORT.md`'s actual output rather than from
this template's placeholder shape.

## Fallback-relevance record (naive-keyword-search baseline)

```yaml
kind: fallback-relevance
tool: naive keyword search (grep), compared against a CEP context package
measurement_type: measured   # naive search actually run; package citation actually checked
task: <one line, from the case's own §2>
naive_query: <the exact grep/keyword search a developer would try first>
date_run: <YYYY-MM-DD>
result:
  found_integration_point: <yes / no / partial — did the naive search's result
    set contain the specific site CEP's package cited?>
  naive_read_cost: <word count of what had to be read to get there, converted
    to tokens at the same ~4/3 tokens/word ratio graphify benchmark reports>
  cep_lookup_cost: <word/token count of the specific item CEP's package cited
    directly, for the same target>
  notes: <what the naive search found instead, and why it missed or hit>
limitation: >
  Retrospective, not blind — the naive query is being chosen after the task's
  real answer is already known, since true blindness isn't achievable after
  the fact (EVIDENCE-METHODOLOGY.md §7). Reused here from the case's own
  reproduction steps rather than reverse-engineered from CEP's citations.
```

**Worked example — a real run, not a hypothetical.** From the Open5GS+RFC 6733
case study (`case-studies/open5gs-ietf-rfc/CASE-STUDY.md`), the RFC-lookup half
of the task:

```yaml
kind: fallback-relevance
tool: naive keyword search (grep), compared against a CEP context package
measurement_type: measured
task: Add Error-Message AVP (RFC 6733 §7.3) support to the S6a interface.
naive_query: "read RFC 6733 end to end looking for the Error-Message AVP definition (no keyword hit is possible — the AVP name is not yet in any local file)"
date_run: 2026-07-24
result:
  found_integration_point: "partial — the RFC text exists locally (specs/external/rfc6733.md) but nothing short of reading through it locates §7.3; there is no in-codebase keyword to grep for"
  naive_read_cost: "43,599 words (~58,132 tokens) to read the whole RFC to find it"
  cep_lookup_cost: "55 words (~73 tokens) — What-L1's direct clause_id lookup returns exactly RFC 6733 §7.3's section_bounds, lines 5333-5339"
  notes: >
    ~797x fewer tokens for this specific lookup. This is the sharpest result
    across the three cases precisely because the target text is external to
    the codebase — grep cannot help at all, so the naive baseline is "read the
    whole external document," not "grep and miss." Contrast with the code-side
    half of the same case (Gx AVP exemplar), where a one-line grep finds the
    answer for free and CEP has no comparable edge — see the case's own
    "Results at a glance" table for the full, mixed picture across both halves.
limitation: >
  Retrospective — RFC 6733 §7.3 is cited by the case study's own reproduction
  steps as the target section, so this replays a known answer rather than a
  blind search. The naive_read_cost is real (the RFC file's real word count),
  not estimated.
```

## Consumer-output-quality record (bare-ask baseline)

```yaml
kind: consumer-output-quality
tool: <the downstream consuming skill actually run — not a CEP-native tool>
measurement_type: measured   # both modes actually run; citations actually grep-checked
task: <one line, the feature/ask given to the consuming skill>
context_package: <package id + content_hash used for the "with CEP" mode>
bare_ask: <the exact one-to-two-sentence wording used for the "without CEP" mode>
date_run: <YYYY-MM-DD>
result:
  real_citations: <count, with-CEP vs. without-CEP — grep-verified against the target codebase>
  hallucinated_apis_or_concepts: <count, with-CEP vs. without-CEP — confirmed absent via grep>
  distinct_actors_named: <count, with-CEP vs. without-CEP>
  nfr_criteria_with_number_and_unit: <count/total, with-CEP vs. without-CEP>
  required_sections_present: <count/total, with-CEP vs. without-CEP, if an org convention defines them>
  notes: <anything that complicates a clean win — a citation the with-CEP mode
    still missed, a placeholder number that passed the gate without being
    benchmarked, etc.>
limitation: >
  One consuming skill, one feature, one run per mode — see
  EVIDENCE-METHODOLOGY.md §7 for what this does not yet show.
```

**Worked example — a real run, not a hypothetical.** From
`case-studies/consumer-benefit-user-stories/CASE-STUDY.md`:

```yaml
kind: consumer-output-quality
tool: spw-write-user-story (ground-up consuming skill, vendored reference-only copy)
measurement_type: measured
task: Allow a disabled Button to remain in the keyboard focus chain instead of being skipped.
context_package: disabled-widget-focusable_feature-add_20260706@4ed6ad43
bare_ask: "Add support for disabled widgets to remain focusable. Users should be able to Tab to a disabled button so they know why it's disabled — add an opt-in setting for this."
date_run: 2026-07-25
result:
  real_citations: "8 (with CEP) vs. 0 (without CEP)"
  hallucinated_apis_or_concepts: "0 (with CEP) vs. 2 (without CEP) — an invented method (Button.set_focusable_when_disabled()) and an imported-but-inapplicable ARIA/live-region concept, both confirmed absent via grep"
  distinct_actors_named: "5 (with CEP) vs. 2, both generic (without CEP)"
  nfr_criteria_with_number_and_unit: "1/1 (with CEP, self-disclosed as an unvalidated placeholder) vs. 0/1 (without CEP)"
  required_sections_present: "7/7 per story (with CEP) vs. 0/7 (without CEP)"
  notes: >
    Even the with-CEP mode wasn't flawless: it missed a second, independent
    disabled-check call site (widget.py:2368's focusable property) that the
    approved context package's own context_items didn't cite — a real gap in
    that specific package's coverage, not in the consuming skill. Logged in
    the case's own §7/§10 rather than silently corrected after the fact.
limitation: >
  One consuming skill, one feature, one run per mode — see
  EVIDENCE-METHODOLOGY.md §7 for what this does not yet show.
```
