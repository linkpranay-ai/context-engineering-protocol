# Case Study: open5gs-gy-supported-features

```yaml
case: open5gs-gy-supported-features
codebase: open5gs/open5gs, AGPL-3.0, ~250k LOC C (5G/EPC core network functions) — pinned
  tag v2.8.0, commit 157f611a530e292e40ec50f9d23f0ef5d4fcd6a6
date_run: 2026-07-26
author: dogfooding run, context-engineering-oss
negative_control: false
```

This is the second case in the consumer-output-quality family, alongside
[`../consumer-benefit-user-stories/CASE-STUDY.md`](../consumer-benefit-user-stories/CASE-STUDY.md).
That case measured the effect on a UI framework (Textual, Python). This case
repeats the same two-track method on a different domain entirely — a telecom
Diameter protocol stack (Open5GS, C) — to check whether the finding holds
outside UI/accessibility features, where the risk of a consuming skill
inventing plausible-sounding-but-wrong domain concepts is arguably higher,
not lower, given how unfamiliar 3GPP/Diameter conventions are to a
general-purpose model.

The consuming skill is the same vendored, reference-only
`spw-write-user-story` copy used in the first case
([`../consumer-benefit-user-stories/vendored-skill/`](../consumer-benefit-user-stories/vendored-skill/))
— not duplicated here; both cases share that one vendored copy. As before,
this is reference-only: not installed under `.github/skills/`, not part of
this repo's skill set, per `ROADMAP.md`'s "Not on this roadmap" stance.

**Feature selected:** add a `Supported-Features` AVP to the Gy interface
(SMF↔OCS online/offline charging), the one Diameter interface in this
codebase that has feature-negotiation entirely absent, while Cx, Gx, Rx, and
S6a already implement it. This is a real, reasonably small, realistic gap in
a real telecom library — not a synthetic exercise. Per this repo's AGPL-3.0
no-vendoring rule (already established in
[`../open5gs-ietf-rfc/CASE-STUDY.md`](../open5gs-ietf-rfc/CASE-STUDY.md)), no
Open5GS source and no generated context package is committed to this repo;
every citation below is independently reproducible against the pinned clone
(see Reproduction steps).

## Results at a glance

| Metric | Without CEP (bare ask) | With CEP (approved package) | Kind |
| --- | --- | --- | --- |
| Distinct real file/line citations | 0 | 18, across 9 files | Measured |
| Hallucinated/fabricated mechanism | 1 ("ARIA live region or similar accessible-label mechanism" — invented for a headless C Diameter stack with no UI at all) | 0 | Measured |
| Distinct, feature-relevant actors | 2 (generic "System"/"OCS administrator") | 5 (SMF operator/network engineer, OCS/billing integrator, Open5GS maintainer/reviewer, roaming/interconnect partner operator, regression test suite as system actor) | Measured |
| NFR acceptance criteria with number+unit | 0 of 1 ("fast enough not to slow down charging requests") | 1 of 1 (1% p95 latency regression at 10,000 concurrent sessions) — but see note below | Measured |
| Org-convention `required_sections` present per story | 0 of 7 | 7 of 7, every story/Enabler | Measured |
| `[Context: ...]`/provenance tagging present | None | Every story tagged package id + `content_hash` | Measured |
| Enabler cross-reference (`[Enabler: ...]` tags matching a real dependency) | 0 of 2 Enablers referenced by any story | 2 of 2, every dependent story tagged | Measured |

The NFR row needs the same caveat the first case flagged: Mode 1's number
(1%, 10,000 sessions) is self-disclosed inside its own output as an
unvalidated placeholder, not a benchmarked figure — it passes the *form*
check (does the criterion carry a number+unit?) without passing the
*provenance* check (was that number ever measured?). See §8 and §10.

## 1. Environment

Pinned clone: `open5gs/open5gs`, tag `v2.8.0`, commit
`157f611a530e292e40ec50f9d23f0ef5d4fcd6a6`, at `dogfood-open5gs/` (sibling to
the `open5gs-ietf-rfc` case's own clone; same repo, same pin). `graphify` CLI
installed and its graph confirmed current for this clone (3,830 nodes, 10,236
edges). `python .github/skills/ult-context-generate/scripts/content_hash.py`
run directly (no live agent session for hashing — a deterministic script).
The consuming skill (`spw-write-user-story`, vendored copy) was run twice,
directly, no live interactive agent session beyond the two generation runs
themselves — same "no live human reviewer" disclosure the other cases in
this directory carry.

## 2. Task

Identical feature description across both tracks, so the only variable is
what the generating skill has to work from:

> Add `Supported-Features` AVP support to the Gy interface so the SMF can
> negotiate optional feature support with the OCS, like we already do on Gx.

## 3. Source set

**Track 2 (with CEP) only** — Track 1 has no source set by construction (see
§4). What-L1/How-L1 population for this run: direct `grep`/`Read` inspection
of `lib/diameter/gy/`, `lib/diameter/gx/`, `lib/diameter/s6a/`,
`src/smf/gy-path.c`, `src/smf/gy-handler.c`, `src/smf/gx-path.c`,
`src/smf/gsm-sm.c`, `src/hss/hss-s6a-path.c`, cross-checked with two
`graphify explain` calls (`smf_gy_send_ccr()`, `smf_gy_handle_cca_initial_request()`)
against the pinned clone's real call graph — not a `discover`/
`confirm-layers` run against a configured `context-config.yaml`, since this
dogfood clone's context-package generation for this case was done as a
direct, hand-built package rather than through the full automated pipeline
(same shortcut the sibling S6a case in `open5gs-ietf-rfc` took, for the same
reason: proving the package-consumption benefit doesn't require re-proving
the generation pipeline, already covered by the other cases in this
directory).

## 4. Package generation / bare-ask baseline definition

**Track 2 (with CEP):** a new context package was generated for this
feature — `contexts/gy-supported-features_feature-add_20260726.yaml`,
`content_hash: 8b9327e0`, `human_approved: true` — containing 6 aspects
(a1-a6: dictionary registration, message-layer resolve chain, AVP-fill
construction, call-site gating, cross-interface pattern precedent, and
non-regression scope) and 12 `context_items`, each with a real file/line
citation (enumerated in full in §1's Environment note and in the Reproduction
steps below). `gaps_detected` records 2 open items, carried forward
faithfully into the generated stories rather than silently resolved: the
correct `Feature-List` bitmask value for Gy's own feature set (Gx's/S6a's
`0x0000000b` is cited as the known-working *shape*, not asserted as the
correct *value*), and the absence of any existing performance baseline for
`smf_gy_send_ccr()`. `conflicts_detected` is empty. This package deliberately
does **not** reuse the S6a case's package almost-verbatim, despite the
structural similarity of the task (both add `Supported-Features` to an
interface that lacks it) — Gy's own aspects/gaps were re-derived from Gy's
own real code, not copied from S6a's package, because Gy's correct pattern
(Gx's single-block shape) is a different pattern than S6a's (dual-block),
and conflating them would have been exactly the mistake this feature needs
to avoid. Full generated output:
[`mode-1-with-cep-output.md`](mode-1-with-cep-output.md).

Reused, disclosed substitution, not silent assumption: no
`org-conventions/user-story.yaml` exists in `dogfood-open5gs`; this run
reuses the same `tmp-graphify-cpp-smoke/re2/org-conventions/user-story.yaml`
convention the first case study also substituted in, for the same reason (a
structurally generic, previously-approved convention, not a domain-specific
one improvised for this run).

**Track 1 (without CEP) — this case's bare-ask baseline, the
consumer-output-quality analogue of `EVIDENCE-METHODOLOGY.md` §4's
naive-keyword-search baseline:** same skill, same feature description quoted
in §2 above, with the skill's Step 1 context-package and org-convention
lookups both returning no match (by construction — no context package or
convention file was made available for this run at all). No source-set
inspection, no `graphify` calls, no file reads were performed for this
track — that absence is the point: it is what a developer relying only on a
short ticket, with no context-engineering step, actually starts from. Full
generated output: [`mode-2-without-cep-output.md`](mode-2-without-cep-output.md).

## 5. Detected gaps, conflicts, staleness

Reported by the Track 2 package's own `gaps_detected`/`conflicts_detected`
fields (§4 above), not re-derived here: 2 gaps (the `Feature-List` bitmask
value; no performance baseline), 0 conflicts. Both gaps propagate visibly
into the Track 2 output — ENB-002/US-002's disclosed "Validation caution" and
NFR-001's disclosed placeholder — rather than being silently resolved or
dropped. Track 1 has no equivalent check to run; its own generated NFR-001
("fast enough") is not a disclosed gap, it is simply unspecific, with no
mechanism in that track to flag it as an open question rather than a filled-
in answer.

## 6. Rubric

Same six dimensions as the first case study, fixed before reading either
output to avoid post-hoc bias:

- **Traceability** — does the story cite real functions/files/lines that
  exist in the pinned clone (checkable via `grep`/`graphify explain`)?
- **Hallucination** — does it invent APIs, AVPs, or mechanisms that don't
  exist, or that exist but mean something different (e.g. confusing
  `Supported-Features` with `OC-Supported-Features`)?
- **Actor coverage** — distinct, feature-relevant actors named vs. generic
  filler.
- **NFR specificity** — acceptance criteria with a number+unit vs. vague
  terms (the same gate `spw-write-user-story` Step 4 self-checks for).
- **Testability** — could an engineer write a test straight from the
  acceptance criteria without first inventing something?
- **Convention adherence** — does the output match the org convention's
  `required_sections`, or invent its own shape?

## 7. Scoring

**Traceability — Measured.** Track 2 cites 18 distinct real file/line
locations across 9 files, every one independently confirmed against the
pinned clone in this run: `lib/diameter/gy/dict.c:159,185,196,216`;
`lib/diameter/gx/dict.c:206,257`; `lib/diameter/gx/message.h:58`;
`lib/diameter/gx/message.c:35,109`; `src/smf/gy-path.c:635`;
`src/smf/gx-path.c:323-353`; `src/smf/gsm-sm.c:116,156,562`;
`src/smf/gy-handler.c:124,175`; `src/hss/hss-s6a-path.c:1307-1381,1382-1452`.
Track 1 cites zero real locations — it names no file, line, or struct
anywhere, consistent with having no source set to draw from (§3).

**Hallucination — Measured.** Track 1's US-003 introduces "an ARIA live
region or similar accessible-label mechanism" to explain graceful
degradation on a headless C Diameter signaling stack that has no UI, no
accessibility tree, and no concept of ARIA anywhere in the codebase (grep
confirms zero matches for `aria` anywhere under `lib/`, `src/`) — an
imported, domain-inappropriate concept, not a paraphrase of anything real.
This is a stronger version of the same failure mode the first case study
found in Textual (where ARIA was at least topically plausible for a UI
framework); here it is imported into a domain where it has no meaning at
all, which is itself a finding: an ungrounded generation doesn't just guess
wrong within the right domain, it can import a concept from an entirely
unrelated domain with no signal to the reader that anything was invented.
Track 2 makes zero such invention — it explicitly identifies and rejects the
one plausible domain-internal confusion available (`OC-Supported-Features`
vs. `Supported-Features`, cited at `gy/dict.c:185,216`) rather than
conflating the two, and explicitly declines to assert Gx's/S6a's
`0x0000000b` literal as Gy's correct value, flagging it as unresolved
instead of guessing.

**Actor coverage — Measured.** Track 2: 5 distinct actors (SMF operator/
network engineer, OCS/billing-system integrator, Open5GS maintainer/code
reviewer, roaming/interconnect partner network operator, regression test
suite as a system actor), each tied to a specific story and grounded in a
real stakeholder relationship this interface actually has (an SMF that
signals to an OCS across an operator/partner boundary). Track 1: 2 generic
actors ("System"/"OCS administrator"), with no partner-operator or
maintainer-reviewer perspective at all — nothing in the bare ask itself
would surface either without a context package's actor-relevant aspects
(a5/a6 in this case) to drive the skill's actor-decomposition step.

**NFR specificity — Measured, caveat.** Track 2's NFR-001 carries a
number+unit (1% p95 latency regression at 10,000 concurrent sessions) and
passes the gate mechanically — but its own text discloses that number as
self-authored, not benchmarked, since the context package itself records
"no performance baseline" as an open gap rather than fabricating one. Track
1's NFR-001 ("fast enough not to slow down charging requests") carries no
number or unit at all and fails the gate outright, with nothing to fall back
on. Net: Track 2 is more specific in form and honest about its own
non-authoritative substance; Track 1 is neither specific nor honest about
the gap, because it has no mechanism to disclose one.

**Testability — Measured.** Track 2: all 6 story/NFR acceptance-criteria
sets map directly onto a concrete existing test pattern or a clearly-scoped
new one (US-005 explicitly proposes the new test cases needed, naming the
exact functions — `smf_gy_send_ccr()`, `smf_gy_handle_cca_initial_request()`,
`smf_gy_handle_cca_update_request()` — to assert against). Track 1: of 4
acceptance-criteria sets, US-003's routes through the fabricated ARIA
mechanism (untestable without first inventing the very thing being tested),
and US-002's ("visible/loggable on the OCS side") names no mechanism to
assert against at all; only US-001's and NFR-001's are testable, and only
vaguely so.

**Convention adherence — Measured.** Track 2: all 7 of the org convention's
`required_sections` present in every story and Enabler (Story statement,
Scope and non-scope, Acceptance criteria, Non-functional criteria,
Observability and failure semantics, Blast-radius and non-regression checks,
Dependencies and rollout notes) — 0 omissions across 7 stories/Enablers.
Track 1: 0 of 7 present in any story — output falls back to an unstructured
"As a/I want/So that" plus a bare acceptance-criteria list, since no
convention was available to follow; Observability, Blast-radius, and
Dependencies sections are entirely absent from every story, not thinly
covered.

## 8. Downstream compounding benefit

This is the specific angle this case was asked to highlight, not just the
Track 1 vs. Track 2 comparison above: the value of the context package does
not stop at the user-story file. Per
[`vendored-skill/CONSUMING-USER-STORY-OUTPUT.md`](../consumer-benefit-user-stories/vendored-skill/CONSUMING-USER-STORY-OUTPUT.md)'s
Detect/Extract/Apply/Announce contract, any later stage of work that picks up
Track 2's output finds, and can act on, its
`[Context: gy-supported-features_feature-add_20260726@8b9327e0 · ctx_NNN · aspect aN]`
tags — the "Extract" step explicitly requires resolving every distinct
`<package-id>@<hash8>` found back to the underlying context package's own
decisions, gaps, and evidence, meaning that same package becomes available,
pre-identified and pre-hashed, to whatever work happens next — without
re-deriving it from scratch. Concretely, across the stages that contract
describes:

- At a **design/review stage**, any new design can be cross-checked against
  the story file's own scope and actor list — it would immediately surface
  US-004's roaming/interconnect-partner scope constraint and ENB-001/ENB-002's
  explicit non-scope (no `OC-Supported-Features` implementation) and flag a
  design that drifted from either, rather than silently re-deciding scope a
  second time.
- At a **planning stage**, every acceptance criterion can be traced to a
  concrete task — NFR-001's disclosed "Inference, not benchmarked" placeholder
  and US-002's open `Feature-List` bitmask question can be routed forward as
  explicit, flagged planning items (e.g. "confirm bitmask value with
  stakeholder before implementation begins") instead of a task silently
  picking its own value.
- At a **test-writing stage**, acceptance criteria already phrased as
  Given/When/Then-shaped assertions become the test assertions directly —
  US-005's criteria (assert presence on CCR-Initial/Update, absence on
  CCR-Termination, no behavior change on the CCA receive path) are a direct
  test-assertion set, not a paraphrase target.
- At an **implementation stage**, each story's acceptance criteria become
  that piece of work's definition of done — an implementation task for
  ENB-002, for instance, isn't complete until US-001's CCR-Initial/
  CCR-Termination criteria are demonstrably true, not just until code
  compiles.

None of this is available to work that consumes Track 1's output instead: it carries
no `[Context: ...]` tag at all, so the "Detect" step of the same contract
finds nothing to extract, and every stage above would have to re-derive
scope, actors, and open questions from the bare ticket text a second (and
third, and fourth) time — or, worse, inherit Track 1's own un-flagged ARIA
hallucination into a design document or test plan with no signal that it was
never grounded in the first place. This is the compounding effect: Track 2's
context package is generated once, but its value is spent repeatedly — every
later stage of work that consumes the tagged user-story output gets the
grounding for free, while Track 1's cost (re-deriving scope, or worse,
propagating an invented mechanism) is paid again at each stage
independently.

## 9. Outcome

**Measured, not inference, on every rubric dimension above** — this case did
not need to fall back on a judgment call anywhere in §7 or §8; every claim
(a citation is real or isn't, an AVP exists or doesn't, a section is present
or isn't, a tag is extractable or isn't per the consuming contract's own
mechanical steps) is directly checkable against the pinned repo, the two
generated files, or the consuming contract's own text. What remains a
judgment call, disclosed as such: whether this rubric is the *right* rubric,
and whether a finding from one feature, one consuming skill, and one
downstream-contract read-through generalizes — see §10.

This result is a clean, unambiguous win for the with-CEP track on every
dimension measured, with the same honest asterisk the first case study
carried: Track 2's own output is not itself perfect (the disclosed, still-
open `Feature-List` bitmask question; the self-disclosed-placeholder NFR
number) — this case reports that CEP measurably improves generated output's
grounding and its downstream reusability, not that it makes the output
flawless or implementation-ready without further review.

## 10. Limitations

Single feature, single consuming skill, single codebase, one run per track —
not a blind trial, and not a claim that this generalizes to every consuming
skill or every feature shape. Ground truth for traceability/hallucination
checks is knowable here specifically because this is a real, unimplemented
feature in a real, inspectable codebase with an already-working analogous
pattern (Gx) to check citations against; a genuinely novel feature with no
analogous real code to cite would not let this rubric run the same way. The
bare-ask baseline (§4) is one reasonable phrasing of a terse ticket, not the
only one a developer might write — a differently-worded bare ask could
plausibly hallucinate less, or more. §8's downstream-compounding-benefit
section is a mechanical trace through `CONSUMING-USER-STORY-OUTPUT.md`'s own
documented contract, not an actual run of any design, planning, test-writing,
or implementation stage against either track's output — that would be a
further, larger case study of its own, not attempted here. Track 2's org convention is reused from a different pilot
project (`re2`), not one native to `dogfood-open5gs`, the same disclosed
substitution the first case study made — this measures CEP's context-package
benefit correctly, but means the "convention adherence" dimension is partly
measuring convention *availability*, a prerequisite CEP's approval workflow
enables but doesn't itself guarantee exists for every project.

## 11. Lessons learned

**The core finding from the first case study generalizes across domains, not
just within one.** The Textual case showed ungrounded generation inventing a
plausible-but-wrong UI/accessibility concept. This case shows the same
failure mode in a domain with essentially no surface-level overlap — a
headless C telecom signaling stack — and the invented concept (ARIA) isn't
even topically adjacent to the domain, unlike the Textual case where ARIA at
least belonged to the same broad category (UI accessibility). That is
arguably a *sharper* finding: an ungrounded consuming skill's hallucination
risk is not bounded by domain plausibility at all — it can import a concept
wholesale from a completely unrelated field with no internal signal that
anything is wrong.

**A context package's most valuable disclosed gap is the one closest to a
plausible wrong answer.** This case's Gy feature has an unusually sharp
version of this: `OC-Supported-Features` (RFC 7683 Overload Control) already
sits, commented out, at the exact dictionary location a naive implementer —
human or model — would reach for when adding `Supported-Features`. Track 2's
package explicitly flagged this as a non-goal/gap rather than letting the
consuming skill discover or ignore it silently; this is a stronger example of
the first case study's "coverage ceiling, not floor" lesson, because here the
trap is not an omission but an actively misleading piece of adjacent, real
code sitting exactly where the mistake would be made.

**Downstream compounding is real but currently mechanical, not yet
empirically run end-to-end.** §8 traces, correctly and verifiably, how
`CONSUMING-USER-STORY-OUTPUT.md`'s own Detect/Extract/Apply/Announce steps
would pick up Track 2's tags and would find nothing in Track 1's output. That
trace is itself Measured (the contract's text is unambiguous about what it
does with a found or missing tag). What it does not yet measure is the
downstream skill's *actual generated output quality* with vs. without that
tag available — the natural next case study in this family, following the
same two-track method one hop further into a downstream planning or
test-writing stage (e.g. that stage fed Track 2's tagged stories vs. Track
1's untagged ones). Recorded here as a candidate for the next case in this
directory, not started in this run.

## Reproduction steps

1. Clone `open5gs/open5gs`, check out tag `v2.8.0`
   (commit `157f611a530e292e40ec50f9d23f0ef5d4fcd6a6`), into a working
   directory (this run used `dogfood-open5gs/`, sibling to
   `open5gs-ietf-rfc`'s own clone at the same pin).
2. Confirm the absence this feature relies on:
   `grep -n "Supported-Features" lib/diameter/gy/dict.c lib/diameter/gy/message.h lib/diameter/gy/message.c`
   — expect zero matches for the real AVP name (only the unrelated, commented-out
   `OC-Supported-Features` lines at `dict.c:185,216`).
3. Confirm the Gx precedent this feature mirrors:
   `grep -n "Supported-Features" lib/diameter/gx/dict.c lib/diameter/gx/message.h lib/diameter/gx/message.c`
   and `sed -n '323,353p' src/smf/gx-path.c`.
4. Confirm the S6a contrast (the pattern this feature deliberately does
   *not* copy): `sed -n '1300,1455p' src/hss/hss-s6a-path.c` — note the two
   separate `Feature-List-ID` blocks.
5. Confirm `smf_gy_send_ccr()`'s 3 real callers:
   `graphify explain "smf_gy_send_ccr()" --graph graphify-out/graph.json`
   (or `grep -n "smf_gy_send_ccr(" src/smf/gsm-sm.c`).
6. Build the context package (not committed — see the AGPL-3.0 disclosure
   above) at `dogfood-open5gs/contexts/gy-supported-features_feature-add_20260726.yaml`
   with the 12 `context_items` cited in §4/§7, then verify its hash:
   `python .github/skills/ult-context-generate/scripts/content_hash.py "dogfood-open5gs/contexts/gy-supported-features_feature-add_20260726.yaml"`
   — expect `8b9327e0`, reproducibly (re-running the hash script against the
   filled-in file returns the same value).
7. **Track 2 (with CEP):** run the vendored skill's Step 1 against the
   package from step 6, reusing `tmp-graphify-cpp-smoke/re2/org-conventions/user-story.yaml`
   as the org convention (disclosed substitution, §4 above). Expect output
   matching [`mode-1-with-cep-output.md`](mode-1-with-cep-output.md).
8. **Track 1 (without CEP):** run the same skill against only the bare ask
   quoted in §2/§4 above, with no context package or org convention
   available. Expect output matching
   [`mode-2-without-cep-output.md`](mode-2-without-cep-output.md).
9. Verify §7's traceability/hallucination claims independently:
   `grep -rniw "aria" lib/ src/` (expect zero matches in the pinned clone),
   `grep -n "Supported-Features" lib/diameter/s6a/message.h lib/diameter/s6a/message.c`,
   `grep -n "OGS_DIAM_GY_CC_REQUEST_TYPE_TERMINATION_REQUEST" src/smf/gy-path.c`.
