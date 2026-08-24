# Generating interface-boundary docs

Read by Step 5d — graph-mode large-repo runs only. Produces one file per
crossing-module pair: `<how_l2_path>/interfaces/<module-a>-to-<module-b>.md`.

## 1. Find the eligible pairs

```
scaffold_state.py list-interfaces <state.json> --eligible-only
```

This prints only pairs where `status` is still `pending` and both endpoint
modules already have `status: generated` in this same state (Step 5b must
reach both endpoints before their interface doc is eligible). Each entry
carries `id` (`<module_a>--<module_b>`), `module_a`, `module_b`,
`relations` (the sorted set of dependency-relation kinds observed —
`imports`, `imports_from`, `calls`), and `weight` (how many qualifying
graph edges were observed between the pair, both directions combined).

Present the list to the user; let them pick which eligible pairs to cover
now versus leave for a later run.

## 2. Fill the template — grounded facts only

Open `templates/interface-boundary-template.md` and fill in:

- **`module_a` / `module_b`**: from the interface entry, verbatim.
- **Relations observed**: the `relations` and `weight` fields, stated as
  what they are — a count of graph-observed dependency edges, not a claim
  about the interface's actual API surface.
- **Everything else** (API shape, request/response contract, versioning
  policy, deprecation policy): a dependency-graph edge cannot evidence any
  of this — it only proves *that* two modules are coupled, not *how*. Every
  one of these fields is `TBD — fill in` in the generated file. Do not
  infer a contract shape from either module's name or from general
  conventions; that would be exactly the kind of confident-but-ungrounded
  claim this skill's honesty standard (`SKILL.md` Step 5) exists to avoid.

## 3. Write and record

Write the filled template to
`<how_l2_path>/interfaces/<module-a>-to-<module-b>.md`. Then:

- **Wrote it:** `scaffold_state.py mark-interface-generated <state.json>
  <interface-id> --output <path>`.
- **Pair not eligible yet, or user declined:** `scaffold_state.py
  mark-interface-deferred <state.json> <interface-id> --reason <text>` —
  e.g. `"endpoint utils/ not generated this run"` for the not-yet-eligible
  case, or the user's stated reason for a decline.
