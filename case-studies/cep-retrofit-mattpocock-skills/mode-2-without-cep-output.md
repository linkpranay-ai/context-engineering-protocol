<!--
Mode 2: pristine to-spec (vendored-skill/to-spec.pristine.SKILL.md) run against the same bare-ask
task wording as Mode 1, with no CEP context package loaded. Per the skill's own Process step 1, a
real run would explore the repo before writing — the exploration budget here is deliberately
bounded to what a developer's terse ticket plus a quick, unguided skim would plausibly surface in a
single pass, not the exhaustive, pre-distilled evidence Mode 1 received from the package. This is
the realistic "no interview, bare ask" baseline the skill is designed for. Captured verbatim as
generated — not hand-polished after the fact.

Bare-ask ticket text (identical task to Mode 1):
"Sparkline doesn't show where zero is when data has positive and negative values. Can we add a
baseline marker option?"
-->

## Problem Statement

When a `Sparkline` widget displays data that includes both positive and negative numbers, there's no
visual cue for where zero falls. Users can't easily distinguish positive segments from negative ones
just by looking at the sparkline.

## Solution

Add a baseline marker option to `Sparkline` that, when enabled, highlights the zero point on the
chart so users can see at a glance which values are above vs. below zero.

## User Stories

1. As a user viewing a sparkline of mixed positive/negative data, I want to see a baseline marker at zero, so that I can tell which bars are positive and which are negative.
2. As a developer, I want the baseline marker to be an opt-in setting, so that it doesn't change the appearance of sparklines I've already built.
3. As a developer, I want the baseline marker to be simple to turn on, so that adopting it is low-effort.
4. As a user, I want the baseline marker to look different from the regular data bars, so I don't mistake it for a data point.
5. As a developer, I want the feature to work with whatever data I pass in, so that I don't have to change how I feed data into the widget.
6. As a user viewing all-positive or all-negative data, I want the sparkline to look the same as it does today, so the new option doesn't add visual noise where it isn't needed.
7. As a developer, I want to be able to customize the marker's color, so that it fits my app's theme.
8. As a maintainer, I want this to be a non-breaking, additive change, so existing usages of `Sparkline` aren't affected.

## Implementation Decisions

- Add a boolean-style option to `Sparkline` to turn the baseline marker on. Off by default.
- The widget currently renders each data point as a bar scaled to the data's range; the baseline
  marker should be drawn as an extra bar/segment inserted at the position in the data range that
  corresponds to zero.
- The marker should use a distinct, likely configurable, color so it's visually separate from the
  normal high/low-colored bars.
- If the data doesn't contain a mix of positive and negative values, the marker option should
  effectively have no visible effect, since there's no zero-crossing to mark.
- This is a self-contained visual feature and shouldn't require changes to how callers pass data
  into the widget — only how that data is rendered.

## Testing Decisions

- Tests should verify the widget's rendered output changes correctly when the baseline marker is
  enabled, and is unchanged when it's disabled (the default).
- Cover mixed-sign data, all-positive data, and all-negative data as separate cases.
- Prior art: the project already has per-widget snapshot tests — a new test named after this widget
  (something like `tests/snapshot_tests/test_sparkline.py`) is likely the right place to add
  coverage, following whatever pattern the existing sparkline snapshot test already uses.

## Out of Scope

- Any styling system beyond a basic configurable marker color.
- Changing the widget's existing color scheme for non-marker bars.

## Further Notes

- Should double check whether this widget has an underlying "renderable" class separate from the
  public widget, since some Textual widgets split rendering logic that way — if so, the
  implementation might need to live in both places, or just the lower-level one.
- Any real PR against this project needs to be tagged appropriately per repo contribution
  guidelines (not investigated in detail for this pass).
