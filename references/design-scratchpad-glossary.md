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

## Decisions (D1–D24)

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
| D24 | Browser onboarding wizard — a local, user-launched, on-demand status/setup tool (`ult-cep-wizard`) that reads already-resolved `ult-repo-layout` state through labeled boxes and a directory picker, with a gated write path (stage/apply/discover) for committing layout decisions. See §18. `ult-autoscaffold-content` (Q-a's resolved name, `.github/skills/ult-autoscaffold-content/`) is the real What-L2/How-L2 content-generation skill the wizard's What/How boxes hand off to — Phase A (single-overview-file, empty-target case), Phase B (large-repo triage/tiering, resume/checkpoint), Phase C (optional, user-supplied domain-pack consumption; OSS ships zero built-in packs), and Phase D (wizard integration — What/How stub cards point at running this skill by name, mirroring `guidelines_card()`; CI wiring; Radisys-scrub gate extended to cover this skill's own directory) are all shipped as of 2026-08-13. Phase 3 (CLI status view, §18.11) is next. See `D24-WIZARD-REMAINING-WORK.md` for the phase sequence. |

## Sections (§14–§18)

| Section | Title | Notable subsections cited elsewhere |
| --- | --- | --- |
| §14 | Readiness for OSS release | — |
| §15 | Project layout and path-dependency configuration (D20) | §15.2 slot registry scope; §15.3 `.layout-slots.yaml` marker format; §15.5 path resolution algorithm; §15.6 `layout.on_missing_write_path`; §15.7 `ult-repo-layout` init/reconcile/discover modes |
| §16 | Workspace-root consolidation (D21) | §16.2 `layout.workspace_root` config key and resolution precedence; §16.4 slot-default re-rooting; §16.5 What-L2 redefinition (corpus root = workspace root); §16.6 scaffold-not-copy; §16.7 SDLC-directory remapping and `what_l2.include_roots`; §16.8 `layout-slots-registry.yaml` |
| §17 | Layer-path discovery for brownfield adoption (D23) | §17.1 why a parallel mechanism, not a slot fold-in; §17.2 the `discover` layer-discovery phase; §17.3 the `context-layout-discovery.md` artifact; §17.4 per-layer discovery heuristics; §17.5 `confirm-layers` commit step; §17.6 drift detection |
| §18 | Browser onboarding wizard (D24) | §18.1 the four labeled boxes (What/How/Guidelines/Trip-wire) and journeys converging on them; §18.2 thin local server, not hosted/persistent, ROADMAP carve-out; §18.2b path-containment and write-path security model; §18.3 two-source read model (marker-derived slots + layer keys), fresh-per-request; §18.4 what's ported vs. dropped from the internal `ult-scaffold-repo` source; §18.6 content-generation handoff modes (agent-writes-in-place / paste-back); §18.7 server-rendered picker, no drag-and-drop; §18.9 open questions closed (Q-a naming, Q-f front-door stance, Q-g Radisys-scrub gate); §18.10 phased rollout and Phase 0 exit criteria |

`ult-repo-layout/SKILL.md`'s own "Path resolution algorithm (§15.5 + §16.2)" section is this repo's
real implementation of the two rows above with matching numbers — that heading is the actual
target, not a further pointer.
