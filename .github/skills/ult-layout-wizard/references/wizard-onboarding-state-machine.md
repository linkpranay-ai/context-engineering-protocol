# The onboarding state machine (Phase 2, D24 §18.14)

Self-contained restatement of `wizard_onboarding_state.py` — how the wizard decides
which of four screens to show, computed fresh on every `GET /api/state` call rather
than gated once at server startup. Read alongside `wizard-security-model.md` §1 (why
this replaced two of `wizard_preflight.py`'s three original checks) and
`wizard-write-path.md` §5 (`POST /api/discover`, the one deterministic action this
state machine's `needs_discover` screen drives).

## 1. Why this exists: check 2 tested the wrong axis

`wizard_preflight.py` originally ran three checks, each independently sufficient to
refuse startup before any socket opened: (1) `ult-repo-layout` installed, (2)
`ult-repo-layout` "initialized" — tested via **D20** slot-registry state
(`.layout-slots.yaml` markers or a `project_layout` key, written by
`ult-repo-layout`'s interactive `init`/`reconcile` flow), (3) `validate_layout.py
--validate` currently passing.

Check 2 was confirmed by direct testing to check the wrong thing. This wizard's own
Decisions UI operates on the **D23** discover/confirm-layers system — `discover_layers.py`
writes `context-layout-discovery.md`, and `confirm_layers.py` writes direct
`layers.what_l2.path`-style keys into `context-config.yaml`; neither ever touches
`project_layout` or writes a marker file. So a repo that only ever ran `discover` +
`confirm-layers` — the actual brownfield path this wizard exists to support — could
never pass check 2, no matter how complete its setup was. Running a real
`discover_layers.py` against a fresh fixture repo did not clear the old preflight; only
hand-stamping a fake `project_layout` key did.

This is why check 2 is **retired outright, not softened into a warning** — a "soft
check 2" would still be measuring D20, under a name that invites confusion with the
real D23-derived state this module now computes instead. Check 3 (`validate` passing)
is also removed from *startup*, for a related but distinct reason: a broken layout is
exactly the case this wizard should be able to show the user, not refuse to start
over.

## 2. The state table

`compute_state(repo_root)` — always re-reads disk, never cached, matching the same
principle `wizard-picker-and-boxes.md` §1 documents for the read path:

| State | Entry condition | Screen |
|---|---|---|
| `layout_broken` | `validate_layout.validate(repo_root)` returns `ok=False` | Minimal screen listing the `FAIL` lines from the validation report. No boxes/decisions/picker attempted — `LayoutSource`'s own constructor-time `validate()==True` invariant means one couldn't be built anyway. |
| `needs_discover` | Validates clean, but `context-layout-discovery.md` doesn't exist yet | Guide-only intro + a real **Run Discover** button (`POST /api/discover`, see `wizard-write-path.md` §5). |
| `decisions_pending` | Artifact exists, at least one field's `state` is `pending` or `staged` | The existing Decisions UI (`wizard-write-path.md` §6), unchanged — just reachable now on a repo that was never pre-initialized outside the browser. |
| `steady_state` | Artifact exists, every field is `confirmed` | The full boxes/decisions/picker experience, byte-for-byte the same as before Phase 2. |

Evaluation order in `compute_state`: `validate()` first (decides `layout_broken` vs.
everything else); then artifact existence (decides `needs_discover` vs. the two
decision-bearing states); then a scan of `read_decisions()` counts (decides
`decisions_pending` vs. `steady_state`). Each state is a dataclass
(`OnboardingState`) carrying enough of that evaluation's byproducts —
`validate_failures`, `discovery_artifact_exists`, `decision_counts` — that the frontend
never has to re-derive them from a second call.

## 3. `d20_initialized`: informational, never gating

D20 status (the old check 2's predicate, relocated verbatim into
`_is_d20_initialized` — same `SLOT_REGISTRY`/`_owning_skill_installed`/
`find_slot_markers` helpers reused from `validate_layout.py`, not reimplemented) is
still computed on every call and carried on every `OnboardingState` as a plain
boolean. It never influences `state` — only whether the frontend shows its dismissible
D20-init banner over `decisions_pending`/`steady_state` (see `SKILL.md`'s "Guided
setup" section). This is deliberate: `wizard_boxes.py` already degrades gracefully
when D20 was never run (`GuidelinesBox.initialized=False`, empty `resolved_paths` — a
normal empty state, not an error), so there was never a correctness reason to block a
screen on it, only a UX reason to mention it.

## 4. `GET /api/state` response shape

Session-gated, cheap (no box assembly — deliberately not folded into `/api/status`,
which assumes a constructible `LayoutSource` and would conflate two different failure
surfaces). Exact JSON (`wizard_onboarding_state.to_json_dict`):

```json
{
  "state": "layout_broken | needs_discover | decisions_pending | steady_state",
  "validate_ok": true,
  "validate_failures": [],
  "discovery_artifact_exists": true,
  "decision_counts": {"pending": 0, "staged": 0, "confirmed": 0},
  "d20_initialized": false
}
```

Note the dataclass field is `OnboardingState.name`, but the JSON key is `"state"` —
`wizard.js`'s `loadState()` reads `view.state`, not `view.name`.

## 5. Consequences for server startup and per-request handlers

`wizard_server.build_server()` no longer eagerly constructs a `LayoutSource` at
startup — doing so could raise once check 3 is no longer a startup gate, and a broken
layout must still let the process bind and serve the `layout_broken` screen rather than
`SystemExit`ing before opening a socket. Every handler that needs a `LayoutSource` now
calls `self._try_layout_source()` fresh, per request, early-returning (503 already
sent) on `None` rather than assuming one built once at startup is still valid. See
`wizard-picker-and-boxes.md` §1 for the read-path side of this same change.
