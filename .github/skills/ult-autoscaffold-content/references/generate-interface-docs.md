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

Evidence gathering for this kind is governed by
`references/evidence-probes.md#interface_boundary` — read it before
filling the template; it names which fields the interface entry itself
already grounds versus which fields need a real call site or ownership
file, and the exact `[src: path#Lx-Ly]` / `Not evidenced. Searched: ...
(absent).` reporting format every section must use.

Open `templates/interface-boundary-template.md` and fill in, following
that template's own per-section evidence comments:

- **`module_a` / `module_b`**: from the interface entry, verbatim.
- **Relations observed**: the `relations` and `weight` fields, stated as
  what they are — a count of graph-observed dependency edges, not a claim
  about the interface's actual API surface.
- **Contract**: cite an actual import/include statement or call
  expression connecting the two modules. Use `evidence_hints.call_sites`
  when the packet has populated it (from `list-interfaces --with-sites`);
  otherwise inspect each module's own source directly for the concrete
  site.
- **Everything else** (versioning policy, deprecation policy, owners): a
  dependency-graph edge cannot evidence any of this — it only proves
  *that* two modules are coupled, not *how*. Where no CODEOWNERS/
  MAINTAINERS file or explicit deprecation marker exists, the field gets
  the honest gap line, never a guess. Do not infer a contract shape from
  either module's name or from general conventions; that would be exactly
  the kind of confident-but-ungrounded claim this skill's honesty standard
  (`SKILL.md` Step 5) exists to avoid.

## 3. Write and record

Write the filled template to
`<how_l2_path>/interfaces/<module-a>-to-<module-b>.md`. Then:

- **Wrote it:** `scaffold_state.py mark-interface-generated <state.json>
  <interface-id> --output <path>`.
- **Pair not eligible yet, or user declined:** `scaffold_state.py
  mark-interface-deferred <state.json> <interface-id> --reason <text>` —
  e.g. `"endpoint utils/ not generated this run"` for the not-yet-eligible
  case, or the user's stated reason for a decline.
