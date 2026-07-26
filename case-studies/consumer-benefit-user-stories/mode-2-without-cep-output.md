<!--
Real, verbatim output of running the vendored spw-write-user-story skill
against the bare ask below, with no context package available (Step 1's
lookup for contexts/<feature-slug>_user-story_*.yaml and
org-conventions/user-story.yaml both come back empty). See CASE-STUDY.md for
methodology. Not edited after generation except for this header note.
-->

# User Story: Disabled widget focus-chain handling

**Context package(s):** none found — Step 1 lookup for
`contexts/disabled-widget-focusable_user-story_*.yaml` returned no match.
**Org convention:** none found — `org-conventions/user-story.yaml` returned no
match. Proceeding on the bare ask alone, per the skill's no-context fallback:
generating from stated scope only, with actors and structure inferred rather
than confirmed against any approved source.

Bare ask, as given:
> Add support for disabled widgets to remain focusable. Users should be able to
> Tab to a disabled button so they know why it's disabled — add an opt-in
> setting for this.

## Scope

- In scope: an opt-in setting that lets a disabled widget stay in the tab
  order.
- Out of scope: not stated by the ask; assumed to exclude anything not
  mentioned (styling, screen-reader behavior) but this is an assumption, not a
  confirmed boundary.

## Affected Areas

Not determinable without a context package. Assumed to involve "the focus
handling code" and "the button widget," without a specific file or function
to point to.

## Enabler Stories

### ENB-001: Add an opt-in disabled-focusable setting

**Type:** Enabler

Add a configuration option that lets a disabled widget stay focusable.

Story statement:
- Provide a way to turn on the new behavior without changing the default.

Acceptance criteria:
- There is a setting that can be turned on per widget.
- When off (default), behavior is unchanged.
- When on, the widget can be focused while disabled.

Referenced by: US-001, US-002

## Functional and NFR Stories

### US-001: User can Tab to a disabled button

As a user
I want to be able to Tab to a disabled button
So that I know why it's disabled.

[Enabler: ENB-001]

Acceptance criteria:
- Given a disabled button with the setting turned on, when I press Tab, then
  the button gets focus.
- Given the setting is off, when I press Tab, then the button is skipped as
  before.
- Given the button has focus, then it should indicate that it is disabled,
  for example by announcing "disabled" through the screen reader's ARIA live
  region or similar accessible-label mechanism.

### US-002: Developer can enable the new setting for a button

As a developer
I want to enable the new opt-in setting on a button
So that my app can offer this behavior where it makes sense.

[Enabler: ENB-001]

Acceptance criteria:
- Given I set `Button.set_focusable_when_disabled(True)`, when the app runs,
  then the button remains in the tab order while disabled.
- The change should not affect other widgets or break anything else.

### US-003: Pressing the disabled button does nothing

As a user
I want a disabled, focused button to not actually trigger its action
So that I can't accidentally activate something that's turned off.

[Enabler: ENB-001]

Acceptance criteria:
- Given the button is disabled and focused, when I press Enter, then nothing
  happens.

### NFR-001: The change should not slow things down

As a developer
I want the new setting to have minimal performance impact
So that apps with lots of widgets don't get slower.

Acceptance criteria:
- The feature should not noticeably affect app performance.

## Actor Coverage Gate Check

- User — covered by US-001, US-003.
- Developer — covered by US-002, NFR-001.

No org-convention-defined actor list was available to check completeness
against, and no 3-bucket actor decomposition (system roles / stakeholder
personas / system actors) was performed, since Step 2.5 in the skill relies on
a loaded context package's aspect list to prompt that decomposition. "User"
and "Developer" are the only actors that occurred to the generation without
that prompt.

## NFR Threshold Gate Check

- NFR-001's acceptance criterion ("should not noticeably affect app
  performance") has no number or unit — fails the gate. No fallback number was
  available to cite or flag as a placeholder, because there was no context
  package to note the absence against.

## Requirement Note Coverage Gate Check

- Not applicable — no compliance/convention/scheduling constraint items were
  available to route, since none were loaded.

## Enabler Cross-Reference Gate Check

- ENB-001: referenced by US-001, US-002. US-003 and NFR-001 omit the
  `[Enabler: ENB-001]` tag despite depending on the same setting — inconsistent
  application, not caught by any structural check since there was no context
  package to gate against.

## Context Tag Gate Check

- Not applicable — no context package was loaded, so no `[Context: ...]` tags
  are present anywhere in this output.

## Refinement Prompt

Would you like to refine any story, add scope, or proceed to planning and
implementation workflows?
