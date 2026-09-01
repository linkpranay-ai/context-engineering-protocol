# Wizard write path (Phase 1 + Phase 2)

Self-contained restatement of `ult-cep-wizard`'s write path (D24 §18, Phase 1 +
Phase 2) — how a repo goes from no discovery artifact at all, to a PENDING decision
line in `context-layout-discovery.md`, to a committed key in `context-config.yaml`.
Read this alongside `wizard-picker-and-boxes.md` (the read path this builds on),
`wizard-onboarding-state-machine.md` (when `/api/discover` becomes reachable at all),
and `wizard-security-model.md` §7 (what gates every request before it reaches any of
the code described here).

**Core rule: wizard-proposes, CLI-commits (§18.3).** The wizard never writes
`context-config.yaml` or a `CONFIRMED` stamp directly *by hand* — every write on this
D23 decision axis goes through `confirm_layers.run_confirm()`, and the one and only
place any of this skill's code calls it is `wizard_apply.apply_confirmed()`.
Everything before that call is refusal logic; everything after it is result
classification, never a second write.

The same invariant, read as "the wizard never writes to disk except by calling an
already-existing, already-tested deterministic CLI script — never ad hoc code of its
own," extends to the separate D20 axis's `wizard_init.py` → `validate_layout.run_init`
(§6a below): a second script, a second axis (slot scaffolding/`project_layout`, not
decision lines), same rule.

## 1. Module map

| Module | Role |
| --- | --- |
| `layout_decision_grammar.py` (in `ult-repo-layout`) | Shared vocabulary: section-title constants, `FIELD_LINE_RE`/`CONFIRMED_STAMP_RE`/`PLACEHOLDER_RE`, `parse_comment_clauses`, `parse_dotted_path`. Both `discover_layers.py`/`confirm_layers.py` and this skill import from here — no more duplicated regexes. |
| `confirm_layers.py` (in `ult-repo-layout`) | The engine: `Field`/`FieldError`/`parse_artifact`/`apply_field`/`set_scalar`/`run_confirm`. Unmodified in spirit by this plan — the wizard calls into it, never reimplements it. |
| `wizard_decision_staging.py` | Wizard-side staging: `validate_custom_arg`, `format_decision_line`, `stage_decision`. Writes only `context-layout-discovery.md`, via `wizard_atomic_write.write_text_atomic` — its first production caller. |
| `wizard_content_hash.py` | `hash_artifact`/`hash_config` — bare SHA-256 over file bytes. The mechanism behind both the H6 staleness check and the C2 no-op check. |
| `wizard_apply.py` | `apply_confirmed()` — the only caller of `confirm_layers.run_confirm()`. Refuses (never commits) on a stale hash, an unresolved field, or a double-primary-choice section; classifies the result into a real commit, an idempotent no-op, or the C2 failure mode. |
| `wizard_layout_source.py` | `LayoutSource.read_decisions()` — parses the current artifact into a flat list of `DecisionField`s for `/api/decisions`, and `LayoutSource.discovery_artifact_path` — the one shared, workspace-root-aware lookup every write-path module uses to find the artifact, instead of each hand-rolling the `_normalize_workspace_root` dance. |
| `wizard_discover.py` | Phase 2. `run_discover()` — the freshness + staged-decision guard in front of `discover_layers.run_discovery()`; see §5 below. |
| `wizard_server.py` | `do_POST` — the three-gate dispatcher (see `wizard-security-model.md` §7) — plus `_handle_api_decisions`/`_handle_api_stage`/`_handle_api_apply`/`_handle_api_discover`/`_handle_api_init_preview`/`_handle_api_init`. |
| `wizard_init.py` | Thin wrapper around `validate_layout.run_init` (D20 axis — §6a) — `preview_init`/`run_init`, same shape as `wizard_discover.py`'s wrap of the D23 discover script. |
| `static/wizard.js` | `postJson()` (CSRF-header-carrying POST), the decisions list UI, the picker-to-CUSTOM-arg "Use this directory" flow, the Apply button, and (Phase 2) the Discover/Re-run-Discover buttons. |

## 2. The staging step: `POST /api/stage`

Request body: `{"section_title", "field_key", "verb", "arg": <optional>, "line_no":
<optional>}`. `line_no` disambiguates when more than one decision-bearing line in the
same section shares the same `field_key` (a §17.4 section can render multiple
candidate lines) — omit it when there's only one.

`stage_decision(repo_root, artifact_path, section_title, field_key, verb, arg=None,
line_no=None)`:

1. Locates the target line via `confirm_layers.parse_artifact` — refuses
   (`DecisionStagingError`) if no matching line exists, or if `line_no` is required to
   disambiguate but wasn't given.
2. Refuses if the line is already non-`PENDING` — staging never overwrites an existing
   staged or confirmed decision; the caller must be looking at current state (which
   `/api/decisions` always gives fresh) before staging.
3. Refuses a second primary choice in the same section (a stage-time mirror of
   `confirm_layers._check_single_primary_choice` — intentionally duplicated here for
   fast UX feedback rather than a round trip through `run_confirm`; this duplication is
   a by-hand sync risk if `confirm_layers.py`'s own rule ever changes without this
   mirror being updated alongside it).
4. For a `CUSTOM` verb, validates `arg` via `validate_custom_arg` — repo-relative,
   forward slashes only (a literal `\` is refused, never silently converted), no `..`,
   no drive letter, no `#`, and must resolve inside the root via
   `wizard_containment.check_containment`. See `wizard-security-model.md` §7 for why
   this validation exists at the wizard's boundary at all — `confirm_layers.py` itself
   has none, because the artifact is hand-editable by design.
5. Renders the new line via `format_decision_line`, preserving the original comment
   clause text verbatim (read from the existing `PENDING` line, reused unchanged) — so
   `parse_comment_clauses` parses the rewritten line identically to a hand edit.
6. Writes the whole artifact back via `write_text_atomic`.

Response on success: `{"staged": true, "artifact_hash": "<sha256 of the artifact after
this write>"}`. The frontend carries this hash forward as the value it will later send
to `/api/apply` — never a value computed client-side, always the server's own
post-write hash.

## 3. Reading current state: `GET /api/decisions`

Returns `{"artifact_hash": <sha256 or null>, "fields": [...]}`. `artifact_hash` is
`null` when no discovery artifact exists yet (a repo that hasn't run `discover`) — in
that case `fields` is `[]`, not an error; a fresh repo with nothing to decide yet is a
normal state, not a failure.

Each field: `{"section_title", "field_key", "line_no", "raw_value", "comment",
"state", "allowed_verbs"}`. `state` is one of `"pending" | "staged" | "confirmed"` —
derived the same lightweight way `stage_decision`'s own checks are (does the comment
carry the `CONFIRMED_STAMP_RE` stamp; is `raw_value` literally `"PENDING"`), **not** by
calling `Field.resolve()` — a still-malformed field must still be listed here so the
UI can show it, not raise and take the whole read down with it. `allowed_verbs` is `[]`
once `state == "confirmed"` (nothing left to offer); resolution and its errors are
`apply_confirmed`'s job entirely, not this route's.

The frontend calls this on load and after every successful stage or apply — it is
always the source of truth for what to render, never a value the client mutates
locally and assumes stays in sync.

## 4. The commit step: `POST /api/apply`

Request body: `{"loaded_artifact_hash": <hash the caller last read via
/api/decisions>}`. A missing/omitted key is not given its own 400 check — the freshness
check below already fails closed on any mismatch (`None` only matches a genuinely
missing artifact), so an absent key naturally routes through the same
`StaleArtifactError` path as an explicitly stale one.

`apply_confirmed(repo_root, artifact_path, loaded_artifact_hash)`:

1. **Freshness check (round-3 H6).** Current artifact hash vs. `loaded_artifact_hash` —
   a mismatch means the artifact changed underneath this session (a concurrent
   `discover` re-run, another browser tab staging something) → `StaleArtifactError`,
   HTTP 409. Nothing is committed.
2. **All-resolved pre-check.** Every `Field` is resolved and
   `_check_single_primary_choice` is run — exactly what `run_confirm` enforces
   internally, done here first so a still-`PENDING` field or an unresolved
   double-primary-choice section produces a structured `ValidationError` (HTTP 400,
   every offending message included) instead of a bare exit-code tuple the caller has
   to interpret.
3. **The real call.** `context-config.yaml` is hashed before, then
   `confirm_layers.run_confirm(repo_root)` is called **in-process** — no subprocess;
   there is nothing interactive in it, and a subprocess would only add exit-code/
   stdout-parsing failure modes on top of the tuple `run_confirm` already returns
   directly — then hashed again after.
4. **Result classification (round-3 C2).** Exit code 0 alone is not proof of a real
   write; three outcomes share it:
   - config hash changed → real commit, `config_changed=true`.
   - config hash unchanged **and** a message starts with `"Nothing to confirm"` → every
     field was already confirmed, a legitimate idempotent no-op, `idempotent=true` —
     still success.
   - config hash unchanged **and** no such message → the C2 silent-no-op failure mode.
     `run_confirm` claimed success but nothing happened and gave no explanation.
     `UnexpectedNoOpError`, HTTP 500. **Never** reported as success.

Response on success (HTTP 200): `{"config_changed", "idempotent", "messages",
"config_hash_after", "artifact_hash_after"}`. The frontend reloads both `/api/status`
and `/api/decisions` after any 200 — the whole point of the write path is that both
read routes reflect the change on the very next read, not a stale in-memory snapshot.

## 5. The discover step: `POST /api/discover` (Phase 2)

Request body: `{"loaded_artifact_hash": <hash the caller last read, or null/omitted if
no artifact exists yet>, "force": <bool, default false>}` — the same field name `/api/apply`
uses (§4), reused rather than introducing a second name for the same concept. Reachable
in the `needs_discover` state (first-run, `loaded_artifact_hash: null`) and again from
`decisions_pending`/`steady_state` as "Re-run Discover…" (re-scan after the repo itself
changed) — same route and same handler either way, per
`wizard-onboarding-state-machine.md`.

`run_discover(repo_root, artifact_path, loaded_artifact_hash, force=False)`:

1. **Freshness check**, checked first, unconditionally — even when `force=True`. Current
   artifact hash (or `None` if no artifact exists) vs. `loaded_artifact_hash` from the
   client. A mismatch means the artifact changed underneath this session since the
   client last read state → `StaleArtifactError`, HTTP 409. `force` only ever waives the
   staged-decision guard below, never this check — there is no scenario where discarding
   work against artifact state the client hasn't even seen yet is the right call.
2. **Staged-decision guard.** Scans every field via `LayoutSource.read_decisions()` for
   `state == "staged"`. If any exist and `force` is not set → `AtRiskDecisionsError`,
   HTTP 409, with `at_risk_sections` listing exactly which ones would be discarded — the
   frontend turns this into a specific "these staged picks will be lost" confirm step,
   not a generic error banner. This exists because `discover_layers.py`'s own drift
   tracking (`_load_prior_confirmed_state`) only preserves a section when *every* field
   in it is already `# CONFIRMED`-stamped; a staged-but-not-yet-Applied pick does not
   qualify and would otherwise be silently clobbered by a bare re-run.
3. **The real call.** `discover_layers.run_discovery(repo_root)` — in-process, same
   non-interactive, no-subprocess reasoning as `run_confirm` in §4 above.

Response on success (HTTP 200): `{"artifact_hash_after", "discarded_staged_sections"}` —
the latter is always `[]` unless step 2's guard was bypassed with `force=True`, in which
case it names exactly what was discarded so the UI can show a specific summary rather
than a silent state change. A `DiscoverError` not covered by either guard above (e.g.
`discover_layers.run_discovery` itself failing) is HTTP 400 with `{"error": str(exc)}`.

## 6a. The init step: `POST /api/init/preview` and `POST /api/init` (ISSUES.md Round 2
finding 9, 2026-08-31)

A separate axis from §§2-5 above: D20 (slot scaffolding / `project_layout`), not D23
(discovery decisions). Reachable only while `workspace_root_offer_eligible` is `true`
in `/api/state` — see `wizard-onboarding-state-machine.md` §6 for the full eligibility
rule and rationale. Request body for both routes: `{"workspace_root": "<path>" |
null}` (blank/omitted → `None`, meaning "use pre-D21 defaults").

Both routes call `wizard_init.py`, which calls `validate_layout.run_init` directly —
no staging step, no freshness hash, no separate confirm route, unlike §§2-5. This is
intentional, not a shortcut around the wizard-proposes/CLI-commits rule: `run_init` is
itself the same kind of deterministic, already-tested CLI script `run_confirm` is
(§4's rule extended — see the "Core rule" callout in §2 above), and `--init` already
exists as a directly-runnable CLI command independent of the wizard. The only thing
the wizard adds is a friendlier request/response shape and the `dry_run` preview
distinction:

- `POST /api/init/preview` → `preview_init(repo_root, workspace_root)` →
  `run_init(..., dry_run=True)`. Runs every refusal check and the full slot-resolution
  loop, writes nothing. Response: `{"messages": [...]}`, each line prefixed "Would …".
- `POST /api/init` → `run_init(repo_root, workspace_root)` →
  `run_init(..., dry_run=False)`. The real write: scaffolds each installed slot,
  writes `project_layout` into `context-config.yaml`, and — only if `workspace_root`
  was given — sets `layout.workspace_root` and pre-populates the
  `layers.what_l2.exclude` triad (§16.5/§16.7). Response: same `{"messages": [...]}`
  shape, past tense.

Either route raises `wizard_init.InitError` (HTTP 400, `{"error": str(exc)}`) on any
refusal `run_init` itself already enforces — no `context-config.yaml` yet, the repo
root itself passed as `workspace_root`, or (the case this route exists to make
unreachable via the UI, not just via the CLI) already D20-initialized. The frontend
never needs to special-case that last refusal: `workspace_root_offer_eligible` already
hides the offer before it could happen.

Both handlers additionally run `wizard_containment.check_containment(ctx.repo_root,
workspace_root)` before calling into `wizard_init` at all (HTTP 400,
`{"error": str(exc)}` on `ContainmentError`) — see `wizard-security-model.md` §5.
`run_init`'s own well-formedness check (`check_path_wellformedness`) independently
rejects an absolute/UNC value too; the two are deliberately redundant, not
either-or, since `check_containment` also catches a symlink/junction component the
well-formedness check was never designed to see. This makes `workspace_root` the same
"validated at the boundary, not just deep in the call stack" shape as every other
client-supplied path this document covers, closing the one route that used to skip it.

## 6. Frontend flow

1. On load, `wizard.js` fetches `/api/decisions` and renders each field as a row: a
   state badge (`PENDING`/`STAGED`/`CONFIRMED`), the current raw value, and one button
   per entry in `allowed_verbs`.
2. Clicking a plain verb (`CONFIRM`/`SKIP`/`DISABLE`/`ACKNOWLEDGE`) stages it
   immediately via `POST /api/stage` with no `arg`.
3. Clicking `CUSTOM` ("Pick directory…") sets that field as the active target and
   reveals a "Use this directory" button in the Browse panel — browsing itself is
   unchanged and has no side effect; only clicking "Use this directory" while a target
   is set calls `/api/stage` with `arg` set to the picker's current `rel_path` (the same
   containment-checked value `/api/picker` already validated, not a second path the
   client constructs — see `wizard-picker-and-boxes.md`).
4. The Apply button stays disabled until every visible field's `state !== "pending"` —
   there is no way to Apply while something is still unresolved, mirroring (client-side,
   for UX only — the server enforces this independently in step 2 above) what
   `apply_confirmed`'s own pre-check refuses.
5. Clicking Apply calls `POST /api/apply` with the last-known `artifact_hash`. On 200,
   both `/api/status` and `/api/decisions` reload. On 409, the UI reports that the
   layout changed and reloads `/api/decisions` rather than allowing a blind retry
   against state the server has already rejected once.

## 7. What this plan deliberately leaves out

- The paste-back content-handoff mode (§18.6) — a different write flow for handing
  wizard-selected content back to a calling process — is out of scope here and remains
  a distinct, later deliverable.
- No undo/redo and no draft-vs-committed distinction beyond staged-vs-applied — a
  staged decision is either re-staged (overwriting the same still-unapplied line, not
  currently supported — `stage_decision` refuses a second stage over a non-`PENDING`
  line) or applied; there is no "unstage" action.
- No multi-user conflict resolution beyond the single H6 freshness check — this is a
  single-operator, single-sitting tool (see `wizard-security-model.md` §6), and a
  second concurrent editor is handled by refusing the second Apply, not by merging.
