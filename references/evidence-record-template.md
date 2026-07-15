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
    actually needs is still open; see the benchmark backlog.
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

## Fallback-relevance record

No template section exists here yet. `EVIDENCE-METHODOLOGY.md` §1 (surface 2)
and §4 name this as a measurement with no defined baseline — a record format
can't be usefully templated until that gap closes.
