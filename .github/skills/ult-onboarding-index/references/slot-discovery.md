# Slot discovery — what to existence-check and how to resolve it

Read by Step 2 before running `onboarding_index.py discover`. Every path
here is resolved from the target repo's own `context-config.yaml`, falling
back to `layout-slots-registry.yaml`'s `workspace_root_leaf` default when
the project hasn't overridden a slot — the same resolution `ult-repo-layout`
performs when it sets up `context-config.yaml` in the first place. This
skill does not re-implement that resolution logic; it consumes its result.

## Registered slots (`project_layout.slots`, from `layout-slots-registry.yaml`)

| Slot id | Kind | Default path (`workspace_root_leaf`) | Link, don't re-enumerate |
|---|---|---|---|
| `compiled_guidelines` | file | `cache/project-guidelines/COMPILED-GUIDELINES.md` | — |
| `autoscaffold_content_index` | file | `cache/autoscaffold-content/CEP-INDEX.md` | Yes — it's already a router; link to it, don't restate its contents |
| `decision_ledger` | file | `cache/decision-ledger/DECISION-LEDGER.json` | Yes — it's JSON; link to it, don't parse or summarize entries |
| `context_packages` | directory | `contexts/` | — |
| `plans_output` | directory | `outputs/plans/` | — (no shipped producer today — see note below) |
| `brainstorm_output` | directory | `outputs/brainstorm/` | — (no shipped producer today) |
| `user_stories_output` | directory | `outputs/user-stories/` | — (no shipped producer today) |
| `security_docs` | directory | `outputs/security_docs/` | — (no shipped producer today) |
| `security_report` | directory | `outputs/security_report/` | — (no shipped producer today) |
| `project_plan_docs` | directory | `outputs/project_plan_docs/` | — (no shipped producer today) |

**On the "no shipped producer today" slots:** every producer named for
these six in `layout-slots-registry.yaml` is an `example-*` skill —
illustrative, not shipped in this library. In a typical run they will
existence-check `false`. Check them anyway: if a user later adds a real
producer skill, or hand-populates one of these directories, the next run of
this skill picks it up automatically with no code change here.

## Config-key paths (not registered slots — no marker file)

| Config key | Kind | Default path | Contents to glob |
|---|---|---|---|
| `how_dimension.how_l2.path` | directory | `inputs/org-conventions/` (project-specific — always resolve, don't assume the default) | `CODING-STANDARDS.md`, `TESTING-GUIDELINES.md`, `interfaces/*.md`, per-module `CONTEXT.md` files |

This is the same resolve-then-glob technique `compiling-project-guidelines`
Step 1 already uses for the same directory. `how_dimension.what_l2.path` and
`how_dimension.what_l1.path` are deliberately **not** existence-checked by
this skill — they hold requirements/spec content that
`compiling-project-guidelines` already folds into `COMPILED-GUIDELINES.md`
(the `compiled_guidelines` slot above), so checking them separately here
would just be a second, redundant path to the same information.

## Building `<path-to-your-table.json>` for Step 2

A flat JSON object, slot id → resolved absolute path (only the ten
registered slots above; the How-L2 glob is passed separately via
`--how-l2-path`):

```json
{
  "compiled_guidelines": "/abs/path/to/target-repo/cache/project-guidelines/COMPILED-GUIDELINES.md",
  "autoscaffold_content_index": "/abs/path/to/target-repo/cache/autoscaffold-content/CEP-INDEX.md",
  "decision_ledger": "/abs/path/to/target-repo/cache/decision-ledger/DECISION-LEDGER.json",
  "context_packages": "/abs/path/to/target-repo/contexts",
  "plans_output": "/abs/path/to/target-repo/outputs/plans",
  "brainstorm_output": "/abs/path/to/target-repo/outputs/brainstorm",
  "user_stories_output": "/abs/path/to/target-repo/outputs/user-stories",
  "security_docs": "/abs/path/to/target-repo/outputs/security_docs",
  "security_report": "/abs/path/to/target-repo/outputs/security_report",
  "project_plan_docs": "/abs/path/to/target-repo/outputs/project_plan_docs"
}
```

`onboarding_index.py discover` checks each path's existence (a directory
slot counts as present only if it contains at least one file — an empty
directory is not "content") and, if `--how-l2-path` is given, globs it for
the four How-L2 artifact kinds above.
