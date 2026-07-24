# Case Study: FastAPI + the OpenAPI Specification

```yaml
case: fastapi-response-links-parity
codebase: fastapi/fastapi, MIT, Python web framework; scoped to fastapi/ (890 KB) for this run
date_run: 2026-07-24
author: dogfooding run, context-engineering-oss
negative_control: false
```

This case pairs a real, unmodified external standard (the OpenAPI Specification, 3.1.0) with a
genuine ergonomics gap in how FastAPI itself implements two peer constructs from that same
standard. Because FastAPI is MIT-licensed, this case follows the permissive-license rule for
committing generated artifacts (see `EVIDENCE-METHODOLOGY.md`): the generated context package and
its `NOTICE.md` attribution are committed alongside this write-up.

## 1. Environment

FastAPI was cloned to a sibling directory (`dogfood-fastapi/`), pinned to tag `0.139.2` (commit
`866b7a3d0`). CEP scaffolding was applied via the canonical installer
(`context-engineering-oss/install.sh --target dogfood-fastapi --init-project`), then
`context-config.yaml` was hand-edited for FastAPI's real layout: What-L3 `path: fastapi/` (the
890 KB library itself, excluding the much larger `docs/`, `docs_src/`, and `tests/` trees). What-L2
`path: docs/en/docs/`. What-L1 enabled, `path: specs/external/`, `md_index_profile: generic`
(the OpenAPI Specification is itself authored in real Markdown, unlike RFC 6733's plaintext in the
Open5GS case — see §5 for what that changes). How-L2 `path: .`. Runtime: no live interactive coding
agent session — all steps run directly via `graphify` CLI, `md_index.py`, and manual
`content_hash.py`, with every normally human-answered step self-answered and flagged as simulated
(see §6).

The OpenAPI Specification (version 3.1.0, the exact version FastAPI's own
`openapi_version="3.1.0"` targets — confirmed via `fastapi/openapi/utils.py:527`) was fetched
directly from its canonical source, `github.com/OAI/OpenAPI-Specification`
(`versions/3.1.0.md`, Apache-2.0), and dropped into `specs/external/openapi-3.1.0.md` for
indexing.

## 2. Task

Add a first-class `links` parameter to the path-operation decorators (`@app.get`, `@app.post`,
`APIRouter` methods, etc.), so a developer can declare OpenAPI Link Objects the same direct way
they already declare OpenAPI callbacks via the existing `callbacks=` parameter — instead of only
being reachable through the generic `responses=` raw-dict override or `openapi_extra`.

This is a deliberate-gap task (D-012 methodology): `callbacks=` and `links` are peer constructs in
the OpenAPI spec's own Response/Components object family, but FastAPI gives one full first-class
parameter support and the other none — confirmed by grep against the real source before the task
was framed, not invented for the case study.

## 3. Source set

What-L3: `fastapi/` graphed via a single scoped `graphify update fastapi/ --no-cluster` run — 808
nodes / 2,568 edges. What-L2: `docs/en/docs/` searched directly (grep) — see §5's gap finding.
What-L1: the OpenAPI Specification (141 real headings, no conversion workaround needed — see §5)
indexed via `md_index.py index --profile generic` into `specs-out/index.json`. How-L2: repo root
`pyproject.toml` (ruff/mypy config) and `docs/en/docs/contributing.md`. No `discover`/
`confirm-layers` workflow was needed — layout was hand-confirmed against the real FastAPI tree up
front.

## 4. Package generation

`ult-context-generate`'s methodology (invoked manually, script-by-script, in this no-live-agent
run) produced a context package (`content_hash: 255b3b82`) with 9 context items across 5 aspects.
What-L3 hits: the `callbacks=` parameter's full build path as the working exemplar
(`fastapi/routing.py`'s per-decorator declarations; `fastapi/openapi/utils.py:323-339`'s recursive
expansion); confirmed absence of any `links=` parameter or build logic via grep; the real
integration point (`fastapi/openapi/utils.py:410-453`, the `deep_dict_update()` merge block); and a
`graphify affected` blast-radius check on `get_openapi_path()` (exactly two callers in the graphed
scope: `get_openapi()`, `FastAPI.openapi()`). What-L1 hits: the Link Object and Callback Object
sections of OpenAPI 3.1.0, cited by section title and line number. What-L2: zero `links=`
tutorial content in `docs/en/docs/` against a full, dedicated `openapi-callbacks.md` tutorial page
— a complete, expected gap.

## 5. Detected gaps, conflicts, staleness

No conflicts: What-L1 (the Link Object's own design-time-only, no-runtime-guarantee framing) and
What-L3 (the existing `responses=`/`deep_dict_update` merge point already accepts arbitrary
additional per-status-code fields) agree on the fix's scope and shape. Two gaps, both expected
rather than tooling misses: the missing `links=` parameter itself (a2 — the task's actual target)
and a complete What-L2 gap (a5 — a full callbacks tutorial exists with no links equivalent).

One real tooling observation surfaced during What-L1 setup, and it is a genuinely useful
*negative* result relative to PR2's Open5GS+RFC case: `DEF-002` (the RFC-editor-plaintext heading
detector gap) did **not** recur here, because the OpenAPI Specification's canonical source is
already real ATX Markdown — no conversion workaround was needed, and heading detection worked
correctly out of the box (141 real headings, first try). This corroborates PR2's own hypothesis
that `DEF-002` is specific to raw plaintext house styles (like RFC-editor `.txt`), not a general
Markdown-indexing defect. `DEF-003` (ranking favoring ancestor headings over descendants), by
contrast, **did** recur: querying `"Link Object"` against the now-correctly-indexed spec ranked the
target section 6th, behind four top-level ancestor chapters and one unrelated sibling — the same
workaround (direct lookup by the target section, bypassing the ranked query) applied. This is
useful corroborating evidence that `DEF-003` generalizes across both document styles tested so far,
as its original entry speculated. Neither observation is logged as a new defect; both are recorded
against the existing `DEF-002`/`DEF-003` entries in the governance-side defect log, not duplicated
here.

## 6. Approval decision

No live human reviewer was available (disposable dogfood clone). Step 1 scope clarification, the
Step 6 design decision (mirror `callbacks=`'s existing shape and call site exactly, rather than
only documenting the already-possible `responses=` workaround), and the Step 9-equivalent approval
were all self-answered by the operator running the tooling and are flagged as simulated in the
package's YAML — disclosed here rather than presented as genuine human-in-the-loop review.

## 7. Downstream use

The package was not handed to a downstream coding agent to actually implement the `links=`
parameter — this run stops at package generation, same as the Open5GS and Textual cases. This
measures the context-assembly step in isolation.

## 8. Outcome

**Inference, not measured:** the package correctly surfaced the exact working exemplar
(`callbacks=`'s full build path), the exact confirmed gap (`links` has no parameter, only a schema
type), the exact integration point in already-centralized response-building code
(`get_openapi_path()`'s `deep_dict_update` block), and the exact spec sections that bound the fix's
scope (the Link Object's design-time-only framing). Whether this is faster than a developer reading
`fastapi/openapi/utils.py` and `fastapi/openapi/models.py` directly and independently locating the
OpenAPI spec's Link Object section is a judgment call, not a controlled comparison — reported as
inference, not measured.

This case also strengthens the Open5GS case's own tentative conclusion about `DEF-002`/`DEF-003`
(§5): running the same What-L1 pipeline against a second, structurally different external
document (real Markdown vs. converted plaintext) isolated which defect was style-specific
(`DEF-002`) and which one generalizes (`DEF-003`) — exactly the kind of second-corpus comparison the
Open5GS case study's own §9 flagged as missing.

## 9. Limitations

Single-task, single-codebase, no-live-reviewer dogfood run, same caveats as the Open5GS and Textual
cases. No negative-control task was run for FastAPI in this pass (Stage 2 Plan requires at least one
ordinary task for this case; the negative control lives in the Textual case per its own
Success Criteria).

## 10. Lessons learned

CEP's gap/conflict checks and `graphify affected` blast-radius check behaved correctly for a
mixed framework/docs/tests codebase, once scoped to the actual library subtree
(`fastapi/`). The second What-L1 run against a real external spec — this time genuine Markdown
rather than converted plaintext — cleanly resolved the open question from the Open5GS case about
whether `DEF-002` was plaintext-specific (confirmed: yes) while corroborating that `DEF-003` is not
(confirmed: it recurs against a structurally different, well-formed document too).

## Reproduction steps

1. Clone the pinned corpus: `git clone https://github.com/fastapi/fastapi.git dogfood-fastapi &&
   cd dogfood-fastapi && git checkout 0.139.2` (commit `866b7a3d0`).
2. Apply this repo's CEP scaffolding via the canonical installer:
   `./install.sh --target dogfood-fastapi --init-project`, then hand-edit `context-config.yaml`
   per §1 above.
3. Fetch the OpenAPI Specification directly from its canonical source:
   `curl -sSL -o specs/external/openapi-3.1.0.md
   https://raw.githubusercontent.com/OAI/OpenAPI-Specification/main/versions/3.1.0.md` — no
   markdown-ification workaround needed (see `DEF-002`'s corroborating negative result, §5).
4. Build the What-L1 index: `python .github/skills/ult-context-generate/scripts/md_index.py index
   specs/external/ -o specs-out/index.json --profile generic`. Expect "Indexed 1 file(s), 141
   heading(s)".
5. Build the What-L3 graph: `graphify update fastapi/ --no-cluster`. Expect 808 nodes / 2,568
   edges.
6. Confirm the task's gap and exemplar directly:
   `grep -rn "callbacks:" fastapi/routing.py | head -3` (exemplar, many hits) and
   `grep -rn "Link(\|\.links\b" fastapi/*.py fastapi/openapi/*.py` (gap — only
   `fastapi/openapi/models.py` matches).
7. Confirm the blast radius: `graphify affected "get_openapi_path" --graph
   fastapi/graphify-out/graph.json` — expect exactly two callers (`get_openapi()`,
   `FastAPI.openapi()`).
8. Look up the OpenAPI spec's "Link Object" section directly by heading title in
   `specs-out/index.json` (not via `query`, per `DEF-003`'s corroborated recurrence) to confirm its
   `section_bounds` and read the Link Object definition at that line range.
9. Compare your package's `content_hash` against this case's recorded value
   (`response-links-openapi_feature-add_20260724.yaml`: `255b3b82`) by running
   `python .github/skills/ult-context-generate/scripts/content_hash.py contexts/<id>.yaml`.
