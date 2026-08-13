---
name: cep-wizard
description: Launch a local, localhost-only browser wizard for a project with ult-repo-layout installed (initialized or not) — guides an uninitialized or not-yet-discovered repo through Run Discover, then shows resolved layer/slot state through four labeled boxes and a directory picker, and lets you resolve pending layout decisions (confirm/skip/disable/pick-a-directory) and Apply them into context-config.yaml via ult-repo-layout's own confirm step. Do NOT use for headless/CI-only layout validation — use ult-repo-layout's discover/confirm-layers/--validate directly.
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
tier: read
---

# ult-cep-wizard

**Status: Phase 0 (read) + Phase 1 (write) + Phase 2 (guided brownfield onboarding)
complete (D24).** A thin, user-launched, localhost-only local server that reads a
project's resolved `ult-repo-layout` state through four labeled boxes (What, How,
Guidelines, Trip-wire) and a server-rendered directory picker, and lets you resolve
each `PENDING` layout decision `discover` left behind — confirm the default, pick a
custom directory, skip, disable, or acknowledge — and Apply everything staged into
`context-config.yaml` in one step. The core rule is **wizard-proposes, CLI-commits
(§18.3)**: the wizard only ever edits *decision lines* in
`context-layout-discovery.md`; the actual commit always goes through
`ult-repo-layout`'s own `confirm_layers.run_confirm()`, called in-process, never
reimplemented. As of Phase 2, the server also always binds — even against a project
that hasn't discovered its layout yet, or whose layout config is currently broken —
and guides you through getting there instead of refusing to start; see "Guided setup"
below. See [`references/wizard-security-model.md`](references/wizard-security-model.md),
[`references/wizard-picker-and-boxes.md`](references/wizard-picker-and-boxes.md),
[`references/wizard-write-path.md`](references/wizard-write-path.md), and
[`references/wizard-onboarding-state-machine.md`](references/wizard-onboarding-state-machine.md)
for the full design; design decision D24 in
[`references/design-scratchpad-glossary.md`](../../../references/design-scratchpad-glossary.md).
The docs viewer described below (top bar + in-app `PROTOCOL.md`/`README.md`/case-study
rendering) is also part of D24; its routes' security model is in
[`references/wizard-security-model.md`](references/wizard-security-model.md)'s §8.

## Prerequisite

This skill only requires `ult-repo-layout` to be **installed** in the target repo
(`SKILL.md` + `scripts/validate_layout.py` present) — it no longer requires the repo to
already be initialized; that's now a guided in-browser step, not a precondition. It is
still a second-step tool relative to `ult-repo-layout` itself, not a replacement for
it — see [`ult-repo-layout`'s own `SKILL.md`](../ult-repo-layout/SKILL.md).
`scripts/wizard_preflight.py` enforces the one remaining check: no socket opens and no
token is minted until `ult-repo-layout` is found installed.

## Guided setup

Every launch computes a fresh onboarding state and shows exactly one matching screen —
see [`references/wizard-onboarding-state-machine.md`](references/wizard-onboarding-state-machine.md)
for the full table and reasoning:

- **`layout_broken`** — `validate_layout.py`'s own validation currently fails; the
  wizard shows the failure lines and stops there rather than guessing at broken state.
- **`needs_discover`** — the repo validates cleanly but has no discovery artifact yet; a
  guide-only intro plus a real **Run Discover** button (`POST /api/discover`) drives
  `ult-repo-layout`'s own `discover_layers.run_discovery()` in-process. The intro copy
  itself has two variants, picked by `d20_initialized` (below): a genuinely greenfield
  repo (never ran `init`) sees a guide-only explanation of what `init` is and asks for,
  plus a note that Discover can run before or after it; a repo that's already run
  `init` sees today's plain Discover-scan explanation. Either way the Run Discover
  button itself is shared and unaffected — the split is guide copy only.
- **`decisions_pending`** — an artifact exists with at least one field still
  pending/staged; today's existing Decisions UI, described above.
- **`steady_state`** — everything is confirmed; the full boxes/decisions/picker
  experience.

Whether `ult-repo-layout init` has ever been run is tracked separately
(`d20_initialized`) and never changes which screen above renders — on
`decisions_pending`/`steady_state` it shows a small, dismissible banner pointing at the
`init` command with a concrete checklist of what it asks (project name + description,
optional workspace-root opt-in), with a Done button that re-checks disk rather than
trusting a self-report; on `needs_discover` it picks the intro variant described above.

## Launching

```
python .github/skills/ult-cep-wizard/scripts/wizard_server.py <repo_root>
```

`<repo_root>` is a required, explicit argument — never inferred from the current
directory, since the wizard's entire path-containment security model is relative to
it. The server prints the resolved absolute root and a one-time exchange URL to the
console; open that URL in a browser (or copy it over from a headless/SSH/WSL session —
the server never assumes it can open a browser for you). The link expires after a
single use or 30 minutes of idle time, whichever comes first; closing the terminal (or
Ctrl+C) stops the server. Nothing is left running in the background.

## What it shows

- **What / How boxes** — the resolved paths for the What-L2/L1 and How-L2/L1 layers
  (union of always-on L2 and opt-in L1), read fresh from `context-config.yaml` on
  every request.
- **Guidelines box** — the `compiled_guidelines` slot's resolved path and whether
  `compiling-project-guidelines` is installed.
- **Trip-wire box** — a read-only summary from `decision_ledger.py`'s `show`, and
  whether `ult-institutional-memory-distill` is installed.
- **Picker** — a GET-only, server-rendered directory browser scoped to the repo root,
  with symlink/junction/UNC/OneDrive-placeholder-aware containment so it can never be
  walked outside that root. Still browse-only on its own; picking a directory *for* a
  decision below is a separate, explicit action.
- **Decisions list + Apply** — every `PENDING` decision line `discover` left in
  `context-layout-discovery.md`, with a button per offered verb
  (`CONFIRM`/`CUSTOM`/`SKIP`/`DISABLE`/`ACKNOWLEDGE`); `CUSTOM` hands off to the picker
  above. Staging a verb only edits the decision line — nothing is committed until
  Apply, which calls `ult-repo-layout`'s own `confirm_layers.run_confirm()` to write
  `context-config.yaml`. See
  [`references/wizard-write-path.md`](references/wizard-write-path.md).
- **Empty-case content cards** — for a What/How box with no real content on disk yet
  (or an uninitialized Guidelines box), a copy-button "run this yourself" prompt block
  for your coding agent to write the content in place. Still preview only — no route
  writes that content on the wizard's behalf; the write path above only ever commits
  *layer paths*, never layer content.

## Docs viewer

A top bar (CEP logo + inline nav) sits above the boxes/decisions view on every screen.
Clicking **Protocol**, **README**, or **Case Studies** fetches CEP's own project docs
and renders them into a full-width in-page overlay — not a real navigation; the
wizard's exchange-token URLs are single-use, so this stays entirely client-side inside
the one already-authenticated page load, with a close control returning to the normal
view. A fourth nav entry, **Guide & FAQ**, is present but disabled (`title="coming
soon"`) — a reserved slot for a user-guide/FAQ doc that doesn't exist yet.

- `PROTOCOL.md` and `README.md` render directly; **Case Studies** renders
  `case-studies/README.md` itself — the real landing doc, not a client-built index —
  so it's automatically current with whatever's published there. Every relative
  Markdown link inside it (to an individual `case-studies/*/CASE-STUDY.md`, to
  `SYNTHESIS.md`/`TEMPLATE.md`, or to a heading anchor in `PROTOCOL.md`/`README.md`)
  becomes a real in-app navigation; a link to something outside the wizard's doc
  corpus (e.g. `references/reproducibility-guide.md`) falls back to a real link at the
  project's public GitHub URL, opened in a new tab so it never dead-ends the overlay.
  Case-study titles come from each file's leading `# Case Study: ...` H1, falling back
  to the directory slug for the one file that has no H1.
- Markdown is converted with a small hand-rolled, stdlib-only renderer
  (`wizard_markdown.py`) sized to what these docs actually use — headers (with
  GitHub-style anchor `id`s for `#fragment` links), fenced code blocks, lists, tables,
  inline formatting/links/images, blockquotes, and a bounded raw HTML passthrough for
  README's centered hero image and badge row. Not a general CommonMark implementation.
- Docs are read from **the wizard's own install location**, not `<repo_root>` (the
  project being onboarded) — this is a generic tool that may run against any repo, but
  `PROTOCOL.md`/`README.md`/case studies are CEP's own docs. A future bare install
  missing these files degrades gracefully: the nav simply omits what isn't found,
  never a 500.
- Backing routes: `GET /api/docs` (list), `GET /api/docs/{id}` (one doc, closed-set —
  `{id}` is a dict-lookup key, never a filesystem path), and
  `GET /api/docs-assets/{rel_path}` (serves a doc's own referenced images, e.g.
  README's hero SVG — this one *does* take a client-supplied path and is
  containment-checked accordingly). Full security model in
  [`references/wizard-security-model.md`](references/wizard-security-model.md)'s §8.

## Do NOT use for

- Headless/CI-only layout validation — call `ult-repo-layout`'s
  `discover`/`confirm-layers`/`validate_layout.py --validate` directly; this wizard is
  a browser session, not a CI-suitable command.
- Running `discover` itself, registering a new path-slot, or writing any layer
  *content* — those stay `ult-repo-layout`'s (and your coding agent's, via the
  empty-case cards) job. This skill's write path only ever resolves decisions
  `discover` already surfaced and commits the resulting *paths* — it never invents a
  new decision line, never scans the filesystem for candidates on its own, and never
  writes What/How/Guidelines content itself.
- Handing selected content back to a calling process (the "paste-back" mode, §18.6) —
  not built by this plan; see below.

## What's next

- **Greenfield (`init`) flow** — addressed at the guide-only level this skill is
  realistically capable of: the `needs_discover` screen's intro copy and the
  `d20_initialized` banner both give a genuinely greenfield repo a concrete
  explanation of what `init` is and asks for (project name + description, optional
  workspace-root opt-in). What remains permanently out of scope, not deferred: running
  `init`/`reconcile` *from* the wizard server. Neither has a callable Python function —
  they exist only as conversational prose in `ult-repo-layout/SKILL.md` requiring
  free-text answers (`init`'s `project_name`/`description`) or an explicit
  "never guess by name similarity" open-ended question (`reconcile`'s no-marker-found
  case) that a fixed UI form cannot honestly ask. This skill points at those commands;
  it does not — and should not — reimplement them.
- **Paste-back content-handoff mode (§18.6)** — a different flow for handing
  wizard-selected content back to a calling process. Explicitly out of scope for the
  write path above; a distinct, later deliverable.
