<!--
Mode 1: retrofitted to-spec (vendored-skill/to-spec.retrofitted.SKILL.md) run against
Textualize/textual, commit 1d99508b928a771b51e1a527319c6b87dcff9e05, loading the already-approved,
already-committed package case-studies/textual/sparkline-baseline-marker_feature-add_20260724.yaml
(content_hash: 62a9b119). Captured verbatim as generated — not hand-polished after the fact.
-->

## Problem Statement

When a `Sparkline` renders a dataset that contains both positive and negative values, every bar is
colored and scaled purely relative to the dataset's own min/max — there's no visual indication of
where zero actually falls. A user watching a sparkline of, say, a P&L series or a temperature delta
can't tell at a glance whether a given bar represents a positive or negative value; the sign change
is invisible.

## Solution

Add an optional baseline marker to `Sparkline`: when enabled, draw a visually distinguishable
row/column at the zero value so the sign change is visible at a glance. Off by default — existing
callers see no change in output.

## User Stories

1. As a dashboard user, I want a sparkline of a signed data series to show me where zero is, so that I can tell positive bars from negative bars without reading raw numbers.
2. As a dashboard user, I want the baseline marker to be visually distinct from the normal min/max-colored bars, so that it doesn't get confused with a regular data bar.
3. As an app developer, I want the baseline marker to be opt-in, so that every existing `Sparkline` usage in my app keeps rendering exactly as it does today unless I explicitly ask for the new behavior.
4. As an app developer, I want to enable the baseline marker with a single constructor argument, so that adopting it doesn't require restructuring how I already build my `Sparkline` widgets.
5. As an app developer, I want the baseline marker to work correctly regardless of `summary_function` (min/max/mean/median/last/etc.), so that I don't have to special-case it for whichever bucket-summary function my data pipeline already uses.
6. As an app developer working with all-positive or all-negative data, I want the baseline marker to simply not appear (there's no sign change to mark), so that the feature doesn't clutter sparklines where it isn't meaningful.
7. As a widget author extending `Sparkline`, I want the baseline concept to live in the renderable itself rather than the `Sparkline` widget wrapper, so that anything consuming the renderable directly (not just the widget) gets the same behavior.
8. As a maintainer, I want the existing color-blend behavior (`min_color`→`max_color` via `blend_colors`) to be untouched for every bar that isn't the baseline marker, so that this feature doesn't regress the sparkline's core visual language.

## Implementation Decisions

- The baseline concept is new to this renderable — today's render loop has no notion of "zero" or
  a fixed reference value; every bar's height and color are computed purely relative to the
  dataset's own `minimum`/`maximum` for that render call. Introducing a baseline marker means
  adding a reference value the render loop checks per-bucket, alongside (not instead of) the
  existing min/max-relative height calculation.
- Scope is the renderable only, not the `Sparkline` widget wrapper's CSS/component-class surface —
  a separate pass would decide whether/how the widget exposes a themeable color for the marker via
  its own component classes.
- The feature must be additive to the existing per-bucket render decision: for each rendered
  bucket, in addition to computing the existing height-ratio-driven bar, determine whether that
  bucket's value range straddles zero (i.e., the dataset actually has both positive and negative
  values) and, if so, mark the row/column nearest zero distinctly from the regular min/max color
  blend.
- If the dataset is entirely non-negative or entirely non-positive, there's no sign change and the
  marker must not render at all — this isn't an error case, it's the expected "nothing to mark"
  state.
- The marker's visual treatment must be distinguishable from a normal bar under the existing
  min/max color-blend scheme, not just a different bar character at the same color — otherwise it
  reads as a regular data point at a glance, defeating the point of the feature.

## Testing Decisions

- Only test external behavior: what a rendered sparkline's output segments/colors look like for a
  given dataset, not the internal bucketing math. Same style already used throughout the existing
  sparkline test suite.
- Prior art: the existing renderable tests already assert on rendered ANSI-escaped output directly
  (`render(Sparkline(...))` equality against a literal expected string built from named color
  constants like `GREEN`/`RED`/`BLENDED`/`STOP`) — new tests for the baseline marker should follow
  that same literal-output-comparison style rather than introducing a new assertion approach.
- Needs explicit coverage for: an all-positive dataset (marker absent), an all-negative dataset
  (marker absent), a dataset that straddles zero (marker present at the correct position), and the
  marker's behavior combined with each of the module's supported `summary_function`s, since the
  per-bucket summary value is what determines where a bucket's rendered value lands relative to
  zero.
- The three checked-in snapshot renders for `Sparkline` must be re-verified unchanged for any call
  that doesn't opt into the new parameter — this is a non-regression check, not new-feature
  coverage.

## Out of Scope

- Any change to the `Sparkline` *widget* wrapper's CSS/component-class API (only the renderable is
  in scope for this pass).
- Any change to color-blending behavior for non-baseline bars.
- Any documentation-guide update — this module currently has no dedicated guide-level
  documentation to begin with, only its per-widget reference page, so this is a net-new doc gap
  regardless of whether this feature ships.

## Further Notes

- No existing repo convention (org-level compiled guidelines) has a scoped section for this
  module's path — only a `tests/snapshot_tests/**`-scoped section exists, which doesn't apply here
  since this feature isn't touching snapshot test infra directly (only being checked against it for
  non-regression). Global guidelines still apply: docstrings in the existing style, tests for the
  change, `black` formatting, `CHANGELOG.md` update, full suite green before a PR.
- Any real PR against this project must self-identify as AI-generated (naming the agent used) and
  link to an already-maintainer-approved issue/discussion per this project's compliance
  requirement — not applicable to this spec-only pass, but binds any real follow-through.
- Open question, deliberately not decided here: whether the baseline marker's color should be
  independently configurable (a third `Color` parameter alongside `min_color`/`max_color`) or fixed
  — left for the implementer to resolve against the widget-wrapper CSS/component-class question
  this spec explicitly put out of scope.

---
`[Context: sparkline-baseline-marker_feature-add_20260724, content_hash: 62a9b119, human_approved: true]`
