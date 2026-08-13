---
name: cep-wizard
description: "Launch a local, localhost-only browser wizard for a project with ult-repo-layout installed (initialized or not) — guides an uninitialized or not-yet-discovered repo through Run Discover, then shows resolved layer/slot state through four labeled boxes and a directory picker, and lets you resolve pending layout decisions (confirm/skip/disable/pick-a-directory) and Apply them into context-config.yaml via ult-repo-layout's own confirm step. Do NOT use for headless/CI-only layout validation — use ult-repo-layout's discover/confirm-layers/--validate directly."
namespace: ult
version: 0.2.0
origin: ground-up
author: Pranay Mishra
maintainer: Pranay Mishra
adapted_from: ~
upstream_version: ~
released: 2026-08-08
tags: [utility, onboarding, browser, wizard, project-layout]
bundle: utilities
---

Read and follow the skill at `.github/skills/ult-cep-wizard/SKILL.md`.

**Hand-authored, not generator-owned:** unlike most prompts in this directory, this one
is not mechanically derivable from frontmatter alone. This skill isn't "chat message
in, one response out" — it's "run a terminal command, then interact in a browser for a
session" — so the steps below exist to carry that shape explicitly.

When invoked directly by an engineer:
1. Run `python .github/skills/ult-cep-wizard/scripts/wizard_server.py <repo_root>`
   in a terminal, passing the real project root explicitly (never inferred). Unlike
   Phase 0/1, the repo does **not** need to have run `ult-repo-layout init`/`discover`
   first — `wizard_preflight.py` now only requires `ult-repo-layout` to be *installed*;
   if it reports a missing-dependency error, that's the one thing to resolve (usually
   re-running `install.ps1`/`install.sh` without a narrow `--only` flag) before
   re-running step 1.
2. Open the one-time exchange URL the server prints in a browser (or hand it to the
   engineer if you're running headless/over SSH — the server never assumes it can open
   a browser itself). The link is single-use and expires after 30 minutes of idle time.
3. The page shows exactly one of four screens depending on the repo's current state —
   see `references/wizard-onboarding-state-machine.md` for the full table:
   - **Layout broken** — `validate_layout.py`'s own validation is currently failing;
     resolve what it reports (by hand, or by asking the engineer to) before anything
     else here is meaningful.
   - **Let's find this repo's layout** — no discovery artifact yet; click **Run
     Discover** (a real, in-process call to `discover_layers.run_discovery()` — safe,
     scans and proposes, writes nothing into `context-config.yaml` itself).
   - **Decisions** — walk each `PENDING`/`STAGED` field with the engineer
     (confirm/skip/disable/acknowledge/pick-a-directory via the picker below), then
     click **Apply** once every field is resolved — this is the only step that commits
     into `context-config.yaml`, via `ult-repo-layout`'s own `confirm_layers.py`.
   - **Steady state** — everything already confirmed; walk the four boxes (What, How,
     Guidelines, Trip-wire) and the directory picker with the engineer. For any box
     showing an empty-case content-scaffolding card, that card is a preview prompt for
     you (the agent) to act on in a separate turn — the wizard never writes content
     itself.
4. If a dismissible banner appears mentioning `ult-repo-layout init` hasn't run, that's
   informational only (affects Guidelines defaults) — it never blocks any of the above;
   point the engineer at `/ult-repo-layout init` if they want to clear it, then click
   Done to re-check.
5. Stop the server (Ctrl+C in the terminal) when the session is done. Nothing is left
   running in the background.

Do not reach for this skill for headless or CI-only validation — call
`ult-repo-layout`'s `discover`/`confirm-layers`/`validate_layout.py --validate`
directly for that instead.
