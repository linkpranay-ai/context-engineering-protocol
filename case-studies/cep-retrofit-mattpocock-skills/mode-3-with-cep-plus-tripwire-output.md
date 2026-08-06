<!--
Mode 3: retrofitted to-spec, loading the Mode 3 fixture package
(decision-ledger-fixture/sparkline-baseline-marker_feature-add_20260724.mode3-with-ledger.yaml,
content_hash: 62a9b119 + spliced institutional_memory_hits[]). Per this repo's
CONSUMING-CONTEXT-PACKAGE.md Step 3 (institutional-memory-hits paragraph, fixed 2026-08-06), all
three hits are pre-dispositioned `accepted` so none trigger a STOP — the skill reads each hit's
`reason`/`disposition_reason` and folds it into the draft before writing. Diff-worthy changes from
Mode 1 are called out inline; everything else is intentionally unchanged from Mode 1 to isolate what
the trip-wire layer alone adds on top of the base package. Captured verbatim as generated — not
hand-polished after the fact.
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
8. As a maintainer, I want the existing color-blend behavior (`min_color`→`max_color` via `blend_colors`) to be untouched — and the baseline marker's own color layered additively on top of it, not replacing it — for every bar that isn't the baseline marker, so that this feature doesn't regress the sparkline's core visual language.

## Implementation Decisions

- The baseline concept is new to this renderable — today's render loop has no notion of "zero" or
  a fixed reference value; every bar's height and color are computed purely relative to the
  dataset's own `minimum`/`maximum` for that render call. Introducing a baseline marker means
  adding a reference value the render loop checks per-bucket, alongside (not instead of) the
  existing min/max-relative height calculation.
- **[trip-wire, ihm_001, tier: proceed, accepted]** The marker's color must be an *additional* Style
  layered onto the affected bucket, not a replacement of the existing `blend_colors()` interpolation
  path — a matched institutional-memory hit confirms `blend_colors()` is deliberately the *only*
  color path in this renderable (a prior decision explicitly rejected discrete threshold color
  bands), so a baseline marker that swapped in a different color mechanism for one bucket would cut
  against that established constraint rather than extend it.
- Scope is the renderable only, not the `Sparkline` widget wrapper's CSS/component-class surface —
  a separate pass would decide whether/how the widget exposes a themeable color for the marker via
  its own component classes. **[trip-wire, ihm_002, tier: proceed, accepted]** A second matched hit
  independently corroborates this exact boundary (new visual features belong in the renderable, not
  the widget wrapper) — no change to this decision, just added confidence it's the right one.
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
- **[trip-wire, ihm_003, tier: revise, accepted — this changes what Mode 1 said]** The
  snapshot-level non-regression check does **not** belong in a new per-widget file. A matched
  institutional-memory hit (tier `revise`, dispositioned `accepted`) states plainly that every
  widget snapshot test in this project lives as a function inside the single
  `tests/snapshot_tests/test_snapshots.py` file, keyed to a snapshot app or example — there are no
  per-widget `test_<widget>.py` files under `tests/snapshot_tests/`, and a prior attempt to add one
  was explicitly rejected in favor of the single-file convention. Concretely: the three existing
  Sparkline snapshot checks are functions named `test_sparkline`, `test_sparkline_render`, and
  `test_sparkline_component_classes_colors` inside `test_snapshots.py` — re-verify those three
  functions unchanged for calls that don't opt into the new parameter; do not create a new
  snapshot-test file for this feature, and do not assume a snapshot test file is named after the
  widget.

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
- **Trip-wire coverage note:** 3 institutional-memory hits were surfaced for this aspect
  (`decision_ledger.py query`, all pre-dispositioned `accepted` — see
  `../decision-ledger-fixture/query-result.json` for the raw query output and
  `../decision-ledger-fixture/ledger.json` for the source entries, all clearly marked as fabricated
  fixtures constructed for this case study). Two (`ihm_001`, `ihm_002`) only corroborated decisions
  this spec would have reached anyway from the base package's own `context_items`/`scope`. One
  (`ihm_003`) materially changed the Testing Decisions section above — without it, this spec would
  have left the snapshot-test location unstated (as Mode 1, without the ledger, in fact did),
  leaving room for whoever implements this to independently guess a per-widget file path that
  doesn't exist in this project's actual layout.

---
`[Context: sparkline-baseline-marker_feature-add_20260724, content_hash: 62a9b119, human_approved: true, institutional_memory_hit_count: 3]`
