# Case Study: consumer-benefit-user-stories

```yaml
case: consumer-benefit-user-stories
codebase: Textualize/textual, MIT, ~90k LOC Python (TUI framework) — same pinned clone as
  case-studies/textual/CASE-STUDY.md
date_run: 2026-07-25
author: dogfooding run, context-engineering-oss
negative_control: false
```

Every other case in this directory measures CEP's benefit on a **retrieval** task — finding the
right integration point or clause cheaper than a naive search would. This case measures a different
kind of benefit: whether an approved context package makes a **downstream consuming skill's
generated output** better, not just cheaper to produce. The consuming skill is
`spw-write-user-story` — a real, already-built, ground-up skill maintained outside this repo (not
part of CEP, not built for this case study) that writes user stories for a feature from either a
loaded context package or a bare ask. A vendored, reference-only copy lives in
[`vendored-skill/`](vendored-skill/) for reproducibility — see that directory's header note and
[`ROADMAP.md`](../../ROADMAP.md) "Not on this roadmap" for why it is not, and will not become, an
installable CEP skill.

This case reuses the context package Run A of `case-studies/textual/CASE-STUDY.md` already
produced and had approved — `contexts/disabled-widget-focusable_feature-add_20260706.yaml`
(`content_hash: 4ed6ad43`, `human_approved: true`) — rather than generating a new one. No new
package-generation work was needed or done for this case; §3-§5 below are inherited from that case
by reference, not re-run.

## Results at a glance

| Metric | Without CEP (bare ask) | With CEP (approved package) | Kind |
| --- | --- | --- | --- |
| Real, file/line-grep-verifiable citations | 0 | 8 distinct real locations (`screen.py:808`, `widget.py:832`, `widget.py:872`, `widget.py:2368`, `button.py:421`, `button.py:429`, `docs/guide/input.md:120`, `COMPILED-GUIDELINES.md:27-30`), all confirmed present via direct grep against the pinned clone | Measured |
| Hallucinated APIs/concepts | 2 (`Button.set_focusable_when_disabled()` — no such method anywhere in the codebase; an ARIA/"live region" screen-reader mechanism — zero matches for `aria`\b or "live region" anywhere in `src/textual/` or `docs/`) | 0 | Measured |
| Distinct, feature-relevant actors named | 2 (generic "User", "Developer") | 5 (keyboard-only user, screen-reader user, app developer, widget author/maintainer, regression test suite as a system actor) | Measured |
| NFR acceptance criteria with a number+unit | 0 of 1 ("should not noticeably affect app performance") | 1 of 1 (5% p95 build-time regression on a 200-widget screen) — but see note below | Measured |
| Org-convention `required_sections` present per story | 0 of 7 (no convention was available to follow — Observability, Blast-radius, and Dependencies sections are entirely absent from every story) | 7 of 7, every story/Enabler | Measured |
| `[Context: ...]`/provenance tagging present | None | Every story tagged with the package id + `content_hash` it was generated from | Measured |

The NFR row needs its own caveat, not glossed over: Mode 1's number (5% p95, 200 widgets) is
self-disclosed inside its own output as an unvalidated placeholder, not a benchmarked figure — it
passes the *form* check (does the criterion carry a number+unit?) without passing a *provenance*
check (was that number ever measured?). See §9 and §11.

## 1. Environment

Same pinned clone as `case-studies/textual/CASE-STUDY.md`: `Textualize/textual`, tag `v8.2.8`,
commit `1d99508b928a771b51e1a527319c6b87dcff9e05`. No new `graphify`/`ult-context-generate` run —
this case starts from that case's already-approved Run A package. The consuming skill
(`spw-write-user-story`, vendored copy under `vendored-skill/`) was run twice, directly, with no
live interactive agent session beyond the two generation runs themselves — same "no live human
reviewer" disclosure as every other case in this directory.

## 2. Task

Identical feature description in both modes, so the only variable is what the generating skill had
available to read: allow a disabled `Button` (and, more generally, disabled widgets) to remain part
of the keyboard focus chain instead of being fully skipped, so a keyboard-only user can Tab to a
disabled control and discover why it's disabled, while keeping it inert to activation — the same
task as Run A of the Textual case study.

## 3. Source set

Inherited from `case-studies/textual/CASE-STUDY.md` §3/§4 (Run A) for Mode 1 — not re-derived here.
Mode 2 has no source set by construction: the bare-ask baseline (§4 below) supplies only the task's
own one-to-two-sentence wording, with no context package, no actor list, and no org convention
available to the generating skill.

## 4. Package generation / bare-ask baseline definition

**Mode 1 (with CEP):** the skill's Step 1 loaded `contexts/disabled-widget-focusable_feature-add_20260706.yaml`
(`content_hash: 4ed6ad43`, `human_approved: true`) and, since `dogfood-textual` has no
`org-conventions/user-story.yaml` of its own, reused the structurally generic, previously-approved
convention from the `re2` pilot project (`tmp-graphify-cpp-smoke/re2/org-conventions/user-story.yaml`)
— disclosed here as a substitution, not a silent assumption. Full generated output:
[`mode-1-with-cep-output.md`](mode-1-with-cep-output.md).

**Mode 2 (without CEP) — this case's bare-ask baseline definition, the consumer-output-quality
analogue of `EVIDENCE-METHODOLOGY.md` §4's naive-keyword-search baseline:** the same skill, run
against only this one-to-two-sentence ask, with Step 1's context-package and org-convention lookups
both returning no match (by construction — no `contexts/disabled-widget-focusable_user-story_*.yaml`
or `org-conventions/user-story.yaml` exists for this exact bare-ask scenario):

> Add support for disabled widgets to remain focusable. Users should be able to Tab to a disabled
> button so they know why it's disabled — add an opt-in setting for this.

This is meant to read like a real, terse ticket a developer would actually start from — not a
deliberately starved strawman. Full generated output: [`mode-2-without-cep-output.md`](mode-2-without-cep-output.md).

## 5. Detected gaps, conflicts, staleness

Inherited from `case-studies/textual/CASE-STUDY.md` §5 (Run A) for Mode 1: no conflicts, one
expected complete gap (the feature aspect itself, pre-implementation). Mode 2 has no gap/conflict
detection at all — there is no context package for any check to run against, which is itself part
of what this case measures: losing gap detection is a cost of skipping CEP, not a neutral omission.

## 6. Rubric (fixed before either output was read)

Six dimensions, fixed before scoring either output to avoid post-hoc bias, each independently
checkable against the real `dogfood-textual` source where possible:

- **Traceability** — does the story cite real functions/classes/files that exist in the repo
  (checkable via grep)?
- **Hallucination** — does it invent APIs/behavior that don't exist?
- **Actor coverage** — distinct, feature-relevant actors named vs. generic filler.
- **NFR specificity** — acceptance criteria with a number+unit vs. vague terms (the same gate
  `spw-write-user-story` Step 4 already self-checks for).
- **Testability** — could an engineer write a test straight from the acceptance criteria?
- **Convention adherence** — does the output match the org convention's `required_sections`, or
  invent its own shape?

## 7. Scoring

**Traceability — Measured.** Mode 1 cites 8 distinct real locations, every one confirmed present by
direct grep against the pinned clone (`screen.py:808`'s `_check_disabled()` skip inside
`_focus_chain`; `widget.py:832`'s `_check_disabled()` definition, `return self.disabled or
self.loading`; `widget.py:872`'s `allow_focus()`, `return self.can_focus`; `button.py:421/429`'s
`press()` guard; `docs/guide/input.md:120`; `COMPILED-GUIDELINES.md:27-30`). Mode 2 cites zero real
locations — it names no file or line anywhere.

One real completeness gap in Mode 1, disclosed here rather than silently corrected: `widget.py:2368`'s
`focusable` property has its *own*, separate disabled check (`not self._self_or_ancestors_disabled`,
line 2374) — a second call site alongside the one Mode 1's ENB-001 did find (`_focus_chain`'s
`_check_disabled()` skip at `screen.py:808`). The approved context package's `context_items` didn't
carry a citation for this second site, and Mode 1's output inherited that gap rather than catching
it independently. This is a real, measured limitation of this specific package's coverage, not of
the consuming skill — see §11.

**Hallucination — Measured.** Mode 1: 0. Mode 2: 2 — `Button.set_focusable_when_disabled()` (no
match anywhere in `src/textual/`, confirmed via grep) and a screen-reader "ARIA live region"
mechanism (zero whole-word matches for `aria` or `live region`/`live_region` anywhere in
`src/textual/` or `docs/` — Textual is a terminal UI framework with no ARIA/web-accessibility layer
to begin with, so this isn't a missed citation, it's an imported concept from a different domain
that doesn't map onto this codebase at all).

**Actor coverage — Measured.** Mode 1: 5 distinct actors (keyboard-only user, screen-reader user,
app developer, widget author/maintainer, regression test suite as a system actor), each tied to a
specific story. Mode 2: 2 generic actors ("User", "Developer"), with no system-actor or
stakeholder-persona decomposition at all — the skill's own Step 2.5 3-bucket actor prompt is driven
off a loaded package's aspect list, so with nothing loaded, that step had nothing to work from.

**NFR specificity — Measured, with a caveat.** Mode 1's NFR-001 carries a number+unit (5% p95
build-time regression, 200-widget screen) and passes the gate mechanically — but its own text
discloses the number as a self-authored placeholder, not a benchmarked figure, since the context
package carries no measured performance baseline to cite. Mode 2's NFR-001 ("should not noticeably
affect app performance") carries no number or unit at all and fails the gate outright, with nothing
to fall back on. Net: Mode 1 is more specific in form, honestly non-authoritative in substance; Mode
2 is neither.

**Testability — Measured.** Mode 1: 5 of 6 story/NFR acceptance-criteria sets map directly onto a
concrete, existing test pattern (`tests/test_focus.py`'s `screen.focus_chain` assertion style); the
sixth (US-002's screen-reader discoverability mechanism) is explicitly left as an open question
rather than an invented answer. Mode 2: of its four acceptance-criteria sets, one (US-001's
screen-reader criterion) routes through the fabricated ARIA mechanism and one (US-002's) routes
through the fabricated method name — neither is testable as written without first inventing
something that doesn't exist in the codebase; only US-003 and NFR-001 are cleanly, if vaguely,
testable.

**Convention adherence — Measured.** Mode 1: all 7 of the org convention's `required_sections`
(Story statement, Scope and non-scope, Acceptance criteria, Non-functional criteria, Observability
and failure semantics, Blast-radius and non-regression checks, Dependencies and rollout notes)
present for every Enabler and story. Mode 2: 0 of 7 — with no convention loaded, the output falls
back to a generic "As a / I want / So that" plus acceptance criteria shape only; Observability,
Blast-radius, and Dependencies sections are absent from every story, not thinly covered.

## 8. Downstream compounding benefit

The value of the approved context package does not stop at the user-story
file `spw-write-user-story` produces. Per
[`vendored-skill/CONSUMING-USER-STORY-OUTPUT.md`](vendored-skill/CONSUMING-USER-STORY-OUTPUT.md)'s
Detect/Extract/Apply/Announce contract, any later stage of work that picks up
Mode 1's output finds, and can act on, its `[Context: ...]` tags — the same
context package (decisions, gaps, evidence) that grounded the stories
becomes available, pre-identified and already approved, to whatever work
happens next, without re-deriving it from scratch:

- At a **design/review stage**, a design can be cross-checked against the
  story file's own scope and actor list, surfacing a scope mismatch (e.g.
  the screen-reader-discoverability open question US-002 leaves unresolved)
  rather than a reviewer having to rediscover it independently.
- At a **planning stage**, every acceptance criterion can be traced to a
  concrete task, and disclosed gaps (like NFR-001's self-flagged,
  unbenchmarked placeholder) can be carried forward as an explicit planning
  item instead of being silently treated as settled.
- At a **test-writing stage**, acceptance criteria that already read as
  concrete pass/fail conditions (US-001's `screen.focus_chain` assertion
  style) become the test directly, not a paraphrase target.
- At an **implementation stage**, each story's acceptance criteria become
  that piece of work's definition of done.

None of this is available to work that consumes Mode 2's output instead: it
carries no `[Context: ...]` tag at all, so the "Detect" step of the same
contract finds nothing to extract, and every stage above would have to
re-derive scope and actors from the bare ticket a second (and third) time —
or, worse, inherit Mode 2's own unflagged ARIA/fabricated-method
hallucinations into a design document or test plan with no signal that
either was ever invented. This is the compounding effect: the context
package is generated once, but its value is spent repeatedly across every
later stage that consumes the tagged output, while the bare-ask mode's cost
(re-deriving scope, or worse, propagating an invented mechanism) is paid
again independently at each stage. This trace is mechanical, based on the
contract's own documented steps, not an actual run of any further stage
against either mode's output — see §10's Limitations.

## 9. Outcome

**Measured, not inference, on every rubric dimension above** — this case study did not need to fall
back to a judgment call anywhere in §7, because every claim (a citation is real or isn't, an API
exists or doesn't, a section is present or isn't) is directly checkable against the pinned repo or
the two generated files themselves. What remains a judgment call, and is disclosed as such, is
whether this rubric is the *right* rubric, and whether one feature and one consuming skill
generalizes — see §10.

The result is a clean, unambiguous win for the with-CEP mode on every dimension measured, with one
honest asterisk: Mode 1's own output is not itself perfect (the missed second disabled-check call
site in §7's Traceability note; the self-disclosed-placeholder NFR number) — the case is reporting
that CEP measurably improves the generated output's grounding, not that it makes the output
flawless.

## 10. Limitations

Single feature, single consuming skill, single codebase, one run per mode — not a blind trial and
not a claim that generalizes to every consuming skill or every feature shape. Ground truth for the
traceability/hallucination checks is knowable here specifically because the real feature already
exists (unimplemented) in a real, inspectable codebase; a task where the "correct" answer is itself
underdetermined (a genuinely novel feature with no analogous real code to check citations against)
would not let this rubric run the same way. The bare-ask baseline (§4) is one reasonable phrasing of
a terse ticket, not the only one a developer might write — a differently-worded bare ask could
plausibly hallucinate less or more. Mode 1 reused an org convention from a different pilot project
(`re2`) rather than one native to `dogfood-textual`; this measures CEP's context-package benefit
correctly (the convention is a real, previously-approved artifact, not fabricated for this case) but
means the "convention adherence" dimension is partly measuring convention availability, which is a
prerequisite CEP's approval workflow enables but doesn't itself guarantee exists for every project.

## 11. Lessons learned

**The core finding generalizes CEP's existing "grounding over guessing" story from retrieval to
generation:** every other case in this directory shows CEP finding the right answer for fewer
tokens; this case shows that when a downstream skill has nothing to ground its output in, it doesn't
just search worse — it invents things (a nonexistent method, an imported-but-inapplicable
accessibility concept) with no signal to the consuming developer that anything was invented at all.
That is a materially different, and arguably more consequential, failure mode than "costs more
tokens."

**A context package's coverage is a ceiling on the downstream skill's grounding, not a floor.** §7's
Traceability note is the sharpest instance: Mode 1's own output missed `widget.py:2368`'s second,
independent disabled-check call site because the approved package's `context_items` didn't carry a
citation for it — the consuming skill correctly used everything it was given, but the package itself
had a real, if narrow, completeness gap. This is not a defect in the consuming skill or in this case
study's method; it is a finding about the specific package under test, logged here rather than
silently patched into Mode 1's already-generated output (which is captured verbatim, per its own
header note). A future package-generation pass over this same feature should re-check whether
`graphify affected`/`explain` on `Widget.focusable` surfaces this second site.

**Gate mechanics check form, not provenance — a real, disclosed gap, not unique to this case.**
NFR-001's Mode 1 number passes the threshold gate (a number+unit is present) while being
self-disclosed as unvalidated. The gate was never designed to verify a number's provenance, only its
presence — worth naming plainly rather than letting a passing gate read as a stronger guarantee than
it is.

## Reproduction steps

1. Follow `case-studies/textual/CASE-STUDY.md`'s Reproduction steps 1-5 to obtain the same pinned
   clone and the same approved package,
   `contexts/disabled-widget-focusable_feature-add_20260706.yaml` (`content_hash: 4ed6ad43`).
2. Copy `vendored-skill/SKILL.md` and `vendored-skill/CONSUMING-USER-STORY-OUTPUT.md` into a
   working directory (they are reference-only; do not install them under `.github/skills/`).
3. **Mode 1:** run the vendored skill's Step 1 against the package from step 1, reusing
   `tmp-graphify-cpp-smoke/re2/org-conventions/user-story.yaml` as the org convention (disclosed
   substitution, §4 above). Expect output matching [`mode-1-with-cep-output.md`](mode-1-with-cep-output.md).
4. **Mode 2:** run the same skill against only the bare ask quoted in §4 above, with no context
   package or org convention available. Expect output matching
   [`mode-2-without-cep-output.md`](mode-2-without-cep-output.md).
5. Verify §7's traceability/hallucination claims independently: `grep -n "_check_disabled"
   src/textual/widget.py src/textual/screen.py`, `grep -n "def allow_focus\|def focusable"
   src/textual/widget.py`, `grep -n "def press" src/textual/widgets/_button.py`, and
   `grep -rniw "aria" src/textual/ docs/` (expect zero matches) against the pinned clone.
