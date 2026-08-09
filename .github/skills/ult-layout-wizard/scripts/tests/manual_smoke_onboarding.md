# Manual smoke test: brownfield onboarding journey (Phase 2, D24 §18.14)

Companion to the automated suites (`test_wizard_onboarding_state.py`,
`test_wizard_discover.py`, `TestApiState`/`TestDiscoverRoute` in
`test_wizard_server.py`) — this walks the same journey a real user would, over a real
browser and real HTTP, end to end: **never-initialized repo → guided Discover →
Decisions → Apply → steady-state**, plus the D20-banner human-in-the-loop step. Same
rigor as the Phase 1 write-path smoke test this session already ran for
`/api/stage`/`/api/apply` — this extends it to cover what's new in Phase 2, it doesn't
replace it. Run this after any change that touches `wizard_onboarding_state.py`,
`wizard_discover.py`, the `/api/state`/`/api/discover` routes, or the frontend state
router, before considering the change done.

## 0. Set up a throwaway fixture repo

Never run this against `context-engineering-oss` itself for steps 1-2 — those steps
run `discover`, which would write real files into this repo's own
`context-layout-discovery.md`. Use a scratch copy instead:

```
python -c "
import shutil, pathlib
src = pathlib.Path('.github/skills')
dst = pathlib.Path(r'C:\Users\pmishra\AppData\Local\Temp\claude\wizard-smoke\fixture')
dst.mkdir(parents=True, exist_ok=True)
shutil.copytree(src / 'ult-layout-wizard', dst / '.github/skills/ult-layout-wizard', dirs_exist_ok=True)
shutil.copytree(src / 'ult-repo-layout', dst / '.github/skills/ult-repo-layout', dirs_exist_ok=True)
"
```

The fixture needs `ult-repo-layout` installed (so preflight's one remaining check
passes) but **not initialized** — no `context-config.yaml`, no
`context-layout-discovery.md`, no `.layout-slots.yaml` markers. That absence is the
whole point of step 1.

## 1. `needs_discover` — first launch against an uninitialized repo

1. `python .github/skills/ult-layout-wizard/scripts/wizard_server.py <fixture_root>`
   from the fixture root. Confirm the server **binds and prints an exchange URL** —
   this is the headline Phase 2 behavior: the old preflight would have `SystemExit`ed
   here instead.
2. Open the printed `http://127.0.0.1:<port>/exchange?token=...` URL in a browser.
3. Confirm the page shows the **"Let's find this repo's layout"** screen (`#state-needs-discover`), not the boxes/decisions/picker layout — those sections should be
   invisible (`display: none` in the DOM), not merely empty. Since this fixture has
   never run `ult-repo-layout init` either, also confirm the **greenfield** intro
   renders here specifically (`#needs-discover-greenfield` visible,
   `#needs-discover-brownfield` `display: none`) — the paragraph explaining what
   `init` is and asks for, not the plain Discover-scan copy. §4 step 5 covers the
   brownfield variant.
4. Open devtools → Network, reload, confirm `GET /api/state` returns
   `{"state": "needs_discover", "discovery_artifact_exists": false, ...}`.
5. Click **Run Discover**. Confirm the button becomes disabled/shows a pending
   message while the request is in flight (not an instant flash).
6. Confirm the page transitions to the Decisions screen without a manual reload — the
   frontend should re-call `loadState()` after a successful `POST /api/discover` and
   route to whatever state that returns (`decisions_pending` on a repo with real
   pending fields).

## 2. `decisions_pending` → Apply → `steady_state`

1. Confirm the Decisions list shows real fields with real `allowed_verbs` buttons —
   this is unchanged Phase 1 UI, just reachable now without a pre-existing
   initialization step.
2. Resolve every field (any mix of CONFIRM/SKIP/DISABLE/ACKNOWLEDGE/CUSTOM), confirm
   the Apply button enables only once none remain `pending`.
3. Click Apply. Confirm HTTP 200, `config_changed: true`, and that both the boxes and
   decisions sections reload afterward.
4. Reload the page from scratch (fresh `GET /api/state`). Confirm it now reports
   `"state": "steady_state"` and the full boxes/picker UI renders exactly as it did
   before Phase 2 — the regression check that nothing here changed for an already-
   initialized repo.

## 3. `layout_broken`

1. Hand-corrupt the fixture's `context-config.yaml` (e.g. malformed YAML, or a value
   `validate_layout.py` rejects) and reload the page.
2. Confirm the page shows the **layout-broken** screen with the actual `FAIL` lines
   from `validate_layout.py --validate`, not a generic error and not a blank
   boxes/decisions layout.
3. Confirm `GET /api/state` returns `"state": "layout_broken"` with a populated
   `validate_failures` array, and that `/api/status` (if called directly) returns a
   503, not a 200 with empty boxes — a broken layout should never look like a normal
   empty one.
4. Fix the corruption, reload, confirm the page recovers on its own (no server
   restart needed) — `compute_state` re-reads disk on every call.

## 4. D20 banner (human-in-the-loop recheck)

1. From a `decisions_pending`/`steady_state` fixture that has never run
   `ult-repo-layout init` (no `.layout-slots.yaml` markers, no `project_layout` key),
   confirm the dismissible banner appears pointing at `/ult-repo-layout init`.
2. Click **Dismiss**. Confirm it disappears and does not reappear on reload within the
   same session (session-scoped, not permanently silenced across restarts — check the
   actual dismissal semantics in `wizard.js` if this assertion needs updating).
3. Reload without dismissing; instead hand-write a `.layout-slots.yaml` marker for any
   `SLOT_REGISTRY` entry into the fixture (simulating a real `init` run), then click
   **Done**. Confirm this triggers a real `GET /api/state` re-check — not a
   self-report — and the banner disappears because `d20_initialized` is now `true`.
4. Confirm at every point in this section that the *screen itself* (boxes/decisions
   vs. any other state) never changed because of the banner — it's additive only.
5. `needs_discover` intro-copy split, brownfield side (§1 step 3 already checked the
   greenfield side): reuse §1's fixture — still `needs_discover`, still showing the
   greenfield intro — and hand-write a `.layout-slots.yaml` marker for any
   `SLOT_REGISTRY` entry (same technique as step 3 above), without running Discover.
   Reload; confirm the state is still `needs_discover` (no artifact yet) but the intro
   has flipped to **brownfield** (`#needs-discover-brownfield` visible,
   `#needs-discover-greenfield` hidden) — today's plain "hasn't been discovered yet"
   copy. Confirm the **Run Discover** button and its behavior are identical either
   way — only the intro paragraph above it changes.

## 5. `/api/discover` guard: staged-decision protection

1. From `decisions_pending`, stage (but do not Apply) at least one decision.
2. Click **Re-run Discover…**. Confirm the UI surfaces a specific warning naming the
   at-risk staged section(s) (`at_risk_sections` from the 409 response) rather than a
   generic error or a silent proceed.
3. Confirm cancelling leaves the staged decision untouched (`GET /api/decisions` still
   shows it as `staged`).
4. Confirm explicitly forcing the re-run discards exactly the sections that were
   staged (and no others), and that the response's `discarded_staged_sections` matches
   what the UI reported before the confirm.

## 6. Regression check against the real repo

Finally, launch the wizard against `context-engineering-oss`'s own checkout (already
`steady_state`) and confirm the page looks and behaves identically to before this
Phase 2 work — zero visible change for a repo that was already fully set up. This is
the one step that's safe to run against the real repo directly, since it never touches
Discover.

## Cleanup

Delete the scratch fixture directory from step 0; nothing under
`context-engineering-oss` itself is touched by steps 1-5.
