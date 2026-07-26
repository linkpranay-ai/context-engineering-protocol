# Design scratchpad glossary

Several skill files, scripts, and config files in this repo carry citations like `(D14)`,
`D20 §15.5`, or `CONTEXT-ENGINEERING-DESIGN.md D11`. These point at an internal build-time
scratchpad document used while designing this protocol — it was never part of this repo, isn't
published, and isn't going to be. The scratchpad itself doesn't matter; what matters is that none
of those citations should be a dead end for a reader of this repo. This file is that resolution:
a plain-English index of what each cited decision (`D<N>`) or section (`§<N>`) actually is, so the
citation makes sense without the source document.

Nothing here reproduces the scratchpad's actual content — each entry is the one-line gist, same
level of detail the citing file itself already implies.

## Decisions (D1–D23)

| ID | What it decided |
| --- | --- |
| D1 | Use `graphify` for all What-dimension layers — no new graph infrastructure. |
| D2 | What-L1 is a fallback, not a foundation. |
| D3 | Human review is mandatory, not optional. |
| D4 | Source attribution on every context item. |
| D5 | Context packages are cached and reused. |
| D6 | Budget-bounded queries. |
| D7 | L2 vs. L3 contradictions are surfaced, not silently resolved. |
| D8 | Complete gaps surface to the user; LLM suggestion is the fallback of last resort. |
| D9 | Context-grounded generation is the floor; domain knowledge raises the ceiling. |
| D10 | Blast-radius analysis is a mandatory What-L3 sub-step for all features (new and enhancement). |
| D11 | Constraints is a third context dimension; `compiling-project-guidelines` is its compiler. |
| D12 | Actor identification and Jira-ready backlog shaping in `spw-write-user-story`. |
| D13 | What-L1 pilot uses direct-file-read, not a `graphify` graph; synonym-expanded keyword matching closes terminology gaps. |
| D14 | Markdown-AST heading-tree bounding + single-hop regex citation-following in the fallback-query step. |
| D15 | Aspect-level gap detection; What-L2 corpus-size auto-indexing; disclosed LLM-training-knowledge fallback. |
| D16 | Query-result corroboration; explain→affected leaf-node pivot. |
| D17 | Stable `aspect_id` as the cross-step join key (refines D15). |
| D18 | Opt-in web fallback before raising an open question (refines D15's fallback-query step). |
| D19 | Context-package traceability tags: two-route consumption model, hash-pinned multi-package tags, Jira-embedded propagation. ("D19 v2" is a later revision of the same decision.) |
| D20 | Project layout and path-dependency configuration — the `ult-repo-layout` slot registry. See §15. |
| D21 | Workspace-root consolidation — the `layout.workspace_root` config key, scaffold-not-copy, four-bucket layout. See §16. |
| D22 | Multi-root What-L2 — a deferred follow-on, not yet implemented. |
| D23 | Layer-path discovery for brownfield adoption — the `discover`/`confirm-layers` phases. See §17. |

## Sections (§14–§17)

| Section | Title | Notable subsections cited elsewhere |
| --- | --- | --- |
| §14 | Readiness for OSS release | — |
| §15 | Project layout and path-dependency configuration (D20) | §15.2 slot registry scope; §15.3 `.layout-slots.yaml` marker format; §15.5 path resolution algorithm; §15.6 `layout.on_missing_write_path`; §15.7 `ult-repo-layout` init/reconcile/discover modes |
| §16 | Workspace-root consolidation (D21) | §16.2 `layout.workspace_root` config key and resolution precedence; §16.4 slot-default re-rooting; §16.5 What-L2 redefinition (corpus root = workspace root); §16.6 scaffold-not-copy; §16.7 SDLC-directory remapping and `what_l2.include_roots`; §16.8 `layout-slots-registry.yaml` |
| §17 | Layer-path discovery for brownfield adoption (D23) | §17.1 why a parallel mechanism, not a slot fold-in; §17.2 the `discover` layer-discovery phase; §17.3 the `context-layout-discovery.md` artifact; §17.4 per-layer discovery heuristics; §17.5 `confirm-layers` commit step; §17.6 drift detection |

`ult-repo-layout/SKILL.md`'s own "Path resolution algorithm (§15.5 + §16.2)" section is this repo's
real implementation of the two rows above with matching numbers — that heading is the actual
target, not a further pointer.
