<!--
Real, verbatim output of running the vendored spw-write-user-story skill
(vendored-skill/SKILL.md) against an approved CEP context package. See
CASE-STUDY.md for methodology. Not edited after generation except for this
header note.
-->

# User Story: Disabled widget focus-chain handling (Button as the representative widget)

**Context package(s):** disabled-widget-focusable_feature-add_20260706@4ed6ad43 (human_approved)

Org convention: org-conventions/user-story.yaml (human_approved) — no `user-story.yaml`
exists yet in the `dogfood-textual` project itself; this run reuses the structurally
generic, previously-approved convention from the `re2` pilot project (same
`required_sections`/`quality_criteria`), disclosed here rather than silently assumed.
See CASE-STUDY.md §1 (Environment) for why.

## Scope

- In scope: allowing a disabled `Button` (and, more generally, disabled widgets) to
  remain part of the keyboard focus chain instead of being fully skipped, so a
  keyboard-only user can Tab to a disabled control and discover why it's disabled,
  while keeping it inert to activation.
- Out of scope: per-widget custom `allow_focus()`/`allow_focus_children()` overrides
  other than `Button`'s default; CSS `:disabled` pseudo-class styling itself; any
  widget other than `Button` used as a worked example.
- Resolution notes: implemented as an opt-in flag defaulting to today's skip-disabled
  behavior, to avoid a breaking change to the documented public contract across the
  whole widget ecosystem. Self-resolved (no live user available in this dogfood run);
  see decision in context package `decisions_log`.
- Validation caution: aspect a2 (the actual feature mechanism) is a complete gap in
  both What-L2/What-L3 layers — expected for a not-yet-built feature-add. The
  mechanism sketch in ctx_003 is implementer guidance, not ready-to-merge code; treat
  ENB-001 below as a design starting point requiring implementation review.

## Affected Areas

Primary touch points: `src/textual/screen.py` (`Screen._focus_chain`),
`src/textual/widget.py` (`Widget._check_disabled`, `Widget.allow_focus`),
`src/textual/widgets/_button.py` (`Button.press`), `tests/test_focus.py`,
`docs/guide/input.md`. Implementer guidance (not separate backlog items, per
constraint routing): tests required for every change + `black` formatting +
`CHANGELOG.md` update + existing docstring style (global convention); any new
focus-ring styling on the focusable-but-disabled state needs a snapshot test under
`tests/snapshot_tests/**`, regenerated only via `make test-snapshot-update` after
visual confirmation (scoped convention).

## Enabler Stories

### ENB-001: Opt-in disabled-but-focusable mechanism

**Type:** Enabler

[Context: disabled-widget-focusable_feature-add_20260706@4ed6ad43 · ctx_001, ctx_002, ctx_003 · aspect a1, a2]

Add a new opt-in flag that, when set, keeps a disabled widget in the focus chain
instead of `Screen._focus_chain` skipping it and its subtree at the DOM-traversal
level. `Widget.allow_focus()` is the documented override point for focus-permission
logic but does not itself check `self.disabled` — the skip happens earlier, in
`_focus_chain`'s disabled-skip branch — so the new flag's check belongs there, not
inside `allow_focus()`.

Story statement:
- Establish one implementation path for the opt-in disabled-focusable check, reused
  by every disabled widget that enables it, not just `Button`.

Scope and non-scope:
- Scope: the new flag, the `_focus_chain` check that consults it, default-off
  behavior for every existing call site.
- Non-scope: any change to `allow_focus()`/`allow_focus_children()`'s own contract.

Acceptance criteria:
- A disabled widget with the new flag set remains in the focus chain produced by
  `Screen._focus_chain`.
- A disabled widget without the flag set (the default) is skipped exactly as today.
- `Widget._check_disabled()` today returns `self.disabled or self.loading` — the new
  flag's check must decide explicitly whether a merely-`loading` (not `disabled`)
  widget is affected, rather than inheriting that conflation silently.

Non-functional criteria:
- No measured performance target available in the context package for this check;
  see NFR-001's disclosed placeholder threshold.

Observability and failure semantics:
- Not applicable — this is a synchronous traversal-order change, not a background
  operation with its own failure mode.

Blast-radius and non-regression checks:
- `Widget.allow_focus()` is called by `Widget.focusable()`, consumed by every
  focus-chain build and mouse click-to-focus check — must keep returning a stable
  bool.
- Loosening the disabled skip must not also start including `loading` widgets, since
  `_check_disabled` conflates the two today.

Dependencies and rollout notes:
- Must complete before the actor-driven stories below are finalized.
- Rollout is opt-in per widget/instance, consistent with the resolved decision above.

Referenced by: US-001, US-002, US-003, US-004, US-005, NFR-001

### ENB-002: AI-generated PR compliance disclosure

**Type:** Enabler

[Context: disabled-widget-focusable_feature-add_20260706@4ed6ad43 · ctx_010 · aspect (none — global constraint)]

If the pull request implementing this feature is AI-generated, it must self-identify
as such (naming the agent used) and link to an issue or discussion already approved
by a maintainer (`@willmcgugan`) — a PR missing either is subject to being closed
without comment.

Story statement:
- Ensure the implementation PR for this feature, if AI-assisted, meets the project's
  disclosed AI-PR policy before submission.

Scope and non-scope:
- Scope: PR description content and prior maintainer approval linkage.
- Non-scope: any code behavior; this is a submission-process constraint, not a
  feature requirement.

Acceptance criteria:
- If AI-generated, the PR description names the agent used.
- The PR links to a maintainer-approved issue/discussion for this feature before
  submission.

Non-functional criteria:
- Not applicable (process constraint, not a runtime property).

Observability and failure semantics:
- Not applicable.

Blast-radius and non-regression checks:
- Not applicable — no code touched by this item.

Dependencies and rollout notes:
- Applies once, at PR submission time, to the feature's implementation PR as a whole
  — not tied to a specific functional story below.

Referenced by: (none — this constraint routes to the PR process for the whole
feature, per the org convention's compliance/global routing rule, not to an
individual functional story. Flagged in CASE-STUDY.md as a routing-table edge case:
the `Referenced by:` field, designed for technical enablers with a natural set of
dependent stories, has no natural target here.)

## Functional and NFR Stories

### US-001: Keyboard-only user can Tab to a disabled Button and discover why it's disabled

[Context: disabled-widget-focusable_feature-add_20260706@4ed6ad43 · ctx_001, ctx_002, ctx_003 · aspect a1, a2]

As a keyboard-only user of a Textual app
I want to be able to Tab to a disabled control
So that I can discover why it's disabled instead of having it silently vanish from
my navigation order.

[Enabler: ENB-001]

Story statement:
- Extend keyboard focus navigation to include a disabled widget when the app opts in.

Scope and non-scope:
- Scope: Tab/Shift+Tab focus-chain traversal reaching a disabled widget with the flag
  set.
- Non-scope: what the widget shows once focused (tooltip/help text content is a
  separate, unscoped concern — see Out of scope above).

Acceptance criteria:
- Given a disabled `Button` with the opt-in flag set, when the user presses Tab
  through the screen, then the button receives focus in its normal chain position.
- Given the same button without the flag set, when the user presses Tab, then the
  button is skipped exactly as today (unchanged default).
- Given the button has focus, when the user inspects it, then it is visibly
  distinguishable as disabled (existing `:disabled` CSS state, per Out of scope —
  no new styling required by this story).

Non-functional criteria:
- Not applicable to this story (see NFR-001 for the cross-cutting performance
  concern).

Observability and failure semantics:
- Not applicable — no new failure mode; focus either lands on the widget or it
  doesn't.

Blast-radius and non-regression checks:
- Existing `tests/test_focus.py::test_focus_chain` fixed-order assertions must keep
  passing unmodified for screens with no opted-in disabled widgets.

Dependencies and rollout notes:
- Depends on ENB-001.
- Default remains opt-in; no existing app's tab order changes without a code change.

[Actor: Keyboard-only user]

### US-002: Screen-reader user is informed a focused control is disabled

[Context: disabled-widget-focusable_feature-add_20260706@4ed6ad43 · ctx_003, ctx_007 · aspect a2, a5]

As a screen-reader user of a Textual app
I want the disabled state of a focused control announced or otherwise discoverable
So that I understand why the control doesn't respond, instead of assuming it's
broken.

[Enabler: ENB-001]

Story statement:
- Make the disabled state discoverable once focus reaches the widget, not just
  visually distinguishable.

Scope and non-scope:
- Scope: disabled-state discoverability at the point of focus.
- Non-scope: a full accessibility/screen-reader API for Textual — out of scope per
  this context package (no What-L2/What-L3 coverage of one exists).

Acceptance criteria:
- Given a disabled, focusable `Button` receives focus, then some discoverable signal
  of its disabled state is present at the point of focus (mechanism to be decided
  during implementation — this context package has no existing accessibility-API
  coverage to cite; flagged for stakeholder input rather than invented here).

Requirement Note:
- RN-001: `docs/guide/input.md`'s existing public-contract statement ("a disabled
  widget cannot receive focus even if `can_focus` is `True`") must be updated to
  describe the new opt-in behavior — this is a documented-behavior change, not an
  internal-only refactor.
- Covered by: this story's acceptance criterion above; the doc update itself is not
  independently testable and is tracked as a docs-completeness check at review time.

Non-functional criteria:
- Not applicable.

Observability and failure semantics:
- Not applicable.

Blast-radius and non-regression checks:
- `docs/guide/widgets.md`'s existing focus-cycling explanation must stay accurate:
  the focusable-but-disabled widget participates in Tab cycling only — keybinding-
  triggered actions stay suppressed (see US-004).

Dependencies and rollout notes:
- Depends on ENB-001.
- The exact discoverability mechanism is an open implementation question, not
  resolved by this context package — see CASE-STUDY.md's Lessons Learned.

[Actor: Screen-reader user]

### US-003: App developer can opt in without breaking existing apps

[Context: disabled-widget-focusable_feature-add_20260706@4ed6ad43 · ctx_001, ctx_003 · aspect a1, a2]

As an app developer using Textual's `Button` widget
I want to opt in to disabled-but-focusable behavior explicitly
So that adopting the new Textual version doesn't silently change my existing app's
tab order.

[Enabler: ENB-001]

Story statement:
- Guarantee the new behavior is additive and requires an explicit choice.

Scope and non-scope:
- Scope: the opt-in flag's default value and its documentation.
- Non-scope: any auto-migration or deprecation path — this is a purely additive
  feature per the resolved decision.

Acceptance criteria:
- Given an app built against the current Textual release, when upgraded to the
  version shipping this feature without any code change, then focus-chain behavior
  for all existing disabled widgets is bit-for-bit unchanged.
- Given a developer wants the new behavior, when they set the new flag on a
  `Button`, then that button (and only that button, by default) becomes
  focusable-but-inert while disabled.

Non-functional criteria:
- Not applicable to this story.

Observability and failure semantics:
- Not applicable.

Blast-radius and non-regression checks:
- No regression in `Widget.focusable()`'s existing consumers (every focus-chain
  build, every mouse click-to-focus check) for widgets that don't set the new flag.

Dependencies and rollout notes:
- Depends on ENB-001.
- Rollout can start with `Button` only, per the feature's stated scope, before
  generalizing to other widgets.

[Actor: App developer]

### US-004: Widget author's activation guards stay inert for a focusable disabled Button

[Context: disabled-widget-focusable_feature-add_20260706@4ed6ad43 · ctx_004, ctx_008 · aspect a3]

As a Textual widget author/maintainer
I want `Button.press()`'s existing disabled guard to keep working unchanged
So that making a disabled button focusable never allows it to be activated via
Enter/Space or click.

[Enabler: ENB-001]

Story statement:
- Confirm and preserve the existing activation guard rather than adding a new,
  possibly redundant one.

Scope and non-scope:
- Scope: verifying `Button.press()`'s independent `self.disabled` guard is
  sufficient once the widget can receive focus while disabled.
- Non-scope: adding any new guard — `Button.press()` (button.py:429) already returns
  immediately with no `Pressed` message when `self.disabled`, regardless of focus
  state; no code change is needed here, only a verifying test.

Acceptance criteria:
- Given a disabled, focusable `Button` has focus, when Enter or Space is pressed,
  then `Button.press()` returns without emitting a `Pressed` message or calling any
  action (existing guard, unchanged).
- Given the same state, when the button is clicked, then the same guard applies.

Non-functional criteria:
- Not applicable.

Observability and failure semantics:
- Not applicable.

Blast-radius and non-regression checks:
- `docs/guide/widgets.md`'s keybinding-triggered-actions description must remain
  accurate: suppressed while disabled, regardless of focus (consistent with US-002's
  blast-radius note).

Dependencies and rollout notes:
- Depends on ENB-001 only for the widget to be reachable by focus in the first
  place; the guard itself needs no new implementation.

[Actor: Widget author]

### US-005: Regression test suite proves the change without breaking existing coverage

[Context: disabled-widget-focusable_feature-add_20260706@4ed6ad43 · ctx_005, ctx_006 · aspect a4]

As the Textual regression test suite (system actor)
I want new disabled-focus test fixtures added alongside the existing focus-chain and
allow_focus tests, in the same assertion style
So that the feature is provably correct and existing coverage never silently
regresses.

[Enabler: ENB-001]

Story statement:
- Add disabled-focus fixtures without modifying existing fixed-order assertions.

Scope and non-scope:
- Scope: new test cases in `tests/test_focus.py`'s existing style (build a compose
  tree, read `screen.focus_chain`, assert the id list) covering a disabled widget
  with the opt-in flag set and unset.
- Non-scope: rewriting or loosening `test_focus_chain`'s or `test_allow_focus`'s
  existing assertions.

Acceptance criteria:
- `tests/test_focus.py::test_focus_chain` and `test_allow_focus` (existing,
  unmodified) continue to pass after the change.
- A new test asserts a disabled, opted-in widget's id appears in
  `screen.focus_chain`'s output at its expected position.
- A new test asserts a disabled, non-opted-in widget's id is absent, exactly as
  today.

Non-functional criteria:
- Added tests complete within the existing `test_focus.py` suite's normal run time
  (no specific number available in the context package; qualitative criterion only).

Observability and failure semantics:
- Not applicable.

Blast-radius and non-regression checks:
- Zero modification to existing assertions in `test_focus_chain`/`test_allow_focus` —
  new cases are additive only.

Dependencies and rollout notes:
- Depends on ENB-001.
- Per the global convention (ctx_009), the full test suite (`make test`) must pass
  before this feature's PR is opened.

[Actor: Regression test suite]

### NFR-001: Focus-chain traversal overhead stays within an acceptable bound

[Context: disabled-widget-focusable_feature-add_20260706@4ed6ad43 · ctx_001, ctx_002 · aspect a1]

As a Textual widget author/maintainer
I want the new disabled-focusable check to add negligible overhead to focus-chain
construction
So that apps with many widgets don't see a measurable slowdown from a feature most
of them won't even use.

[Enabler: ENB-001]

Story statement:
- Bound the performance cost of the new check.

Scope and non-scope:
- Scope: `Screen._focus_chain`'s traversal cost with the new check present but
  unused (flag unset, the common case).
- Non-scope: any optimization of the existing traversal beyond this new check.

Acceptance criteria:
- Adding the new opt-in check to `Screen._focus_chain` must not increase focus-chain
  build time by more than 5% p95 for a screen with 200 widgets, none using the new
  flag.

Non-functional criteria:
- The 5%/200-widget figure above is a self-authored placeholder threshold —
  **Inference, not benchmarked** — chosen as a conservative, testable number in the
  absence of any measured performance baseline in this context package. Flagged for
  stakeholder validation before merge, consistent with the skill's own guidance for
  items with no `llm_scaffold_count`-backed measurement to cite.

Observability and failure semantics:
- Not applicable.

Blast-radius and non-regression checks:
- Same traversal function (`Screen._focus_chain`) used by every screen in every
  Textual app — a regression here is global, not scoped to apps using the new flag.

Dependencies and rollout notes:
- Depends on ENB-001.
- Should be benchmarked once ENB-001 has a real implementation to measure, not
  estimated further here.

[Actor: Widget author]

## Story-Craft Additions

No story-craft additions (Step 4.5). Reviewed the generated stories against
feature-add story-structure patterns (system-actor stories for automated
enforcement, admin/end-user perspective split, error-recovery-distinct-from-error
stories) — US-005 already covers the system-actor pattern; the other two patterns
don't apply to a UI-widget-library feature with no admin/end-user split and no
error-recovery flow. Context package unchanged by this step.

## Actor Coverage Gate Check

- Keyboard-only user: covered by US-001.
- Screen-reader user: covered by US-002.
- App developer: covered by US-003.
- Widget author: covered by US-004, NFR-001.
- Regression test suite (system actor): covered by US-005.

## NFR Threshold Gate Check

- NFR-001's acceptance criterion includes a number + unit (5% p95, 200 widgets) —
  passes the gate mechanically, but the number itself is disclosed as an unvalidated
  placeholder (see NFR-001's Non-functional criteria note). The gate checks *form*
  (is there a number?), not *provenance* (is the number real?) — see CASE-STUDY.md
  Lessons Learned for this distinction.

## Requirement Note Coverage Gate Check

- RN-001 (US-002): covered by US-002's acceptance criterion, with a disclosed caveat
  that the doc update itself is checked at review time, not by an automated test.

## Enabler Cross-Reference Gate Check

- ENB-001: referenced by US-001 through US-005 and NFR-001, each carrying a matching
  `[Enabler: ENB-001]` tag. Passes.
- ENB-002: has no `Referenced by:` target — see ENB-002's own note. This is a routing-
  table edge case (compliance/global constraints don't map onto the
  Enabler-references-stories pattern), not a gate failure in the technical sense, but
  worth flagging as an open question for the org convention's maintainers.

## Context Tag Gate Check

- Every story/Enabler/NFR above opens with
  `[Context: disabled-widget-focusable_feature-add_20260706@4ed6ad43 · ...]`, matching
  the package id and `content_hash` (`4ed6ad43`) loaded in Step 1. Passes.

## Refinement Prompt

Would you like to refine any story, add scope, or proceed to planning and
implementation workflows?
