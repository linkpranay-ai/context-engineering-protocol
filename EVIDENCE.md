# Evidence

Real, tool-measured runs against real codebases — not marketing narratives. This page is a
headline-first, shareable entry point; the full tables, methodology, and disclosed limitations live
in [`README.md#measured-impact`](README.md#measured-impact),
[`EVIDENCE-METHODOLOGY.md`](EVIDENCE-METHODOLOGY.md), and
[`case-studies/SYNTHESIS.md`](case-studies/SYNTHESIS.md) — this page condenses those, it doesn't
duplicate them as a second source of truth. If a number here and a number there ever disagree, the
README and `SYNTHESIS.md` are authoritative.

## The headline finding

An ungrounded AI coding assistant invented the same hallucinated concept twice, in two completely
unrelated codebases — a UI framework and a telecom protocol stack — while the CEP-grounded run
produced 26 real, checkable citations and zero inventions across both.

| | consumer-benefit-user-stories (UI framework) | open5gs-gy-supported-features (telecom) | Combined |
|---|---|---|---|
| Real citations, with CEP vs. bare ask | 8 vs. 0 | 18 vs. 0 | **26 vs. 0** |
| Hallucinated concepts, with CEP vs. bare ask | 0 vs. 2 (an invented method + an imported web-accessibility concept with no counterpart in the codebase) | 0 vs. 1 (the *same* concept, imported again into a codebase with no UI at all) | **0 vs. 2 distinct fabrications, 3 total instances** — the same one recurs identically across both unrelated domains |
| Org-convention structure | Full vs. none | Full (7/7) vs. none (0/7) | — |

**Why this number leads, not the token-reduction numbers below:** the token-reduction figures are a
cost argument — real, but the kind that mainly lands with a token-optimization audience. The
hallucination-recurrence finding is a trust argument: the same fabricated concept resurfacing,
unprompted, in a domain where it has no plausible reason to appear, is a concrete story worth
retelling in one sentence, not a percentage to take on faith.

## Retrieval cost: finding the right integration point

| Case | Codebase | Task-level token reduction | `graphify benchmark` reduction |
|---|---|---|---|
| [open5gs-s6a-error-message-avp](case-studies/open5gs-ietf-rfc/CASE-STUDY.md) | `open5gs/open5gs` (C) | ~797x | 36.8x |
| [fastapi-response-links-parity](case-studies/fastapi/CASE-STUDY.md) | `fastapi/fastapi` (Python) | ~15.3x | 5.6x |
| [textual-focus-chain-and-sparkline-baseline](case-studies/textual/CASE-STUDY.md) | `Textualize/textual` (Python) | ~17.6x (Run B, negative control: naive read was cheaper) | 39.6x |

**Measured**, per `EVIDENCE-METHODOLOGY.md` §5 — naive-full-corpus-read and naive-keyword-search
baselines, applied retrospectively (see limitations in `SYNTHESIS.md`).

## Generation quality: does the output improve, not just cost less?

| Case | Domain | Real citations: CEP vs. bare ask | Hallucinations: CEP vs. bare ask | Org-convention structure |
|---|---|---|---|---|
| [consumer-benefit-user-stories](case-studies/consumer-benefit-user-stories/CASE-STUDY.md) | UI framework | 8 vs. 0 | 0 vs. 2 | Full vs. none |
| [open5gs-gy-supported-features](case-studies/open5gs-gy-supported-features/CASE-STUDY.md) | Telecom protocol stack | 18 vs. 0 | 0 vs. 1 (same fabricated concept as above) | Full (7/7) vs. none (0/7) |
| [ripgrep-trim-user-stories](case-studies/ripgrep-user-stories/CASE-STUDY.md) | Rust CLI (ripgrep) | 9/9 vs. 0 | 0 vs. 0 — see case §9, this run's headline is citation/actor grounding, not hallucination-suppression | N/A — skipped by design |

**Measured**, per `EVIDENCE-METHODOLOGY.md` §5 — same consuming skill, same feature, run twice (with
an approved context package vs. a bare ask). The first two rows share one vendored consuming skill
(`spw-write-user-story`); the third uses an independently-designed, ground-up one
(`demo-write-user-stories`), also repeated on a fourth, RobotFramework case not shown in this table
because it doesn't share these three columns' exact shape — see
[`README.md#measured-impact`](README.md#measured-impact) for that case and two more (a retrofit-based
generative comparison and a tooling-only side-quest).

## What this doesn't yet show

Ten case studies total; the direct bare-ask-vs-CEP generation-quality axis above has been run four
times across two independently-designed consuming skills and four domains (UI framework, telecom,
Rust CLI, RobotFramework/large-repo) — still no blind trials, no live human reviewer. Full disclosure
of every limitation: [`case-studies/SYNTHESIS.md`](case-studies/SYNTHESIS.md) and
[`EVIDENCE-METHODOLOGY.md`](EVIDENCE-METHODOLOGY.md) §7.
