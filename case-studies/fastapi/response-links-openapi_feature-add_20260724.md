# Context package: response-links-openapi_feature-add_20260724

**Task:** Add a first-class `links` parameter to the path-operation
decorators, so a developer can declare OpenAPI Link Objects the same direct
way they already declare callbacks via `callbacks=` — instead of only being
reachable through the generic `responses=` raw-dict override.

## Summary

- What-L3: `callbacks=` is a fully-wired first-class parameter — declared on
  every path-operation method, threaded onto `APIRoute.callbacks`, and
  expanded into nested OpenAPI objects inside `get_openapi_path()`
  (`fastapi/openapi/utils.py:323-339`).
- What-L3: `links` exists only in the pydantic OpenAPI schema/validation
  layer (`fastapi/openapi/models.py`) — no route-decorator parameter, no
  build logic anywhere else in the codebase, confirmed by grep.
- What-L3: the real integration point is `fastapi/openapi/utils.py:410-453`,
  the block that already `deep_dict_update()`s a `responses=` override into
  each generated response — this is where a first-class `links=` parameter's
  built dict would need to merge in, before the user's own override.
- What-L1: OpenAPI 3.1.0's Link Object (§"Link Object") is explicitly a
  design-time construct, no runtime invocation guarantee — bounds the fix to
  declarative metadata, not runtime link-following.
- What-L2: a full dedicated tutorial page and example exist for callbacks;
  zero equivalent for links — confirmed complete gap.
- No conflicts detected.
- Decision (self-resolved, no live user available in this dogfood run):
  mirror `callbacks=`'s existing shape and call site exactly, rather than
  only documenting the already-possible `responses=` workaround.

## Conflicts

None detected.

## Gaps

- **a2 — Link Object has no dedicated parameter:** the deliberate task
  target — confirmed by grep across `fastapi/*.py` and `fastapi/openapi/*.py`.
- **a5 — Docs have no links tutorial/example:** complete What-L2 gap; a full
  callbacks tutorial page exists with no equivalent.

## Non-regression risks (blast radius, via `graphify affected`)

- `get_openapi_path()` (`fastapi/openapi/utils.py:260`) — exactly two callers
  in the graphed scope (`get_openapi()`, `FastAPI.openapi()`); no other blast
  radius (depth 2).
- The new `links=` build logic must run before the existing
  `if route.responses:` `deep_dict_update` block, so a user's own manual
  override still wins.
- `callbacks=`'s own build path must stay untouched — this fix is additive,
  not a refactor of the exemplar.

## Note on this run

This context package is part of the FastAPI case study, a dogfood run of
`ult-context-generate` against a pinned clone of FastAPI (tag `0.139.2`)
plus the real OpenAPI Specification (3.1.0, Apache-2.0) dropped in as an
external What-L1 source, with no live interactive user available mid-run.
All normally human-answered steps (scope clarification, gap handling, open
questions, approval) were self-answered and are flagged as simulated in the
YAML package above.

One tooling observation corroborated from the Open5GS+RFC case study: the
same section-ranking bias observed there (ancestor headings outranking more
specific descendants when querying `md_index.py`) reproduced here too,
against a real, well-formed Markdown spec rather than converted RFC
plaintext.
