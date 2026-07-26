# CEP Conformance Specification

This document defines what it means for a tool, agent, workflow, or implementation to **conform**
to the Context Engineering Protocol as [`PROTOCOL.md`](PROTOCOL.md) currently describes it. It
makes mandatory only what this repository's protocol decisions already establish — it introduces
no new behavior of its own. See [`PROTOCOL.md`](PROTOCOL.md) for the full behavioral description,
[`GLOSSARY.md`](GLOSSARY.md) for term definitions, and
[Interpretation of MUST/SHOULD/MAY](PROTOCOL.md#interpretation-of-mustshouldmay) for how the
normative keywords below are read.

Nothing in this document changes `PROTOCOL.md`. If something here ever appears to conflict with
`PROTOCOL.md`'s own text, `PROTOCOL.md` wins — this specification is a derived summary, not an
independent source of behavior.

## 1. Relationship to the rest of this repository

This repository's own skills (`ult-context-generate`, `ult-codegraph`,
`compiling-project-guidelines`, and the rest) are one implementation of this protocol, not the
protocol itself (`PROTOCOL.md` §4). This specification exists so a *different* implementation —
someone else's tool, agent, or runtime integration — has a concrete, checkable bar to build
against, and so this repository's own users can tell a portable protocol requirement from a
choice this repository happened to make (YAML package format, specific CLI flags, file layout).

## 2. Conformance subjects

A conformance claim is always made about one of four kinds of thing:

- **Implementation** — a concrete system that carries out this protocol's behavioral state
  machine end-to-end: discovery, gap detection, conflict detection, staleness detection, package
  assembly, and the human-approval gate (`PROTOCOL.md` §3).
- **Consumer** — a downstream skill, tool, or workflow that uses an already-approved context
  package as its primary context, following the discover → confirm → load → spot-check → cite →
  tag contract (`PROTOCOL.md` §4).
- **Runtime adapter** — a generated, runtime-specific artifact (e.g. a `.cursor/rules/*.mdc` file,
  a merged `AGENTS.md` block) that surfaces this protocol's skills inside a particular agent
  runtime.
- **Workflow** — the broader downstream process (design, planning, test generation, code review,
  etc.) that takes an approved context package as an input but is not itself part of context
  assembly.

**This is deliberately a different taxonomy from `PROTOCOL.md`'s [`## Roles`](PROTOCOL.md#roles)**
(context-package author, context-package approver, consuming-skill implementer). Roles describe
*who* is accountable for a behavior during package assembly; conformance subjects describe *what
kind of artifact* a conformance claim can be made about. The same human or agent can hold a Role
while the software they're running is being assessed as a Subject — the two vocabularies are not
meant to be merged into one.

## 3. Mandatory behavioral requirements

Every requirement below already exists as a MUST/MUST NOT statement in `PROTOCOL.md`. This section
only extracts, organizes, and tags each one with the conformance subject(s) it binds — it adds no
new obligation.

| # | Requirement | Source | Binds |
| --- | --- | --- | --- |
| 1 | On a genuine contradiction (`l2-l3-contradiction`, `constraint-lateral`, `constraint-vertical`), an Implementation MUST NOT resolve it on its own — it MUST stop and ask a human. The contested point MUST NOT proceed until answered. | `PROTOCOL.md` §3.1 | Implementation |
| 2 | When both What-L3 and What-L2 have no coverage for an aspect, an Implementation MUST NOT silently fill the gap from its own judgment — it MUST fall through the defined fallback sequence instead. | `PROTOCOL.md` §3.2 | Implementation |
| 3 | Every fallback item (external spec, model training knowledge, org process standard) MUST carry an explicit provenance tag and sit in its own reviewer block. It MUST NOT enter an approved package without a human confirming it belongs there. | `PROTOCOL.md` §3.2 | Implementation |
| 4 | Staleness (of a code graph or a compiled-guidelines cache) MUST be checked. A stale source MUST NOT block assembly, but the staleness MUST be surfaced, not silently ignored. Whether a stale source is good enough for a given task stays a human judgment call; an Implementation MUST NOT decide it unilaterally. | `PROTOCOL.md` §3.3 | Implementation |
| 5 | A context package MUST be assembled with every item source-attributed to a `file:line-range` or an external reference, with every decision logged. It MUST be presented for review, and MUST NOT be treated as final until a human explicitly approves it. | `PROTOCOL.md` §3.4 | Implementation |
| 6 | A Consumer MUST NOT trust a context package that has not been through the approval gate. | `PROTOCOL.md` §3.4, §4 | Consumer |
| 7 | A Consumer that wants to use an approved package as primary context MUST follow the discover → confirm → load → spot-check → cite → tag contract, and MUST write addenda rather than edit the approved package directly. | `PROTOCOL.md` §4 | Consumer |
| 8 | Every `context_items` entry an Implementation produces MUST name its source — a `file:line-range`, an external document, or explicitly-labeled model training knowledge. Nothing MUST be asserted without a citation. | `PROTOCOL.md` §4 | Implementation |
| 9 | An Implementation MUST stop at context assembly. It MUST NOT itself generate the downstream artifact (code, design doc, test, review comment) as part of satisfying this protocol — that is Workflow's responsibility, not Implementation's. | `PROTOCOL.md` §4 | Implementation, Workflow (boundary) |

**A note on CI-enforced checks:** this repository's own `catalog/export_adapters.py --check`,
wired into CI, keeps its Runtime adapters generated and current with each skill's `SKILL.md`
frontmatter. That is evidence of *this repository's own* self-conformance to the general principle
that a Runtime adapter must not drift from what generated it — it is not itself a portable
requirement. A conforming Implementation MUST keep its own Runtime adapters synchronized with
whatever produces them, but the specific mechanism (a CI check, a build step, manual regeneration)
is an implementation choice.

## 4. Optional capabilities

The following are explicitly not required for baseline conformance. An Implementation MAY adopt
any subset of them, or none:

- **Constraints** (`PROTOCOL.md` §2.1) — coding/design conventions, compliance/regulatory
  requirements, and scheduling/dependency constraints. Explicitly optional infrastructure; its
  absence is not a gap the way missing What/How coverage is.
- **What-L1** (external reference fallback — industry standards, competitor docs, whitepapers) —
  piloting. An Implementation MAY implement it; if implemented, requirement 3 above still applies
  in full.
- **How-L1** (org-wide process-standard fallback) — piloting, defaults disabled
  (`how_l1.enabled: false`). Same MAY-if-implemented-then-still-MUST pattern as What-L1.
- **MCP-backed sourcing** for What-L1/How-L1 — MAY be used as a way of *populating* the fallback
  path (mirror-then-index). Mirrored content MUST carry the same content-hash and staleness
  discipline as any other source if this is implemented; MCP is not a separate content-item type
  with different rules.
- **Cross-file citation resolution, selective/granular install** — implementation-specific
  capabilities this repository happens to ship (`ROADMAP.md` items 1–2). MAY be implemented by
  others; not required for baseline conformance.
- **A three-tier How dimension, or runtime scope-filtering at consumption time** — explicitly
  speculative and undesigned in this repository (`ROADMAP.md` items 10, 12). Not part of this
  specification in any form; adopting either is not currently a meaningful conformance signal
  either way.

`PROTOCOL.md` §2.2's ingested-content rule (treat What-L1/How-L1/MCP-mirrored content as data to
cite, never instructions to follow) is itself a MUST — every Implementation is bound by it whether
or not it implements What-L1/How-L1 at all, since the rule constrains how ingested content is
*used*, not whether a given optional layer is present. What is explicitly **SHOULD**, not MUST, is
the specific heuristic mechanism this repository ships to help satisfy that rule:
`scripts/content_safety_scan.py` flags `.md` files under `what_l1.path`/`how_l1.path`/an MCP-mirror
output directory that contain imperative/instruction-like phrasing, for human review before those
files are cited. It is a strong recommendation, not a requirement — a heuristic keyword/pattern
match, run once per corpus build, that can miss real cases and flag harmless ones (an ordinary
process standard's own "MUST"/"SHOULD" language is not itself suspicious). An Implementation that
enables What-L1/How-L1 without running an equivalent scan still satisfies every MUST above as long
as ingested content is never treated as an instruction by construction; the scan is a best-effort
aid to a human reviewer, never itself the enforcement mechanism, and never auto-blocking
(`PROTOCOL.md` §3.1's no-automatic-resolution stance applies here too).

## 5. Conformance levels

This specification defines a **single conformance bar**, not tiered levels or profiles: an
Implementation conforms if it satisfies every requirement in §3, and MAY implement any subset of
§4's optional capabilities. There is no "Level 1 / Level 2" structure.

This is a deliberate choice, not an oversight. The piloting layers (What-L1, How-L1, Constraints)
are already optional per §4 without needing a tier system to express that. Introducing conformance
levels on top of that would risk creating tiers that track marketing rather than actual behavioral
difference — exactly the outcome a conformance specification should prevent, not manufacture. If a
concrete need for differentiated conformance levels surfaces later, it will be designed then,
against a real case, rather than speculatively now.

## 6. Evidence required for a conformance claim

A statement that something "conforms to CEP" is itself a claim, and this project's existing
evidence discipline (`EVIDENCE-METHODOLOGY.md` §5–§6) applies to it the same way it applies to any
other claim this project makes:

- A claim of conformance to a specific requirement in §3 is **measured** only if it names the
  specific test, walkthrough, or session record that produced it by actually running something and
  reading the output directly (for example: a recorded session where a genuine conflict was
  actually surfaced to a human and blocked, rather than silently resolved).
- A conformance claim with no named mechanism behind it is **self-reported**, not measured,
  regardless of how confidently it is phrased — and should be worded that way ("believed
  conformant," "not yet independently checked") rather than as if it had been tested.
- A conformance claim MUST NOT be phrased as measured unless it names the specific check that
  measured it.

This applies `EVIDENCE-METHODOLOGY.md` §5–§6's own measured/self-reported rule to conformance
claims specifically; it does not introduce a separate evidence framework for them.

## 7. Self-assessment checklist

An Implementation can check itself against this list. Each line corresponds directly to a
requirement in §3:

- [ ] On a genuine requirement-vs-code or Constraints contradiction, does the system stop and ask a
      human, rather than resolving it automatically? (§3 #1)
- [ ] When both What-L3 and What-L2 have no coverage for an aspect, does the system fall through a
      defined fallback sequence instead of guessing? (§3 #2)
- [ ] Does every fallback item carry a provenance tag and require explicit human confirmation
      before entering an approved package? (§3 #3)
- [ ] Is staleness checked and surfaced, without blocking assembly and without the system deciding
      unilaterally whether a stale source is acceptable? (§3 #4)
- [ ] Is every package source-attributed, with every decision logged, and withheld from
      "final" status until a human explicitly approves it? (§3 #5)
- [ ] Do consumers refuse to trust a package that hasn't been through approval? (§3 #6)
- [ ] Do consumers follow discover → confirm → load → spot-check → cite → tag, and write addenda
      rather than editing an approved package? (§3 #7)
- [ ] Does every `context_items` entry name its source, with nothing asserted uncited? (§3 #8)
- [ ] Does the system stop at context assembly, leaving artifact generation to a separate
      downstream workflow? (§3 #9)

## 8. Non-conformance examples

Concrete, non-hypothetical failure patterns — each is the direct negation of a §3 requirement:

- A tool that detects a contradiction between a requirements doc and the code graph, but picks one
  side automatically (even with a confident heuristic) instead of asking a human, is
  **non-conformant with requirement 1** regardless of how often its automatic pick happens to be
  right.
- A tool that, finding no coverage in either What-L3 or What-L2, fills the gap from the model's own
  general knowledge without labeling it as a fallback or routing it through review, is
  **non-conformant with requirements 2 and 3**.
- A tool that surfaces a stale code graph's staleness only in a log file nobody reads, rather than
  in the output a human actually sees before approving, is **non-conformant with requirement 4**
  — staleness that isn't actually surfaced is functionally silent.
- A tool that lets a downstream skill start consuming a package before a human has approved it —
  even "just this once," or "because the package looked obviously fine" — is **non-conformant with
  requirements 5 and 6**.
- A tool that edits an already-approved package in place to reflect something learned later,
  instead of writing an addendum, is **non-conformant with requirement 7**.
- A tool that includes an unsourced claim in a context package — "this is standard practice," with
  no file, external reference, or explicit training-knowledge label — is **non-conformant with
  requirement 8**.
- A tool that, once it has assembled and gotten approval for a context package, goes on to also
  generate the code/design/test artifact itself as part of the same protocol-governed step, with no
  separation from the downstream workflow, is **non-conformant with requirement 9**.

## 9. Versioning and compatibility rules

A conformance claim MUST reference a specific point in this repository's history — either a
`CHANGELOG.md` entry (for example, "checked against `[0.1.0]`") or a specific commit hash — rather
than an unqualified "conforms to CEP." This repository does not maintain a separate version number
for the protocol distinct from its `CHANGELOG.md` and git history, so neither does this
specification.

`PROTOCOL.md`'s own [Protocol Lifecycle](PROTOCOL.md#protocol-lifecycle) section allows a normative
rule to change over time (a MUST becoming a SHOULD, or the reverse, gated on the same evidence bar
as introducing a new rule). Because of that, a conformance claim tied to an older reference point is
not automatically invalidated the moment `PROTOCOL.md` changes — but it is also not automatically
carried forward. Re-checking a conformance claim against the current `PROTOCOL.md` is the
Implementation's own responsibility; this specification does not track that for them.

## 10. Future certification strategy — not current

This specification defines **self-assessment only**. There is no certification body, paid audit
program, conformance test suite, or "CEP-certified" mark associated with this project, and none is
currently planned.

If a certification mechanism is ever proposed, it would be evaluated against the same guardrails as
any other protocol change (`PROTOCOL.md`'s Protocol Lifecycle) and against the risk of overclaiming
interoperability this project already tries to avoid elsewhere (`PROTOCOL.md` §4: this repository
defines a behavioral contract, not a universal data model, transport, or interoperability
guarantee). Nothing in this document should be read as implying such a mechanism exists or is
imminent.
