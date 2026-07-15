# Evidence Methodology

How this project evaluates its own claims, what it measures, what it hasn't measured yet, and
what would make a measurement misleading. Written for the same reason [`GLOSSARY.md`](GLOSSARY.md)
and [`PROTOCOL.md`](PROTOCOL.md) are: a maturity claim ("Piloting," "partly self-reported") should
be checkable against a defined method, not taken on trust.

This document describes methodology and definitions. It does not itself report new benchmark
results — see [`ROADMAP.md`](ROADMAP.md) and [`README.md`](README.md#whats-not-yet-done) for the
project's current, disclosed evidence state.

## 1. What this project evaluates

Three surfaces produce evaluable claims:

1. **Token efficiency** — whether querying the generated code graph (`ult-codegraph`) costs fewer
   tokens than a naive full-corpus read, for a given codebase.
2. **Fallback relevance** — whether What-L1/How-L1 fallback items surfaced to a human reviewer are
   actually relevant to the gap that triggered them, and whether the human-approval gate is doing
   real filtering work rather than rubber-stamping.
3. **Context-package usage** — whether the context items a package assembles are actually cited by
   the downstream artifacts that consume them, or sit unused (over-inclusion).

Only (3) currently has a real, running measurement mechanism (`scripts/usage_report.py`, ROADMAP
item 7). (1) has a defined tool and baseline but no recorded run (§2). (2) has no defined
measurement at all yet — flagged as a gap, not filled by this document (see §7).

## 2. Benchmark methodology

`graphify benchmark` (`.github/skills/ult-codegraph/SKILL.md`, "Measuring impact") is the one
benchmark tool that exists in this repo today. It measures token count for querying the generated
code graph against a target codebase, compared to a naive full-corpus-read baseline (§4), and
reports the reduction as a percentage.

Procedure:

1. Run `graphify update .` at least once on the target codebase (builds `graphify-out/graph.json`).
2. Run `graphify benchmark`. It is a one-off measurement, not part of the regular query loop — no
   need to re-run it routinely on the same codebase.
3. Record the result: codebase identity (name, approximate size, language), the reported
   percentage, and the date run.

**Current status: the tool exists and is documented; no run has been recorded in this repo yet.**
`README.md`'s "What's not yet done" and `ROADMAP.md` item 7 both disclose this plainly rather than
imply a number that hasn't been measured — this document does the same. The first real run against
a pilot codebase is future work, not something this document reports.

## 3. Representative-corpus selection criteria

Four demo corpora exist today under [`examples/`](examples/):

| Demo | Corpus | Representative? |
| --- | --- | --- |
| `cross-file-resolution-demo` | Hand-authored synthetic, 2-3 files | No — deliberately small, built to exercise the resolution mechanism, not corpus scale. |
| `how-l1-dogfood-demo` | Small synthetic corpus, `generic` profile | No — ROADMAP item 13 names this explicitly: no real/representative CMMI/ISO/IEEE-style corpus tested yet. |
| `mcp-what-l1-demo` | Real, executed run sequence (mirror → index → query → citation-following) | Partially — the *mechanism* was run for real, but the underlying source content is a demo fixture, not a production-scale MCP source. |
| `telecom-what-l1-demo` | Hand-authored synthetic 3GPP-style fixture | No — ROADMAP item 8 states real 3GPP spec text is gated/copyrighted and isn't freely redistributable into this Apache-2.0 repo. |

None of the four is a representative corpus in the sense this section defines. A corpus counts as
representative for a given claim when it is:

- **Domain-matched** — text of the same kind the claim is about (e.g. a real or realistically-
  licensed process-standard document for a How-L1 claim, not a hand-authored stand-in).
- **Scale-matched** — large enough that a token-efficiency or fallback-relevance result wouldn't
  trivially reverse on a bigger corpus (the current demos are all small by design).
- **Multiply-queried** — exercised with more than one task type or query, so a relevance result
  isn't a single lucky match. ROADMAP item 13 names this as an explicit current gap for How-L1: only
  one task type has been queried against the smoke-test corpus.
- **Licensable into this repo, or run externally and reported.** Real industry-standard text (CMMI,
  ISO, IEEE, 3GPP) is frequently gated/copyrighted. Where it can't be redistributed here, an
  operator can run the same procedure against a licensed corpus they hold, and contribute a
  sanitized writeup rather than the corpus itself — the same pattern
  `examples/telecom-what-l1-demo/`'s "Using your own real corpus" section already documents for
  What-L1.

## 4. Baseline definitions

- **Naive full-corpus read** (token efficiency, §2): reading every file in the target codebase as
  context, with no code-graph query scoping. This is the only baseline currently defined in this
  repo, used by `graphify benchmark`.
- **No baseline is currently defined for fallback relevance (§1, surface 2).** There is no
  reference ranking or human-agreement baseline to compare a How-L1/What-L1 result against — a
  gap this document names but does not fill (see §7, "No relevance baseline").

## 5. Measurement definitions

A number in this project's documentation is one of two kinds. Every future evidence record should
state which kind it is:

- **Measured** — produced by running code against real data and reading its output directly.
  Example: a citation count from `contexts/USAGE_REPORT.md` (`scripts/usage_report.py`), which
  scans real `contexts/<id>.yaml` and `<id>_*.addenda.yaml` files. A future `graphify benchmark`
  run, once recorded, is also measured.
- **Self-reported** — an estimate not backed by a harness run against real session data.
  `README.md`'s current token-cost claims are explicitly this kind ("partly self-reported... not
  yet independently measured against a real, large repo").

The `tokens_used` field added to the addenda schema (ROADMAP item 7) exists specifically to let
token-cost claims move from self-reported to measured, once operators start recording real per-run
values — `usage_report.py` reports "no measured runs yet" rather than fabricate a figure in the
meantime, and this document follows the same rule: it names no number that hasn't actually been
produced by running something.

## 6. Interpretation

Treat every claim in this repo's documentation as self-reported unless it names the specific tool
or script that measured it, per §5. A claim with no named measurement mechanism has not been
measured, regardless of how it is phrased.

## 7. Threats to validity

- **Synthetic-corpus bias.** Three of the four existing demos (§3) use hand-authored synthetic
  fixtures. A result that holds on a small synthetic corpus may not hold on a large, messy,
  real-world one — this is exactly why §3 defines representativeness as a separate, unmet bar
  rather than treating "a demo exists" as sufficient evidence.
- **Single-task-type testing.** ROADMAP item 13 names this directly for How-L1: only one task type
  has been queried against the smoke-test corpus, so relevance-ranking claims cannot yet be said to
  hold across task types.
- **No relevance baseline (§4).** Without a reference ranking or human-agreement baseline, a future
  fallback-relevance number would have nothing to be compared against — a result could look good in
  isolation while still being no better than chance. This methodology flags the gap; closing it
  (defining what a relevance baseline should look like) is future work, not resolved here.
- **Self-reported/measured conflation.** Before this document, no explicit rule distinguished a
  measured number from a self-reported estimate (§5) — a future contributor could unintentionally
  present an estimate as measured. The §5 rule is the mitigation.
- **Small sample size generally.** Every current evidence artifact in this repo (all four demos,
  the not-yet-run `graphify benchmark`, the not-yet-populated `USAGE_REPORT.md` at scale) reflects
  at most a handful of runs. None of the claims in this document or elsewhere in the repo should be
  read as statistically robust; they are disclosed pilot-stage findings, consistent with how
  `README.md` and `ROADMAP.md` already frame this project's maturity.

## See also

- [`ROADMAP.md`](ROADMAP.md) items 7, 8, and 13 — the source-of-truth status for each evidence gap
  named in this document.
- [`GLOSSARY.md`](GLOSSARY.md) — definitions for What-L1/L2/L3, How-L1/L2, and other terms used
  above.
- [`references/reproducibility-guide.md`](references/reproducibility-guide.md) — exact steps to
  rerun the measurements named in §2 and §5.
- [`references/evidence-record-template.md`](references/evidence-record-template.md) — a structured
  format for recording a measurement, populated with a real (small-scale, non-representative)
  `graphify benchmark` run as a worked example.
