# Contributing to the Context Engineering Protocol

## Before you start

This is a personal, single-maintainer project — there's no separate access
token or internal tooling to set up. Fork the repo, make your change on a
branch, and open a pull request on GitHub.

## Frontmatter requirements

Every skill's `SKILL.md` needs valid frontmatter. Full example:

```yaml
---
name: context-generate
description: Assemble a source-attributed, human-approved context package before a downstream generation task runs (min 20 chars). Do NOT use for simple one-file lookups.
namespace: ult
version: 0.1.0
origin: ground-up
author: Your Name
maintainer: Your Name
adapted_from: ~
upstream_version: ~
released: 2026-07-06
tags: [context, provenance, gap-detection]
bundle: utilities
tier: draft
---
```

### Provenance fields explained

| Field | Required | Values | Purpose |
|---|---|---|---|
| `origin` | Yes | `ground-up` / `adapted` / `adapted-extended` | Where this artifact came from |
| `author` | Yes | Full name | Who wrote or adapted it |
| `maintainer` | No | Name | Defaults to the repo owner if omitted |
| `adapted_from` | Yes | Upstream project name + version, or `~` for ground-up | Enables upgrade detection and feeds `NOTICE` |
| `upstream_version` | Yes | Semver string, or `~` for ground-up | Version of upstream at time of adaptation |
| `released` | Yes | `YYYY-MM-DD` | First release into this repo |

If you set `adapted_from` to anything other than `~`, run
`python catalog/generate_notice.py --write` before opening your PR — it
regenerates `NOTICE`'s "Adapted content" section from every skill's
frontmatter, so that file never has to be hand-edited (and CI checks it
stays in sync — see below).

### Version numbering convention

- `0.1.0` — new contribution or first adaptation of external material
- `1.0.0` — adapted from a mature, stable upstream project
- Increment `MINOR` for meaningful extensions or improvements
- Increment `PATCH` for fixes, wording corrections, typo repairs

`namespace` should match one already in use in this repo (`ult`, `demo`)
unless your contribution genuinely doesn't fit either — new namespaces are
fine, just make the choice a meaningful one.

## Skill quality standards

These aren't CI-enforced yet (porting a full frontmatter/body linter is
open future work — see the project backlog), so they're reviewed by hand on
every PR rather than blocking a merge. New contributions should meet all of
them:

- **Body size.** Keep the `SKILL.md` body under **1,500 words** where
  possible — that's roughly the point where co-loading this skill alongside
  several others starts costing real context budget. **5,000 words is a
  hard ceiling** if there is no `references/` directory: move procedural
  detail, schema examples, and "read once then execute" scripts into
  `references/*.md`, and have the body point to them with "read
  `references/X.md` now" instructions. See `ult-context-generate` for a
  worked example of this pattern.
- **Description quality.** At least 40 characters, and must include a
  "when NOT to use this" signal (e.g. "Do NOT use for X — see Y instead").
  The negative clause is as important as the positive one for routing —
  without it, agents will fire your skill on inputs it was never meant to
  handle. The whole `description` field is capped at 200 characters total —
  write tight.
- **`tier` field.** Every skill should declare `tier: read | draft | act`
  in its frontmatter. Ask: does this skill's own workflow have an explicit,
  blocking "stop until a human approves" gate (or is it a meta-skill that
  authors/edits other skills, which always enters at `draft` regardless of
  confidence)? → `draft`. Does it take direct action (file writes, git
  operations, subagent dispatch, code changes) or produce a finished
  deliverable without such a gate? → `act`. No artifact/action consequence
  (pure analysis, reference, behavioral guidance)? → `read`.

## Evaluation cases (EDD — write these alongside your skill, not after)

Every skill should ship with at least **3 eval cases** in
`evals/<skill-name>.eval.json` — minimum 2 positive (input that should
trigger your skill) and 1 negative (input that looks similar but should NOT
trigger it, usually tied to your description's "Do NOT use for..." clause).
Copy `evals/template.json` to start.

Why before/alongside rather than after: writing the negative case forces
you to actually think through what your skill should *not* fire on —
exactly the gap that causes false-positive routing in production. If you
can't write a negative case, your description's negative clause is
probably too vague.

`catalog/check_eval_triggers.py` runs in CI against every
`evals/*.eval.json` — a zero-LLM-cost, deterministic keyword-overlap check
(not a real model-based eval, but free and catches the most common trigger
failures): positive cases must share enough vocabulary with your skill's
`description`/`tags` to plausibly route there; negative cases must NOT. A
failure here usually means either your eval input is unrealistic, or your
description's vocabulary doesn't actually cover the use case you're
claiming — both are worth fixing before merging.

## Review

There's one maintainer and no auto-merge tier yet — every PR gets a human
look before merging. CI must pass: both skills' test suites, the eval
trigger check, and the `NOTICE` freshness check (see
`.github/workflows/ci.yml`).
