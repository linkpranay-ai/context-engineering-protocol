# Wizard retrofit flow (Journey 3, D24 Phases A-C)

Self-contained restatement of `ult-cep-wizard`'s Journey 3 flow — hooking an existing,
third-party skill library up to a project's CEP output via `ult-cep-retrofit`, without
vendoring or rewriting that library. Journey-3 analogue of
`wizard-onboarding-state-machine.md`/`wizard-write-path.md`/`wizard-picker-and-boxes.md`,
which together document Journey 1 (brownfield-layout onboarding). Read alongside
`wizard-security-model.md` §7 (gates every mutating route described here) and
`wizard-picker-and-boxes.md` (the `GET /api/picker` route this flow's target picker
reuses, now with an additional optional `external_root` param — see §1.2).

## 0. Why this is its own journey, not a fifth onboarding box

`wizard_onboarding_state`'s four-value enum (Phase 0/1) models one linear flow: discover
→ decide → confirm the *project's own* layout. Retrofit is a different question entirely
— "does *this other skill library* know how to use what the project just produced?" — and
doesn't fit that state machine as a fifth value. It's modeled as a fully orthogonal nav
entry instead: reachable regardless of onboarding state, with its own state file
(`RETROFIT-STATE.json`, §3 below), never touching `context-layout-discovery.md` or
`context-config.yaml`.

## 1. Two scope-narrowing decisions (binding, made explicit up front)

1. **No LLM in the loop.** `ult-cep-retrofit`'s own SKILL.md leans on a Claude agent's
   judgment for voice-matched drafting (its Step 6.3). The wizard is pure deterministic
   Python and cannot reproduce that. Every drafted sentence is a fixed, contract-specific
   template (`wizard_retrofit_draft._TEMPLATE_SENTENCES`) with the resolved reference
   substituted in — never generated text — and the frontend always renders the result into
   an editable textarea (`wizard_retrofit_state.set_draft_override`) so a human supplies
   final wording. The draft is a starting point, never treated as final.
2. **Target defaults to inside the project repo; an external target is an explicit,
   separately-validated opt-in (ISSUES.md Round 2 finding 7, 2026-08-31).** The
   picker/containment machinery (`wizard_picker.py`/`wizard_containment.py`) is rooted at
   `ctx.repo_root` by default — `cep_retrofit.py`'s own Step 1 has no such constraint, but
   opening the picker to arbitrary absolute paths with no validation would be a real
   containment regression. Rather than leave that as a permanent same-repo-only limit, the
   frontend's `#retrofit-external-root-panel` lets a human type an absolute path and
   "Browse" it; every request that touches it re-resolves and canonicalizes that path via
   `wizard_containment.resolve_external_target()` (must be absolute, not already inside
   `repo_root`, not a symlink/junction, and an existing real directory) — the server never
   trusts a client-supplied or previously-persisted value at face value, including reads
   from its own `RETROFIT-STATE.json`. The resolved root threads through as `external_root`
   (`GET /api/picker`, `GET /api/retrofit/inventory`) or `target_root` (`POST
   /api/retrofit/select`, persisted per-unit, then re-read for `draft`/`apply`) — see §5.
   `cep_retrofit.py` itself is still always imported from *this* repo's
   `ult-cep-retrofit` regardless of the retrofit target, and `RETROFIT-STATE.json` still
   lives under `ctx.repo_root` always; only the containment/write boundary for
   target-side paths moves. Same-repo reference mode is refused for a genuinely external
   target (`RetrofitDraftError` server-side; the same-repo radio is disabled client-side
   with an explanatory note) — plugin-qualified is the only reference shape that makes
   sense once the target isn't this repo, so it's forced there instead of left to fail
   later at draft time. For an in-repo target, nothing here changes: same-repo stays the
   wizard-computed default, plugin-qualified stays an explicit manual override, never
   auto-detected.

## 2. Module map

| Module | Role |
| --- | --- |
| `cep_retrofit.py` (in `ult-cep-retrofit`, imported dynamically — never vendored) | Stateless, read-only-until-Phase-C engine: `inventory()`, `describe()`, `recommend()`, `check_pointer()`, `find_insertion_point()`. Same in-process dynamic-import pattern as `wizard_decision_staging._import_confirm_layers`, applied here so `recommend()`'s embedded-double-quote PowerShell-mangling bug (see its own docstring) never has a shell in the path to trigger it. |
| `wizard_retrofit_inventory.py` (Phase A) | `build_inventory()` — containment-checks the target, then batches `inventory()`/`describe()`/`recommend()` for every discovered unit into one `RetrofitInventoryResult`, so the frontend needs one round-trip, not N. A single unit's `describe()` failure (race-deleted file, unreadable primary file) is recorded on that unit (`describe_error`) rather than aborting the whole inventory. Read-only — no write function anywhere in this module. |
| `wizard_retrofit_draft.py` (Phase B) | Pure functions: `resolve_reference()` (same-repo relative-path math via `posixpath.relpath`, or plugin-qualified pass-through validated against `_PLUGIN_QUALIFIER_RE`), `draft_insertion_text()` (fixed `CONTRACT_ORDER`, template substitution, one combined block per SKILL.md Step 6.4), `detect_contract_locations()` (best-effort default only, always shown as an editable field — SKILL.md Step 5's "ask, don't assume"). `build_draft()` is the one orchestration entry point: idempotency check first (`check_pointer`, by contract identity), and only for whatever remains — `find_insertion_point()` plus this module's own resolve/draft functions. |
| `wizard_retrofit_state.py` (Phase B) | Owns `cache/cep-retrofit/RETROFIT-STATE.json` under `ctx.repo_root` — durable per-unit selection/draft state, see §3. |
| `wizard_retrofit_apply.py` (Phase C) | `apply_unit()`/`apply_batch()` — the write path, see §4. |
| `wizard_server.py` | `do_GET`/`do_POST` route dispatch for every `/api/retrofit/*` route (§5), each mutating route behind the same three-gate chain every other write route uses (`wizard-security-model.md` §7). |
| `static/wizard.js` | Target picker (reuses `GET /api/picker`, plus `#retrofit-external-root-panel` for an explicit external target — §1.2) → inventory table → per-row draft panel (reference-mode radio, disabled to plugin-only for an external target, editable draft textarea, three-`<pre>`-zone context-before/inserted-block/context-after preview) → batch preview → "Apply changes" with a live per-unit result list and summary. |

## 3. Durable state: `cache/cep-retrofit/RETROFIT-STATE.json`

Modeled directly on `ult-autoscaffold-content/scripts/scaffold_state.py`'s
`TRIAGE-STATE.json` convention (whole-file rewrite, stable key order, 2-space indent, so
diffs stay small and readable) — written via `wizard_atomic_write.write_text_atomic`, same
primitive Phase 1's write path uses.

**Why durable state here, when Phase A needed none:** a run against a 20+-unit library
walking per-unit select → draft → review is exactly the multi-round-trip flow a browser
refresh or a wizard-process restart (routine for a local dev tool) would otherwise blow
away. Unlike the layout-onboarding journey, there's no already-durable artifact to
re-derive selections from — `cep_retrofit.py` is stateless by design. Unlike
`scaffold_state.py`'s own modules, retrofit *units* aren't rediscovered by rescan here:
Phase A's `build_inventory()` is always the live source of truth for what units exist;
this file only ever remembers what a human decided about them.

The file never records target-file *content* — only selections, drafted text, and the
target file's content hash at draft time (`wizard_content_hash.hash_file`), so Phase C's
freshness check can detect the file changing underneath a stale draft before ever writing
to it (mirrors `wizard_apply.py`'s `StaleArtifactError` pattern in the layout journey).
The containing directory is idempotently, best-effort registered in the onboarded
project's own `.gitignore` — this is wizard scratch data, never meant to be committed to
the project being onboarded.

Per-unit shape (`units.<unit_id>`): `primary_file`, `unit_dir_rel_path`, `include`,
`contracts`, `reference_mode`, `reference_args`, `context_availability` (from
`upsert_selection`, i.e. `POST /api/retrofit/select`) plus `draft_text`,
`draft_overridden`, `insertion_point`, `contracts_included`,
`contracts_skipped_idempotent`, `target_file_hash`, `context_before`,
`context_after` (from `set_draft`/`set_draft_override`, i.e.
`POST /api/retrofit/draft`/`draft-override`).

`context_availability` (ISSUES.md Round 2 finding 6, 2026-08-31) is one of
`ask`/`required`/`optional` (`wizard_retrofit_draft.CONTEXT_AVAILABILITY_POLICIES`,
default `ask`) — a per-unit UI control next to the contract checkboxes
(`renderRetrofitUnitRow` in `wizard.js`), posted alongside `contracts` on
select, and rendered into the drafted CONSUMING-CONTEXT-PACKAGE.md pointer
sentence by `draft_insertion_text()` so the policy is visible in the
retrofitted skill file itself, not only in wizard state. See
`CONSUMING-CONTEXT-PACKAGE.md`'s "Context-availability policy" callout for
what each value means to the consuming skill at runtime.

## 4. The write path: `wizard_retrofit_apply.py`

**This is the phase that grows the write surface.** Phase 1's write path (`wizard_apply.py`)
touches exactly two CEP-owned artifacts. This module writes to *any file the target picker
can reach under the project* — the whole point of retrofitting a consumer skill library.
`wizard_containment.check_containment` is still the fail-closed boundary (see
`wizard-security-model.md` and `SECURITY.md`'s write-surface paragraph, which landed
together with this phase per the plan's own gate, not as a follow-up).

`apply_unit()`'s per-unit (not per-batch) mechanics, mirroring SKILL.md Step 8's own
stated contract ("a write failure on one file is reported for that file and does not
abort the rest of the batch"):

1. **Fast-path skip** if there's nothing staged to insert (`draft_text` empty) — covers
   both "never drafted" and "already fully applied in a prior request" without touching
   the filesystem. This is the mechanism (see step 5 below) that makes re-posting an
   already-applied batch safe.
2. **Freshness check** — re-hash the target file and compare against the hash captured
   when its diff preview was computed (`build_draft`'s `target_file_hash`). A mismatch
   means the file changed underneath the session; reject this unit only, asking for a
   reload + re-draft, never silently overwrite.
3. **Last-instant idempotency guard** — re-run `check_pointer()` on exactly this draft's
   contracts, immediately before writing. All-present → skip without writing
   (`skipped_idempotent`). *Some but not all* present → fail closed rather than attempt a
   partial re-slice of an already-baked `draft_text` block (a single combined block per
   Step 6.4 can't be safely re-sliced without re-running `draft_insertion_text`, which this
   module deliberately never does — no re-templating on the write path). This branch is
   defense-in-depth only; it's provably unreachable via the normal
   select → draft → apply → (re-)apply flow (see the module's own docstring for the proof),
   but `apply_unit` doesn't rely on that invariant holding.
4. **Splice + atomic write** — insert `draft_text` at `insertion_point["line"]` (0-indexed,
   insert-before semantics, the exact contract `find_insertion_point`/
   `_extract_context` both already assume), preserving the original file's trailing-newline
   convention, then `wizard_atomic_write.write_text_atomic`.
5. **Isolation** — every step above returns rather than raises for every anticipated
   failure; `apply_batch()` additionally wraps each `apply_unit` call in a bare `except` so
   one truly unexpected exception can't take the rest of the batch down with it either.

**State-update note (caller's responsibility, not this module's):** after a successful
apply, `wizard_server.py`'s route handler resets the unit's state via
`wizard_retrofit_state.set_draft(..., draft_text="", insertion_point=None,
contracts_included=[], contracts_skipped_idempotent=<old + newly-applied>,
target_file_hash=<post-write hash>, ...)` — the exact same shape `build_draft()` already
uses for "nothing left to insert here." This keeps "fully applied" and "fully satisfied
on disk already" a single representation instead of two states this module would
otherwise have to keep in sync, and is what makes step 1's fast-path skip correctly turn a
resubmitted already-applied unit into `skipped_idempotent` without ever touching the
filesystem again.

## 5. Routes

| Route | Gate | Handler |
| --- | --- | --- |
| `GET /api/picker?path=<rel>[&external_root=<abs>]` | session only (read-only) | `_handle_api_picker` → `wizard_picker.list_directory`, rooted at `external_root` once resolved, `repo_root` otherwise |
| `GET /api/retrofit/inventory?target=<rel>[&external_root=<abs>]` | session only (read-only) | `_handle_api_retrofit_inventory` → `wizard_retrofit_inventory.build_inventory` |
| `GET /api/retrofit/state` | session only (read-only) | `_handle_api_retrofit_state` → `wizard_retrofit_state.load_state` |
| `GET /api/retrofit/contract-locations` | session only (read-only) | `_handle_api_retrofit_contract_locations` → `wizard_retrofit_draft.detect_contract_locations` |
| `POST /api/retrofit/select` (body may include `target_root`) | origin/host → session → CSRF | `_handle_api_retrofit_select` → `wizard_retrofit_state.upsert_selection` |
| `POST /api/retrofit/draft` | origin/host → session → CSRF | `_handle_api_retrofit_draft` → `wizard_retrofit_draft.build_draft` (re-reads/re-validates `target_root` from the persisted state entry, never from the request body), persisted via `wizard_retrofit_state.set_draft` |
| `POST /api/retrofit/draft-override` | origin/host → session → CSRF | `_handle_api_retrofit_draft_override` → `wizard_retrofit_state.set_draft_override` |
| `POST /api/retrofit/apply` | origin/host → session → CSRF | `_handle_api_retrofit_apply` → `wizard_retrofit_apply.apply_batch`, per-unit state reset per §4; per-unit `target_root` (from state) is re-validated inline so one unit's vanished/invalid external root fails only that unit, never the batch |

`select`/`draft` are kept as two separate steps (rather than one combined call) so a
change to contracts or reference config can be re-staged without forcing a redraft in the
same request — `upsert_selection` never touches a unit's previously-computed draft fields;
callers that change the selection are expected to call `draft` again afterward, which
recomputes and overwrites those fields together, atomically.

`POST /api/retrofit/apply` always answers HTTP 200 with a per-unit results list — a
partial batch failure is a normal outcome, not a request-level error; only a structural
failure (e.g. a vanished repo root) would 500 the whole route.

`external_root`/`target_root` are always optional and always re-validated server-side via
`wizard_containment.resolve_external_target()` on every request that carries one —
omitting the field (the default, unchanged from before this finding) means "use
`ctx.repo_root`," matching every prior version of this flow exactly; see §1.2.

## 6. UI walk

1. Target picker (reuses `GET /api/picker`) → "Use directory" stages the retrofit target,
   containment-checked the same way every other picker consumer is. `#retrofit-external-
   root-panel`, above the repo-relative picker, is an alternative entry point for an
   explicit external target (§1.2): typing an absolute path and clicking "Browse" re-roots
   the same picker UI at that directory (via `external_root`) once the server resolves and
   canonicalizes it; a resolution failure clears the attempt and shows the error inline
   rather than silently falling back to `repo_root`. Once active, a warning banner names the
   resolved external path so it's never ambiguous which root subsequent writes will target,
   and "Use this repo instead" clears it.
2. Inventory table: name/type/path/`via_symlink` badge per unit, an unclaimed-directories
   panel with a free-text "how should these be treated?" box (SKILL.md Step 2's "don't
   guess a fourth heuristic" — the wizard doesn't either). For medium-to-large inventories
   (ISSUES.md Round 2 finding 8, 2026-08-31 — 85 mixed units from a single third-party repo
   in the reported case), a filter bar sits above the list: text search (name/path), a
   canonical-only checkbox (checked by default — `build_inventory()`'s `tier_counts`
   already distinguishes canonical from supplementary; this just defaults the view to it),
   code-related/task-related checkboxes, and clickable directory chips sourced from
   `RetrofitInventoryResult.directory_counts` (one bucket per unit's first path segment
   below the retrofit target, computed once server-side as `RetrofitUnit.source_directory`
   so the frontend never re-derives its own grouping). Changing any filter re-scopes what
   "reviewed" means: the review-gate checkbox and its label text
   (`#retrofit-review-gate-text`) both reset to describe only the currently-visible count,
   not a global "I reviewed everything" acknowledgement — the exact behavior the finding's
   Recommendation asked for.
3. Per-row expand: `recommend()`'s two badges (code-related/task-related) + matched terms,
   the 3 contract checkboxes pre-checked per SKILL.md's exact code/task → contract rule,
   always editable; a reference-mode radio (same-repo default, computed via
   `detect_contract_locations`, or plugin-qualified manual override) — disabled to
   plugin-qualified only, with an inline note explaining why, whenever this inventory's
   target is external (§1.2; same-repo's relative-path math is meaningless once the
   target isn't this repo, so the row forces the only mode that still makes sense rather
   than letting the human pick one the server will refuse at draft time).
4. Draft panel: editable textarea seeded from `build_draft()`'s template output, with the
   three-`<pre>`-zone context-before / inserted-block / context-after preview (pure
   string-slicing around `insertion_point.line` — no diff algorithm needed, every change
   here is a pure insertion, never a replacement).
5. Batch preview: one collapsible card per unit with a saved draft, a per-card checkbox to
   drop a unit from the batch at the last second (SKILL.md Step 7: "per-file or in one
   batch, their choice"), and a live "N changes" count gating the Apply button.
6. Apply: `POST /api/retrofit/apply` for every remaining checked unit, then a live
   per-unit result list (status-colored: applied / skipped_idempotent / failed-with-reason)
   plus a persistent "N retrofitted, M skipped, K failed" summary, rendered as a sibling of
   the batch-preview section (not nested inside it) — a successful apply empties the batch
   (applied cards drop out once their `draft_text` clears), which hides that section; if the
   result list lived inside it, the report of what just happened would vanish in the same
   instant it appeared. Any still-open draft panel for an applied unit is refreshed in place
   rather than the whole inventory re-rendering, which would collapse open `<details>`
   elements.

## 7. What this plan deliberately leaves out

- **LLM-assisted drafting** — v1 scope decision (§1.1); every draft is a fixed template,
  always human-reviewed in an editable textarea before it can be applied.
- **A fourth unclaimed-directory heuristic** — SKILL.md's own stance, carried forward
  unchanged: the wizard surfaces unclaimed directories and a free-text box, never guesses.
- **Undo/redo** — mirrors `wizard-write-path.md` §6's same call for the layout journey;
  once a unit is applied, reverting it is a normal file edit outside the wizard, not a
  wizard feature.
- **Partial re-slicing of an already-drafted block** — see §4 step 3; a change to which
  contracts apply always means re-drafting, never patching a stale block in place.
