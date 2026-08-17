# Evidence Methodology

How this project evaluates its own claims, what it measures, what it hasn't measured yet, and
what would make a measurement misleading. Written for the same reason [`GLOSSARY.md`](GLOSSARY.md)
and [`PROTOCOL.md`](PROTOCOL.md) are: a maturity claim ("Piloting," "partly self-reported") should
be checkable against a defined method, not taken on trust.

This document describes methodology and definitions. It does not itself report new benchmark
results — see [`ROADMAP.md`](ROADMAP.md) and [`README.md`](README.md#whats-not-yet-done) for the
project's current, disclosed evidence state.

## 1. What this project evaluates

Four surfaces produce evaluable claims:

1. **Token efficiency** — whether querying the generated code graph (`ult-codegraph`) costs fewer
   tokens than a naive full-corpus read, for a given codebase.
2. **Fallback relevance** — whether What-L1/How-L1 fallback items surfaced to a human reviewer are
   actually relevant to the gap that triggered them, and whether the human-approval gate is doing
   real filtering work rather than rubber-stamping.
3. **Context-package usage** — whether the context items a package assembles are actually cited by
   the downstream artifacts that consume them, or sit unused (over-inclusion).
4. **Consumer-output-quality** — whether an approved context package makes a downstream *consuming
   skill's generated output* more grounded (traceable to real code, free of invented APIs/behavior)
   than the same skill working from a bare ask alone. Distinct from (1)/(2): those measure retrieval
   cost/precision; this measures the quality of what a generative downstream task produces once it
   has (or lacks) that retrieval's output to work from.

(3) has a real, running measurement mechanism (`scripts/usage_report.py`, ROADMAP item 7). (1) now
has real recorded runs against three real corpora (§2) — no longer an unfilled gap, though still
only three data points. (2) now has a defined baseline (§4) and a first retrospective application
across the same three corpora — a real start, but not yet a general-purpose measurement mechanism
(see §7 for what's still limited about it). (4) now has four real runs
(`case-studies/consumer-benefit-user-stories/CASE-STUDY.md`, 2026-07-25, and three more since —
`open5gs-gy-supported-features`, `ripgrep-trim-user-stories`, `robotframework-wizard-ui`) across two
independently-designed consuming skills and four domains — more than the single-case start it began
as, but still not yet a blind trial or a general-purpose measurement mechanism (see §7 for what
remains limited about it).

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

**Current status: run for real, for the first time, against the three dogfood
corpora** (2026-07-24): Open5GS (`src/`+`lib/diameter/`, 3,830 nodes / 10,236 edges) — 36.8x
reduction, 191,500 words → ~255,333 naive tokens, ~6,934 tokens/query average; FastAPI (`fastapi/`,
911 nodes / 2,568 edges) — 5.6x reduction, 45,550 words → ~60,733 naive tokens, ~10,925
tokens/query average; Textual (`src/`, 20,116 nodes / 59,448 edges) — 39.6x reduction, 1,005,800
words → ~1,341,066 naive tokens, ~33,877 tokens/query average. Full per-question breakdowns and the
naive-keyword-search comparison (§4) are recorded in each case's own `CASE-STUDY.md` "Results at a
glance" table. This closes the gap for these three corpora specifically — the four synthetic demos
in §3 still have no recorded run, and three real-repo data points is not yet a claim about
`graphify benchmark`'s behavior in general.

**Common misreading:** the reported multiplier (e.g. "39.6x") is an *average* across a small set of
queries per corpus (5-8 questions each), not a per-query guarantee. A single expensive query — one
that genuinely needs broad context — can sit well below the average while the aggregate still looks
strong; the average hides that one catastrophic-for-that-query case rather than ruling it out. Read
the number as "typical across the queries actually run," not "every query gets this reduction."

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
  context, with no code-graph query scoping. Used by `graphify benchmark`.
- **Naive keyword search** (fallback relevance / correctness, §1 surface 2): given only the task's
  own wording, the plausible grep/read a developer would try first — no context package, no
  `graphify query`/`affected`, no `md_index.py` lookup. Measured as: (a) whether the search's
  result set contains the specific integration point CEP's package actually cited (yes / no /
  partial, with how many extra files a developer would have had to read to disambiguate), and
  (b) the word count of what had to be read to get there, converted to tokens at the same
  ≈4/3 tokens-per-word ratio `graphify benchmark` itself already reports in its own output (§2).
  First applied retrospectively across the three case studies (2026-07-24) — see each
  case's "Results at a glance" table. This is a real baseline with real numbers, but see §7 for its
  disclosed limitation (retrospective, not blind) and its current single-round-of-cases scope.
  **Common misreading:** a "yes" on (a) — naive search technically found the right file — is not
  the same as naive search being usable. The real cost hides in (b): a "yes, found it" result that
  also required reading through several extra files to disambiguate which match was correct still
  cost real time and attention. High precision on (a) alone can make naive search look like it
  worked fine when the disambiguation count says otherwise — read (a) and (b) together, never (a)
  in isolation.
- **Bare ask** (consumer-output-quality, §1 surface 4): given only the task's own one-to-two-sentence
  wording, the terse ticket a developer would actually start from — no context package, no actor
  list, no constraints, no `[Context: ...]` tagging requirement — run through the same consuming
  skill that would otherwise read an approved context package. Measured as: (a) how many of the
  skill's own citations are real (checkable via grep against the target codebase) vs. invented, (b)
  how many distinct, feature-relevant actors are named vs. generic filler, (c) whether NFR
  acceptance criteria carry a number+unit, and (d) whether the output matches the project's own
  `required_sections` convention or falls back to a generic shape. First applied for real in
  `case-studies/consumer-benefit-user-stories/CASE-STUDY.md` (2026-07-25), then three more times
  since across a second consuming skill and three more domains — see §1 item 4 and §7 for the
  fuller picture and what these four applications still don't show.
  **Common misreading:** a fluent, confident-sounding bare-ask output is not evidence of grounding —
  fluency and correctness are independent. A well-organized answer that cites plausible-looking but
  invented APIs is the exact failure mode this baseline exists to catch, not a sign the comparison
  was easy or the baseline was "basically fine." Judge grounding by (a) — real vs. invented citations,
  checked by grepping the target codebase — never by how polished or complete the prose reads.

## 5. Measurement definitions

A number or outcome in this project's documentation is one of three kinds. Every future evidence
record should state which kind it is:

- **Measured** — produced by running code against real data and reading its output directly.
  Example: a citation count from `contexts/USAGE_REPORT.md` (`scripts/usage_report.py`), which
  scans real `contexts/<id>.yaml` and `<id>_*.addenda.yaml` files. A future `graphify benchmark`
  run, once recorded, is also measured.
  **Common misreading:** "measured" is read as "statistically significant" or "representative of
  the general case." It isn't — it only means the number came from running something real, not
  that ten cases (§7) generalize to every codebase. A measured number can still be a small sample.
- **Self-reported** — an estimate not backed by a harness run against real session data.
  `README.md`'s current token-cost claims are explicitly this kind ("partly self-reported... not
  yet independently measured against a real, large repo").
  **Common misreading:** "self-reported" is read as "unreliable" or "made up," on the assumption
  that anything short of a harness run is marketing. It isn't a hidden estimate — it's a labeled
  one, disclosed as such precisely so it isn't mistaken for the stronger claim.
- **Inference** — a qualitative judgment call, not a number at all — e.g. whether a package
  "helped" a downstream task, made without a controlled comparison against a no-CEP baseline. This
  is the category `case-studies/TEMPLATE.md` §8 asks case studies to distinguish from a measured
  outcome (an artifact you can point to). Inference is not a weaker form of self-reported; it's a
  different kind of claim (judgment, not estimate) and should be labeled as such, not folded into
  either of the two above.
  **Common misreading:** the opposite direction — inference claims are the ones most likely to get
  *read* as measured, because they're usually phrased as a firm conclusion ("CEP helped here") with
  no numeric hedge attached to signal otherwise. The absence of a number is not the absence of a
  judgment call; check for a named controlled comparison before treating an inference as a result.

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
- **Consumer-output-quality has been run four times, across two consuming skills, still not
  blind.** The first application of this surface (§1 item 4, §4's bare-ask baseline) used a single
  vendored consuming skill (`spw-write-user-story`, not a CEP-native tool) against a single
  feature, and showed a real, measured citation/hallucination gap. Three more runs have since
  followed: a second use of that same vendored skill on an unrelated domain
  (`open5gs-gy-supported-features`), and two runs of a brand-new, independently-designed consuming
  skill (`demo-write-user-stories`) built specifically to check whether the finding depended on
  the first skill's own construction (`ripgrep-trim-user-stories`, `robotframework-wizard-ui`).
  The citation and actor-specificity gap held across all four; the hallucination gap did not — the
  `demo-write-user-stories` runs found 0 vs. 0 hallucinations, because that bare ask had too little
  surface to invent from, not because grounding stopped mattering (see
  `case-studies/ripgrep-user-stories/CASE-STUDY.md` §9). This is a broader base than the original
  single-case start, but every run is still one round, self-approved or reused, and not blind — it
  does not yet show whether the finding holds for a task type or bare-ask phrasing meaningfully
  different from what's been tried so far.
- **Relevance baseline is real but retrospective, not blind (§4).** The naive-keyword-search
  baseline now defined and applied across the three cases reuses grep queries drawn
  from each case's own reproduction steps — a genuine first-attempt search a developer would try,
  but reconstructed after the task's answer was already known, since true blindness isn't
  achievable after the fact. Each case study states this plainly rather than presenting the
  comparison as a controlled trial. It is also currently three data points from one round of
  dogfooding, not a repeatable measurement mechanism a future case can just plug into without
  re-deriving its own naive query by hand.
- **Self-reported/measured conflation.** Before this document, no explicit rule distinguished a
  measured number from a self-reported estimate (§5) — a future contributor could unintentionally
  present an estimate as measured. The §5 rule is the mitigation.
- **Small sample size generally.** Every current evidence artifact in this repo (all four demos,
  the not-yet-run `graphify benchmark`, the not-yet-populated `USAGE_REPORT.md` at scale) reflects
  at most a handful of runs. None of the claims in this document or elsewhere in the repo should be
  read as statistically robust; they are disclosed pilot-stage findings, consistent with how
  `README.md` and `ROADMAP.md` already frame this project's maturity.
- **Field-name drift in historical case studies.** The three real dogfood runs (§2, §4) recorded
  under `case-studies/` were captured before the context-package schema renamed its approval field
  from `human_approved: true|false` to `approved_by: [{actor, at}]`. Those case studies, and their
  vendored fixture YAMLs, still show the old boolean field verbatim, as an accurate record of what
  each run actually produced at the time — they are not out of date or in error, and are left
  unedited on purpose (rewriting historical evidence to match a later schema would misrepresent what
  the run actually output). Read `human_approved: true` in a case study as equivalent to today's
  `approved_by` holding one entry.

## See also

- [`ROADMAP.md`](ROADMAP.md) items 7, 8, and 13 — the source-of-truth status for each evidence gap
  named in this document.
- [`GLOSSARY.md`](GLOSSARY.md) — definitions for What-L1/L2/L3, How-L1/L2, and other terms used
  above.
- [`references/reproducibility-guide.md`](references/reproducibility-guide.md) — exact steps to
  rerun the measurements named in §2 and §5.
- [`references/evidence-record-template.md`](references/evidence-record-template.md) — a structured
  format for recording a measurement, populated with a real (small-scale, non-representative)
  `graphify benchmark` run and a real naive-keyword-search fallback-relevance run as worked
  examples.
- [`CONFORMANCE.md`](CONFORMANCE.md) — how to check whether an implementation actually conforms to
  the protocol these measurements are evaluating.
