# Layer-path discovery and confirmation (D23 §17.2-§17.6)

**Distinct from the 8-slot `discover` mode in `SKILL.md`**, which guesses
`project_layout.slots` entries by content signature. This is a separate,
two-step mechanism for the four layer paths that §17.1 deliberately excludes
from `project_layout.slots` (`layers.what_l2`, `layers.what_l1`,
`how_dimension.how_l2`, `how_dimension.how_l1` — no content-signature marker,
legitimately absent/opt-in, multi-root by nature): `discover_layers.py`
proposes, `confirm_layers.py` commits.

## `discover` — layer-path discovery phase (D23 §17.2-§17.4)

Run it with:

```
python scripts/discover_layers.py <repo_root>
```

For each layer it proposes one of three shapes, per §17.4's escalation
matrix:

- **Shape 2a (NOTICE-only)** — the layer's path already resolves (hand-set or
  CEP default) and has content. Nothing to decide; the artifact records this
  as a `NOTICE:` line and stops there.
- **Shape 2b (hand-configured precedence)** — an explicit, non-default `path`
  is already set and has content. Discovery never re-scores or challenges it.
- **PENDING decision line(s)** — no populated default exists: What-L2 scans
  every top-level sibling directory for §17.4's category signals
  (Requirements/Design/API-spec name or content match) and proposes the best
  match as `decision: PENDING   # CONFIRM: <path> | CUSTOM: <path> | SKIP`;
  every other categorized sibling becomes an
  `include_roots_decision: PENDING   # ADD: <path> | SKIP` proposal on the
  same What-L2 section, since a repo can have more than one legitimate
  content root. How-L2 uses its own fixed candidate-directory list plus a
  root-signal fallback. What-L1/How-L1 are opt-in (`enabled: true` required)
  and only ever propose a decision once enabled.
- When `layout.workspace_root` is set, a non-CEP-bucket subdirectory inside it
  that looks vendor/generated (many files, no human-authored docs) is
  proposed as `exclude_decision: PENDING   # ADD: <path> | SKIP` instead of an
  `include_roots` candidate.
- A cross-layer collision check flags — but never blocks — two layers
  whose resolved or candidate paths are equal or nested, as a
  `collision_decision: PENDING   # CUSTOM: <dotted.path> -> <new path> |
  ACKNOWLEDGE` line.

The artifact is written to `context-layout-discovery.md`
(`{workspace_root}/` if set, else the repo root). Nothing here mutates
`context-config.yaml` — that's `confirm-layers`' job, next.

## `confirm-layers` — commit layer-path decisions (D23 §17.5-§17.6)

Reads `context-layout-discovery.md` and validates every decision-bearing
line's edited value against its own trailing comment before writing anything.
Run with:

```
python scripts/confirm_layers.py <repo_root>
```

- **Comment-as-grammar (edit only the value, never the comment):** each line
  looks like `decision: PENDING   # CONFIRM: docs/api/ | CUSTOM: <path> |
  SKIP`. Replace `PENDING` with one of the offered verbs — a bare verb that
  already has a value attached in the comment (`CONFIRM`, `ADD`) reuses that
  value automatically; `CUSTOM` has no real default (only a `<...>`
  placeholder) and always needs an explicit `CUSTOM: <your/path/>` edit. The
  comment itself must stay untouched — it is not free-text help, it's parsed.
- **Refuse-on-`PENDING`/invalid-verb, no partial write:** if any line is still
  `PENDING`, uses a verb its own comment doesn't offer, or leaves a `<...>`
  placeholder unfilled, `confirm-layers` prints every such error and writes
  nothing to `context-config.yaml` — never a partial apply.
- On success, each resolved `decision`/`include_roots_decision`/
  `exclude_decision`/`collision_decision` line is written into
  `context-config.yaml` (`SKIP`/`ACKNOWLEDGE` write nothing — there's no path
  to record), and the artifact line itself is stamped
  `# CONFIRMED <timestamp>` in place of the grammar comment.
- **§17.6 drift tracking:** a later `discover` run never re-litigates a
  section that was fully confirmed last time — it carries the stamped section
  forward unchanged, *unless* something it recorded has genuinely
  disappeared:
  - A confirmed primary `CONFIRM`/`CUSTOM` path no longer exists or is empty
    → the carried-forward section stays, plus a dated
    `## Re-discovery - <layer> - <date>` section with a fresh proposal for
    the whole layer.
  - Otherwise, an individually-confirmed `include_roots`/`exclude` candidate
    (an `ADD`) no longer exists or is empty → the carried-forward section
    stays untouched, plus a narrower dated
    `## Re-discovery - <layer> - candidates - <date>` section naming only
    that candidate — every other already-confirmed candidate in the same
    layer is left alone.
  - Both still fine → no new section at all; re-running `discover` is a
    no-op.
