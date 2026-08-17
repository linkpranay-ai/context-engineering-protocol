# Frequently Asked Questions

Short, direct answers to the questions that come up most once you've skimmed
[`CONCEPT.md`](CONCEPT.md) or [`PROTOCOL.md`](PROTOCOL.md) — not a replacement for either, just
a faster way to the specific thing you're wondering about. Every answer below links back to the
document that actually defines the behavior, so if you want the full picture, follow the link.

## Contents

**Getting started**
1. [What is CEP, in one sentence?](#1-what-is-cep-in-one-sentence)
2. [Who is CEP for?](#2-who-is-cep-for)
3. [Do I need to read both CONCEPT.md and PROTOCOL.md?](#3-do-i-need-to-read-both-conceptmd-and-protocolmd)
4. [How do I install CEP in my project?](#4-how-do-i-install-cep-in-my-project)
5. [Which AI coding agents does CEP work with?](#5-which-ai-coding-agents-does-cep-work-with)

**Concepts**
6. [What's the difference between a What layer and a How layer?](#6-whats-the-difference-between-a-what-layer-and-a-how-layer)
7. [Why isn't there a How-L3 tier?](#7-why-isnt-there-a-how-l3-tier)
8. [What are Constraints, and how are they different from How-L2?](#8-what-are-constraints-and-how-are-they-different-from-how-l2)
9. [What's a context package?](#9-whats-a-context-package)
10. [What's an addendum?](#10-whats-an-addendum)
11. [What's a trip-wire?](#11-whats-a-trip-wire)

**Using CEP day to day**
12. [What's the difference between Path A and Path B setup?](#12-whats-the-difference-between-path-a-and-path-b-setup)
13. [Do I have to run the full pipeline, or can I just compile guidelines?](#13-do-i-have-to-run-the-full-pipeline-or-can-i-just-compile-guidelines)
14. [How does CEP decide something is a gap vs. a conflict vs. stale?](#14-how-does-cep-decide-something-is-a-gap-vs-a-conflict-vs-stale)
15. [Does CEP block me, or just warn me?](#15-does-cep-block-me-or-just-warn-me)
16. [Who has to approve a context package, and can I skip that?](#16-who-has-to-approve-a-context-package-and-can-i-skip-that)

**Maturity & piloting status**
17. [What's implemented vs. still piloting?](#17-whats-implemented-vs-still-piloting)
18. [Is How-L1 safe to turn on?](#18-is-how-l1-safe-to-turn-on)
19. [How mature is Trip-wire?](#19-how-mature-is-trip-wire)

**Extending & customizing**
20. [Can I add, merge, or drop layers?](#20-can-i-add-merge-or-drop-layers)
21. [Can I bring an existing skill library under CEP without rewriting it?](#21-can-i-bring-an-existing-skill-library-under-cep-without-rewriting-it)
22. [How do I contribute a skill or a case study?](#22-how-do-i-contribute-a-skill-or-a-case-study)

**Evidence & limitations**
23. [What evidence is there that CEP actually helps?](#23-what-evidence-is-there-that-cep-actually-helps)
24. [Where does CEP add little or no value?](#24-where-does-cep-add-little-or-no-value)

---

## Getting started

### 1. What is CEP, in one sentence?

A protocol and reference skill set that assembles a **human-approved, source-attributed context
package** — code graph + requirements + org conventions + constraints — before an AI coding agent
generates anything, instead of letting it free-read the repo and guess. See
[`README.md`](README.md) for the full pitch and [`CONCEPT.md`](CONCEPT.md) for why this matters.

### 2. Who is CEP for?

Teams using an AI coding agent (Claude Code, GitHub Copilot, Cursor, or OpenAI Codex) on a
codebase where guessing is expensive — because requirements, org conventions, and existing code
need to agree before a change ships, and nothing today checks that automatically. It's also used
past code: the same gap/conflict/staleness mechanism can run an organization's own process
standards and QMS conventions in agentic mode (README's "Beyond code" note).

### 3. Do I need to read both CONCEPT.md and PROTOCOL.md?

Read [`CONCEPT.md`](CONCEPT.md) first — it's the conceptual model, written to be read before
anything else. [`PROTOCOL.md`](PROTOCOL.md) is the normative specification: the actual layer
table, state machine, and MUST/SHOULD rules an implementation is judged against. You need
CONCEPT.md to understand *why*; you need PROTOCOL.md to actually build or evaluate against CEP.

### 4. How do I install CEP in my project?

```sh
git clone https://github.com/linkpranay-ai/context-engineering-protocol.git
cd context-engineering-protocol
./install.sh --target /path/to/your/project --init-project   # or install.ps1 -TargetPath ... -InitProject
```

That copies `.github/skills/`, `.github/prompts/`, `.cursor/rules/`, and `AGENTS.md` into your
project and scaffolds a starter `context-config.yaml`. Re-running is safe — library files refresh,
project-owned files are left alone. See [README.md's Quickstart](README.md#quickstart) for the
full flag list and the two setup paths (Path A/B, [Q12](#12-whats-the-difference-between-path-a-and-path-b-setup)).
You can also drive setup through a browser instead of the CLI — see
[`ult-cep-wizard`](.github/skills/ult-cep-wizard/SKILL.md).

### 5. Which AI coding agents does CEP work with?

Claude Code (native `SKILL.md` files, or a one-click plugin install), GitHub Copilot
(`.prompt.md` wrappers), Cursor (`.cursor/rules/*.mdc`), and OpenAI Codex (root `AGENTS.md`).
All four are field-validated against a real cloned repository — see
[README.md's Runtime support](README.md#runtime-support) for what was actually run and confirmed
on each.

## Concepts

### 6. What's the difference between a What layer and a How layer?

**What** layers describe *what the product is and does* — What-L3 is the codebase itself (a
generated knowledge graph), What-L2 is this product's own requirements/spec documents, What-L1 is
external reference material (industry standards, competitor docs). **How** layers describe *how
work should be done* — How-L2 is your org's compiled, project-specific conventions, How-L1 is
org-wide external process standards (CMMI, ISO 9001, IEEE). The number is a maturity/scope tier,
not a ranking of importance. Full table: [PROTOCOL.md §2](PROTOCOL.md#2-the-layer-model).

### 7. Why isn't there a How-L3 tier?

CONCEPT.md's own three-tier framing (How-L1/L2/L3) suggests a How-L3 for "how similar work has
actually been performed in the system" — but the reference implementation deliberately doesn't
build one. The structural, pattern-level part of that question is already surfaced by What-L3's
own codegraph; workflow- and process-level conventions, if an organization wants them explicit,
belong under How-L2. Layer count and boundaries aren't fixed by the protocol — an organization may
add, merge, or drop tiers, including reintroducing a How-L3, to match its own complexity. See
[CONCEPT.md §4](CONCEPT.md#4-how-the-work-should-be-done) and
[PROTOCOL.md §2's "Why there's no How-L3" note](PROTOCOL.md#2-the-layer-model).

### 8. What are Constraints, and how are they different from How-L2?

Constraints (design decision D11) are a cross-cutting third dimension, not a layer — coding/design
conventions, compliance/regulatory requirements, and scheduling/dependency constraints, each
tagged `constraint_class: compliance | convention | scheduling`. They're read from the *same*
`COMPILED-GUIDELINES.md` cache How-L2 draws on, but for a different purpose: How-L2 answers "what
convention applies," Constraints answers "what bounds does this solution have to respect." Optional
infrastructure — absence isn't a gap. See [PROTOCOL.md §2.1](PROTOCOL.md#21-the-third-dimension-constraints-d11).

### 9. What's a context package?

"A structured, source-attributed package of context assembled for a bounded task and explicitly
approved by a human before downstream use" ([GLOSSARY.md](GLOSSARY.md)). It's built by
[`ult-context-generate`](.github/skills/ult-context-generate/SKILL.md), which runs gap → conflict
→ staleness checks before anything is generated, and is content-hashed with every claim traced
back to a file or section — never handed to a downstream skill without a human explicitly
approving it first ([PROTOCOL.md §3.4](PROTOCOL.md#34-the-human-approval-gate)).

### 10. What's an addendum?

"A consumer-written, append-only companion record that adds discovered context or decisions
without rewriting an approved package" ([GLOSSARY.md](GLOSSARY.md)). Once a package is approved,
its content doesn't get edited in place — new findings during actual work get written as a new
addendum instead, so the evolution of understanding stays traceable rather than silently
overwritten. Concrete schema: [CONSUMING-CONTEXT-PACKAGE.md's "Addendum file format"](.github/skills/ult-context-generate/CONSUMING-CONTEXT-PACKAGE.md).

### 11. What's a trip-wire?

A mechanism that watches for a task walking a road the organization has already rejected, and
surfaces that history to a human before the agent repeats the mistake — instead of silently
reinventing it. Implemented by
[`ult-institutional-memory-distill`](.github/skills/ult-institutional-memory-distill/SKILL.md),
which distills PRs/design docs/postmortems into a persistent decision ledger. Never auto-applied
or auto-suppressed — a hit is always shown to a human. See
[PROTOCOL.md §7](PROTOCOL.md#7-trip-wire--institutional-memory-decision-ledger-piloting).
Piloting — see [Q19](#19-how-mature-is-trip-wire).

## Using CEP day to day

### 12. What's the difference between Path A and Path B setup?

**Path A** (simple, 3 steps) — just compile scattered guideline sources into one
conflict-checked `COMPILED-GUIDELINES.md` for any AI agent to read. **Path B** (full pipeline, 9
steps) — code graph + requirements + constraints assembled into a full context package, then
handed to a downstream generation skill. Walkthrough for both:
[`user_guides/topics/project-setup-context-engineering.md`](user_guides/topics/project-setup-context-engineering.md).

### 13. Do I have to run the full pipeline, or can I just compile guidelines?

You can stop at Path A — running just
[`compiling-project-guidelines`](.github/skills/compiling-project-guidelines/SKILL.md) gives you a
single conflict-checked conventions file with no code graph or context-package machinery involved.
The full Path B pipeline is there for when a task needs code-graph grounding and human-approved
packaging, not a requirement for every use of CEP.

### 14. How does CEP decide something is a gap vs. a conflict vs. stale?

Three distinct checks, one blocking and two not: **gap detection** classifies, per requirement
aspect, whether coverage exists in code, in docs, or neither — a complete gap is surfaced to a
human rather than silently filled
([PROTOCOL.md §3.2](PROTOCOL.md#32-gap-detection--falls-through-layers-never-guesses)).
**Conflict detection** flags a genuine requirement-vs-code contradiction or an unresolved
Constraints conflict, and **blocks** approval until a human resolves it
([§3.1](PROTOCOL.md#31-conflict-detection--blocks)). **Staleness detection** flags that a derived
source (code graph, guidelines cache) may predate the current repo state — non-blocking, a nudge,
never silent ([§3.3](PROTOCOL.md#33-staleness-detection--non-blocking-but-never-silent)).

### 15. Does CEP block me, or just warn me?

Depends which check fires (see [Q14](#14-how-does-cep-decide-something-is-a-gap-vs-a-conflict-vs-stale)):
unresolved conflicts block approval outright; gaps are surfaced for a human decision rather than
silently filled; staleness only nudges. The one universal, non-configurable gate is human approval
itself — a package can't reach a downstream consumer without an explicit human sign-off, regardless
of how clean gap/conflict/staleness came back.

### 16. Who has to approve a context package, and can I skip that?

Any human reviewer explicitly confirming the package may be used as primary context by downstream
work — this is mandatory, not configurable away
([PROTOCOL.md §3.4](PROTOCOL.md#34-the-human-approval-gate), [§4](PROTOCOL.md#4-what-makes-this-a-protocol-not-a-tool)).
There's no flag or setting that bypasses it; that's the deliberate difference between CEP and a
fully autonomous pipeline.

## Maturity & piloting status

### 17. What's implemented vs. still piloting?

| Layer / mechanism | Status |
|---|---|
| What-L1/L2/L3 | Implemented |
| How-L2 | Implemented |
| How-L1 | **Piloting** — [Q18](#18-is-how-l1-safe-to-turn-on) |
| Trip-wire (`ult-institutional-memory-distill`) | **Piloting** — [Q19](#19-how-mature-is-trip-wire) |
| Runtime adapters (Claude Code, Copilot, Cursor, Codex) | Field-validated, all four |

Source of truth: [PROTOCOL.md §2's layer table](PROTOCOL.md#2-the-layer-model) and
[README.md's "What's not yet done"](README.md#whats-not-yet-done). Full prioritized detail:
[`ROADMAP.md`](ROADMAP.md).

### 18. Is How-L1 safe to turn on?

It's disabled by default (`context-config.yaml`'s `how_l1.enabled: false`) and gap-triggered —
it only fires once per package, when How-L2 comes up empty for a given task type, and every hit
lands in a `[HOW-L1 FALLBACK ITEMS — REVIEW]` block that's never auto-approved. It's real and
usable, but not yet field-validated against a real process-standard corpus — the case-study pilot
so far is disclosed, not a large-scale run. See
[PROTOCOL.md §5](PROTOCOL.md#5-how-l1--gap-triggered-task-type-scoped-piloting) and
[README's "What's not yet done"](README.md#whats-not-yet-done).

### 19. How mature is Trip-wire?

Implemented and exercised in a real retrofit case study,
[cep-retrofit-superpowers](case-studies/cep-retrofit-superpowers/CASE-STUDY.md), where it caught a
real, grep-verified regression the no-CEP baseline missed — but using a disclosed fixture decision
ledger, not a real, organically-grown one. Field-validating it against a real decision corpus is
the next headline item in [`ROADMAP.md`](ROADMAP.md).

## Extending & customizing

### 20. Can I add, merge, or drop layers?

Yes — the layer count and boundaries in [PROTOCOL.md §2](PROTOCOL.md#2-the-layer-model) are the
reference implementation's choice, not a protocol requirement. An organization may need two
layers, four layers, or a different hierarchy entirely; CONCEPT.md says this explicitly for both
the What and How dimensions, and the "no How-L3" decision ([Q7](#7-why-isnt-there-a-how-l3-tier))
is itself an example of that flexibility being exercised.

### 21. Can I bring an existing skill library under CEP without rewriting it?

Yes — that's what [`ult-cep-retrofit`](.github/skills/ult-cep-retrofit/SKILL.md) does: inventory,
classify, and insert an idempotent pointer to `CONSUMING-CONTEXT-PACKAGE.md` into each relevant
unit of a third-party library, without rewriting the library's own instructions. Validated
end-to-end against two real, unrelated skill libraries, `mattpocock/skills` and
[`obra/superpowers`](case-studies/cep-retrofit-superpowers/CASE-STUDY.md) — 0 misclassifications
across both (see [PROTOCOL.md §8](PROTOCOL.md#8-cep-retrofit--bringing-an-existing-skill-library-under-this-protocol)
for the full evidence claim and [case-studies/README.md](case-studies/README.md) for why only the
`superpowers` write-up is kept in this directory). In the wizard, this is the "Retrofit a Skill
Library" journey.

### 22. How do I contribute a skill or a case study?

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the general process. For a case study specifically,
[`case-studies/TEMPLATE.md`](case-studies/TEMPLATE.md) defines the format every case follows, and
[`case-studies/README.md`](case-studies/README.md) is the index it gets added to — including
deliberate negative controls where CEP added little or no value ([Q24](#24-where-does-cep-add-little-or-no-value)),
which are treated as first-class results, not omitted.

## Evidence & limitations

### 23. What evidence is there that CEP actually helps?

Tool-measured (not self-reported) token-reduction and citation/hallucination comparisons across
seven real-codebase case studies plus two retrofit cases — up to ~797x token reduction on an
external-spec clause lookup, and, on two independent generative comparisons, 8 vs. 0 and 18 vs. 0
real citations with zero hallucinations under CEP versus 2-3 hallucinations bare-ask. Full
breakdown and methodology: [`EVIDENCE.md`](EVIDENCE.md) (condensed) and
[README.md's "Measured impact"](README.md#measured-impact) (full).

### 24. Where does CEP add little or no value?

Disclosed directly rather than omitted: in the Textual case study's Run B (a deliberate negative
control), three tool outputs agreed there was nothing worth assembling context for, and a naive
read was actually cheaper (551 vs. 902 words) than running CEP. The pattern across all cases:
CEP's edge tracks how much of a task's answer lives in prose with no keyword to grep for — for
in-repo, keyword-findable code, its edge narrows to disambiguation and certainty rather than
discovery, and can reverse outright. See
[case-studies/SYNTHESIS.md](case-studies/SYNTHESIS.md) for the full analysis and limitations.
