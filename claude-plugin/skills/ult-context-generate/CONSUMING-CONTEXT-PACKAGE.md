# How a consuming skill should consume an approved context package

> **Status: piloting** — this contract is the general "any skill or tool"
> consumption story for context packages, independent of any specific
> downstream skill set. `demo-consume-context` is a small, from-scratch
> worked example that exercises it end-to-end. Any skill whose job is to
> produce an artifact for a specific feature (a design, a plan, test cases, a
> code review, a debug session, ...) is a candidate consumer.
>
> **D19 v2 additions (newest pilot surface):** step 0 (tag discovery —
> existence/hash/supersession checks against `<package-id>@<hash8>` tags) and
> step 9 (tag emission + reverse-index addenda) are the traceability-tag
> half of this contract. Item-level `[Context: ...]` tags (step 0 looks for
> these) are produced by whichever skill pushes individually-addressable
> sub-units to an external tracker — none of the skills in this repo do that
> today, so item-level tags are N/A here; every consuming skill still reads
> them when present (step 0) and writes its own document-level/attribution
> tags (step 9).
>
> **Path resolution (D20 Phase 1 + D21 Phase 3a):** `contexts/` throughout
> this document is the `context_packages` path-slot — resolve it the same way
> `ult-context-generate/SKILL.md`'s Config reference section does (its
> "`context_packages` (D20 §15.5, D21 §16.2)" note), and substitute that
> resolved path everywhere `contexts/` appears below. Projects with neither
> `project_layout`, `cache.product_context_path`, nor `layout.workspace_root`
> set are unaffected — `contexts/` remains the default.
>
> **Institutional-memory hits (added 2026-08-06):** `institutional_memory_hits[]`
> (§7 in `PROTOCOL.md`, trip-wire) has been part of the context package schema
> since it shipped, but this contract never told a consuming skill to actually
> read it — meaning the "surfaced for free once it rides in the package" benefit
> the schema implies wasn't real for any skill that only follows this contract.
> Step 3 below now says so explicitly. Gap found during the `ult-cep-retrofit`
> design review, fixed here rather than deferred.
>
> **Context-availability policy (added 2026-08-31, the 2026-08-31 Round-2
> evaluation's finding on context-availability policy handling during
> retrofit drafting):** step 1's "Not found" branch used to say "proceed exactly as you
> normally would" unconditionally — a task-oriented skill (e.g. `implement`)
> could then complete real work ungrounded, with the only disclosure arriving
> in step 8's end-of-work attribution line, too late for the user to choose
> otherwise. Every consuming skill now declares one of three policies —
> retrofitted skills set this per-unit in `ult-cep-wizard`'s retrofit picker
> (persisted as `context_availability` alongside that unit's contract
> selection); a hand-authored consuming skill states its policy next to its
> one-line pointer to this file:
>
> - **`ask`** — the recommended default for implementation, design, planning,
>   review, and debugging skills. Step 1 below asks before proceeding.
> - **`required`** — for high-risk or governed skills. Step 1 below is
>   written to stop until an approved package is supplied or generated,
>   rather than proceed ungrounded.
> - **`optional`** — preserves the original lightweight behavior (proceed
>   silently), but step 1 below now announces the absence up front instead of
>   only in step 8's attribution line, so silence is never the only signal.
>
> A skill with no declared policy at all (pre-2026-08-31 content, or a
> hand-authored skill that hasn't adopted this) behaves exactly as `optional`
> did before this addition — this callout changes nothing for it beyond
> requiring the up-front announcement.
>
> **This is a recorded decision, not an enforced one.** The policy line
> tells a consuming skill what its own step 1 should do; nothing in this
> file, the context-package schema, or `ult-cep-wizard` verifies that a
> given execution actually reached and honored step 1 before doing real
> work. A `required` unit that's driven by something other than this
> contract's own step-by-step instructions (a differently-prompted agent, a
> shortcut invocation) is not mechanically stopped — the guarantee here is
> "the decision is written down and machine-readable," not "the decision is
> enforced." Treat any doc that implies otherwise as overstating this.

Any skill that is asked to work on a specific feature (brainstorm a design,
write a plan, write test cases, review code, debug an issue, etc.) should
follow this before doing that work:

0. **Tag discovery (D19 v2)** — before falling back to the glob check in step
   1, scan whatever artifact(s) you were handed (a pasted user story, a Jira
   description, a file on disk, etc.) for a `**Context package(s):**` header
   line and/or `[Context: ...]` item-level tags. Each tag holds one or more
   `<package-id>@<hash8>` references, `;`-separated if there's more than one
   (C3/C4 — a story can draw on multiple packages).

   For each distinct `<package-id>@<hash8>` found:
   - **Existence check (C7):** if `contexts/<package-id>.yaml` doesn't exist,
     print: `"Warning: tagged context package '<package-id>' not found at
     contexts/<package-id>.yaml — proceeding without it for this package."`
     and drop it from the resolved set. (If a multi-package tag named several
     packages, the others still resolve independently.)
   - **Hash check (C1):** compare the tag's `<hash8>` against the resolved
     package's current `content_hash` field — a plain field read, no
     recomputation. On mismatch (non-blocking): `"Note: tagged context
     package '<package-id>' has changed since this tag was minted (hash
     <hash8> -> <current-hash8>). Proceeding with current content; the
     freshness spot-check (steps 4-5) will flag any contradicted decisions."`
     If the package predates D19 v2 and has no `content_hash` field at all,
     the hash check cannot run — proceed silently (this reflects the
     package's age, not drift; it gets a `content_hash` the next time it's
     regenerated, fold-addenda'd, or domain-enriched, per the two-pass save
     in `ult-context-generate/SKILL.md`).
   - **Supersession check (C5):** scan the package's sibling
     `contexts/<package-id>_<date>.addenda.yaml` (if any) for an entry with
     `kind: supersession`. If found (non-blocking): `"Note: '<package-id>'
     was superseded by '<superseded_by>' on <added_at> — consider checking
     the newer package too."` Do not auto-switch to the superseding package.

   Every package that survives the existence check becomes a "Found" package
   for step 2 onward — **regardless of its own `task_type`** (a tag minted for
   one task type is still useful context for a related one — e.g. a
   design-note package can inform a later test-planning task).
   Merge (dedupe by `<package-id>`) with whatever step 1's glob check also
   finds.

   If no input artifact was provided, or none of it carried a recognizable
   tag, this step finds nothing — fall through to step 1's glob check as
   today.

1. **Check** whether `contexts/` contains a file matching
   `<feature-slug>_<task-type>_*.yaml` for the feature/task at hand, with a
   non-empty `approved_by`. Also check for a sibling
   `<feature-slug>_<task-type>_*.addenda.yaml`. This glob check is the
   fallback path used when step 0 found no tagged packages.
   - **Found:** continue to step 2.
   - **Not found:** branch on this skill's declared context-availability
     policy (see the "Context-availability policy" callout above; treat an
     undeclared policy as `optional`):
     - **`ask`:** ask the user, verbatim:
       > No approved CEP context package was found for `<feature>` /
       > `<task type>`. Generate one now, continue without CEP context, or
       > provide an existing package?
       - *Generate one now:* hand off to `/ult-context-generate` for
         `<feature>`/`<task type>` — do **not** run it yourself inline, package
         generation stays a human-approved process. Once an approved package
         exists (or the handoff is declined), resume this skill at step 1 and
         re-check.
       - *Continue without CEP context:* proceed as the `optional` branch
         below does, then continue to step 2.
       - *Provide an existing package:* have the user point to the file:
         confirm it matches `<feature-slug>_<task-type>_*.yaml` with a
         non-empty `approved_by`, then treat it as **Found** and continue to
         step 2. If it doesn't qualify, return to the top of this branch.
     - **`required`:** stop. State that this skill requires an approved CEP
       context package for `<feature>`/`<task type>` and none was found; do
       not proceed with the work. Direct the user to `/ult-context-generate`
       or to supply an existing approved package, then re-check step 1 —
       never fall through to normal work ungrounded.
     - **`optional`:** announce up front — e.g. "No approved CEP context
       package found for `<feature>`/`<task type>` — proceeding without it."
       — then proceed exactly as you normally would: consult the code graph
       if `CONSUMING-CODE-GRAPH.md` applies, apply compiled guidelines if
       `CONSUMING-COMPILED-GUIDELINES.md` applies. Don't auto-run
       `/ult-context-generate`; that remains a human-initiated step. Continue
       to step 2.

   None of these branches ever auto-run `/ult-context-generate` on their own
   initiative — generation is only ever a human-approved handoff, triggered by
   an explicit user choice (`ask`) or an explicit user direction (`required`).

2. **Confirm with the user**, in one line:
   > "Found a context package for this feature (`<id>`, generated `<date>`,
   > approved[, `<N>` addenda]) — use it as primary context for this
   > work?"

3. **Load it as primary context.** Read the package's `decisions_log` /
   `decisions`, `context_items`, `gaps_detected`, `institutional_memory_hits`,
   `non_regression_risks`, and `summary`. If a sibling `.addenda.yaml` exists, load its entries too —
   **latest `added_at` first**. When a package exists, codegraph and
   compiled-guidelines checks become **narrow/targeted** (the freshness
   spot-check below, plus targeted lookups for genuinely new topics) rather
   than a second full pass.

   **What-L1 fallback items:** any `context_items` entry with
   `what_l1_fallback: true` is an external-reference suggestion (Step 7.1,
   D2/D13 in `ult-context-generate/SKILL.md`) that already passed the mandatory
   human review gate at generation time — but it carries lower confidence than
   What-L2/L3 items, since it describes what an external spec says, not what
   this product does or requires. If the work at hand touches that item's
   topic, flag it distinctly to the user (e.g. "this package includes an
   external-reference suggestion for `<topic>`, sourced from `<source>` — treat
   as informative, not authoritative, for this product").

   **Web fallback items (D18):** a `context_items` entry with
   `what_l1_fallback: true` and a `source` of the form
   `web_search(<query>) retrieved_at: <ISO timestamp>` is a live web-search
   result (Step 7.1 step 5a, opt-in via `what_l1.allow_web_fallback`) — it
   already passed the same mandatory human review gate, but its caveat is
   "unverified against this project's own conventions or implementation," not
   a training-data cutoff. Treat it the same as other What-L1 fallback items
   above (informative, not authoritative), and note its `retrieved_at`
   timestamp if relevance depends on recency.

   **How-L1 fallback items:** any `context_items` entry with
   `how_l1_fallback: true` is an org-wide process-standard suggestion (Step
   2.1, D13 in `ult-context-generate/SKILL.md`) that already passed the
   mandatory human review gate at generation time — it describes what the
   organization's process requires, not what this project's own How-L2
   conventions say. It carries no `aspect_id`/`aspect` (task-type-scoped, not
   aspect-scoped). If the work at hand is affected, flag it distinctly (e.g.
   "this package includes a How-L1 process-standard item sourced from
   `<source>` — treat as informative, not automatically authoritative, for
   this project's own conventions").

   **Institutional-memory hits (§7 in `PROTOCOL.md`, trip-wire):** any
   `institutional_memory_hits[]` entry whose `aspect_id` matches the aspect
   you're about to work on is a prior decision the trip-wire distillation
   process flagged as relevant — read its `reason` (cites the matched ledger
   entry's decision/rejected alternatives) before proceeding on that aspect,
   and branch on its `disposition`:
   - `dismissed` — the reviewer judged it not applicable here at approval
     time. Informative only, no action needed — but if the work you're about
     to do actually resembles what `reason` describes, it's worth a second
     look before assuming the dismissal still holds.
   - `accepted` — the reviewer explicitly proceeded despite the flagged risk,
     with `disposition_reason` stating why. Treat this as a deliberate,
     recorded override, not silent tolerance: don't reintroduce the same
     risk without accounting for `disposition_reason`.
   - `escalated`, or still `null` (unresolved): treat exactly like a
     contradicted decision in step 5 — **STOP.** Tell the user concretely
     which hit is unresolved (its `id`, `reason`, and `required_evidence[]`)
     and don't proceed on the affected aspect until they disposition it. Per
     §7's own approval gate, an approved package should never carry an
     unresolved `revise`/`escalate`-tier hit — finding one anyway (e.g. added
     by a later addendum) is itself a signal something upstream skipped the
     gate, and worth saying so explicitly rather than silently treating the
     null as a pass.
   - A `proceed`-tier hit needs no disposition to act on, but its
     `required_evidence[]` is still worth a quick real check before treating
     it as settled — same spirit as step 4's freshness spot-check for facts.

   **Aspect fields (D15/D17):** `context_items[].aspect_id`,
   `gaps_detected[].aspect_id`, and `institutional_memory_hits[].aspect_id`
   are the stable integer join key into the package's top-level `aspects[]`
   list (e.g. to check `aspects[].what_l3_covered`
   /`.what_l2_covered`/`.what_l1_covered` for the aspect an item belongs to).
   The sibling `.aspect` field (on `context_items`/`gaps_detected`) is the
   human-readable name and may have been edited by the user after
   `aspect_id` was assigned — use `.aspect` for display, `.aspect_id` for
   matching against `aspects[]`.

4. **Quick freshness spot-check** — NOT a full `ult-context-generate` re-run:
   - Re-read 2–3 `context_items` whose `source` is a `file:line-range` and
     confirm the referenced code still says what the package claims.
   - If `starter_kit/project_guidelines/COMPILED-GUIDELINES.md` exists,
     compare its header date to the package's `generated_at` — has it been
     recompiled since?

5. **Spot-check outcomes — split by kind, never blanket "latest wins":**
   - **A FACT changed** (the code simply moved on since the package was
     generated): note it, write a new addendum (step 7) describing what
     changed, and proceed using the newer information. Tell the user in one
     line that this happened — don't block on it.
   - **A DECISION is contradicted** (current code disagrees with an approved
     `decisions_log` / `decisions` entry): **STOP.** Tell the user
     concretely — `"<decision topic>` was decided as `<value>` in the
     approved package, but `<what you found>` suggests otherwise — is this a
     bug (code drifted from the decision) or should the decision be
     revisited?"`. Do **not** write an addendum and do **not** proceed on the
     affected work until the user answers. This extends D7's existing
     "conflicts block until human-acknowledged" rule to addenda as another
     conflict source.

6. **While doing the actual work**, if something comes up that the package
   and its addenda simply don't cover: do **one** small, targeted lookup (a
   single `graphify query` / `graphify explain`, or a direct file read — not
   a re-scan of everything), then write what you found as a new addendum
   (step 7) so the next skill that touches this feature doesn't have to look
   it up again. If the new finding is itself a What-L1-worthy gap (per Part 1
   of the assessment), write it as a `context_item` with
   `what_l1_fallback: true` — it inherits the same mandatory-review rule at
   fold-back time.

7. **Addendum file format** —
   `contexts/<feature-slug>_<task-type>_<date>.addenda.yaml`, a sibling of
   the main package, append-only, and **never itself carries `approved_by`**
   (that keeps a non-empty `approved_by` on the main package meaning what it
   already means). Reuses the package's existing `context_items` /
   `decisions_log` shapes — just two new fields, `added_by` and `added_at`:

   ```yaml
   addenda:
     - id: add_<NNN>
       kind: context_item        # or: decision
       added_by: <skill-name>          # e.g. demo-consume-context
       added_at: <ISO timestamp>
       note: >
         <one line — what was being looked up, and why>
       # then the normal context_items shape (id/layer/source/type/
       # confidence/summary/what_l1_fallback/how_l1_fallback) if
       # kind: context_item, or the decisions_log shape (topic/decided)
       # if kind: decision
   ```

   If the file doesn't exist yet, create it with this top-level `addenda:`
   list. If it exists, append to it.

8. **State, in one line, which mode was used** — at the end of your work:
   - `"Context package consulted: <id>@<hash8> (approved, generated
     <date>; <N> addenda read, <M> written)"` — for multiple packages,
     `;`-separate them: `<id1>@<hash8-1>; <id2>@<hash8-2>`.
   - or `"No context package found — proceeding without it."`

   For skills whose output is primarily a chat response rather than a
   persisted file, this line *is* the tag (D19 v2, step 9) — no separate
   file action is needed.

9. **Document-level tag and reverse index (D19 v2)** — if this skill's work
   produces a **persisted file** (a plan document, saved design notes, a
   generated report, ...), add a `**Context package(s):**
   <id1>@<hash8-1>[, <id2>@<hash8-2>...]` line near the top of that file,
   listing every package consulted (resolved via steps 0 and/or 1).

   **Item-level tags** (`[Context: <package-id>@<hash8> · ctx_NNN · aspect
   <id>]` as the first line of a generated item's body) are N/A for
   document- or chat-response-level consuming skills — they only apply to a
   producer that pushes individually-addressable sub-units to an external
   tracker (e.g. a user-story generator writing one tracker item per story).
   None of the skills in this repo do that today.

   **Reverse-index addendum (core):** for every package named in step 8's
   attribution line or this step's document-level tag, write a
   `kind: reference` addendum to its sibling
   `contexts/<package-id>_<date>.addenda.yaml` (create if absent):

   ```yaml
   addenda:
     - id: add_<NNN>
       kind: reference
       added_by: <skill-name>           # e.g. demo-consume-context
       added_at: <ISO timestamp>
       artifact: <path-to-output, or "chat response">
       cites: { ctx_ids: [...], aspect_ids: [...] }
       session_id: <optional — correlates addenda written by the same
         consuming run, if your harness exposes one>
       tokens_used: <optional int — only if a real harness-reported session
         token count is known for this run; omit if unknown, never estimate>
   ```

   `session_id` and `tokens_used` are both optional and additive — omit
   either (or both) when unknown; nothing downstream treats their absence as
   an error. They exist so `scripts/usage_report.py` (ROADMAP item 7) can
   aggregate real, measured token data across runs once operators start
   filling `tokens_used` in — see `SKILL.md`'s "Token cost tracking" section.

   This lets a future reader of `contexts/<package-id>.yaml` discover every
   downstream artifact that consulted it — the reverse of the forward tags
   this step writes.

---

This file is the single source of truth for "how does a consuming skill use
an approved context package and its addenda." It is referenced by a one-line
pointer from each consuming skill's `SKILL.md`/`.prompt.md` rather than
copied into each one — the protocol is written, reviewed, and updated in
exactly one place.

It is colocated with `ult-context-generate/SKILL.md` — the skill that
produces the package this file describes how to consume — so anyone changing
one sees the other and keeps them in sync. This mirrors the
`compiling-project-guidelines/CONSUMING-COMPILED-GUIDELINES.md` and
`ult-codegraph/CONSUMING-CODE-GRAPH.md` pattern deliberately (same shape:
fixed standard location, non-blocking optional check, one-line attribution).

This contract **never edits the approved package directly** — only the
sibling `.addenda.yaml`. Folding accumulated addenda back into the approved
package (merging facts, surfacing decision-level conflicts, re-running gap
detection, re-approving) is `ult-context-generate`'s job — see its Step 3
"fold addenda" option.

This is additive alongside `CONSUMING-CODE-GRAPH.md` and
`CONSUMING-COMPILED-GUIDELINES.md` — when no context package exists for the
current feature, this contract is a no-op and those two contracts behave
exactly as they do today.
