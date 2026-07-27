# `reconcile --adopt-workspace-root` — per-slot decision tree (D21 §16.6)

**Advisory/dry-run only: moves nothing, writes no marker.** For an
**existing** project that just added `layout.workspace_root: <path>` to
`context-config.yaml` and wants to know what changes, for every registered
slot:

- **Already has a marker (anywhere)** → report "`<slot>` — unaffected,
  already has a marker at `<marker path>`" (§16.11/S16) and move on. A
  marker always wins over `workspace_root`, so adopting it changes nothing
  for this slot.
- **No marker, content exists at BOTH the pre-D21 default AND the
  `{workspace_root}/<leaf>` default** → flag as the S18 conflict (§16.11/M5)
  — "`<slot>` has content at both `<pre-D21 path>` and `<workspace_root
  path>` — resolve this duplication by hand before adopting `workspace_root`
  for this slot" — and offer **neither** option below for this slot.
- **No marker, content exists only at the pre-D21 default** → report both
  human-actioned options, pick one:
  - (a) write a marker at the *current* (pre-D21) location, pinning this
    slot there indefinitely (same effect as `workspace_root` never having
    been set, for this slot only); or
  - (b) print the `mv`/`git mv` command to relocate the slot's content to
    `{workspace_root}/<leaf>` — after running it, the existing zero-marker
    `reconcile` flow (`SKILL.md`'s `reconcile` step 3, unchanged) writes the
    marker at the new location on the next run.
- **No marker, nothing exists yet at either location** → report
  "`<slot>` — no content yet; future writes will use
  `{workspace_root}/<leaf>` (its new resolved default)." No action needed.

The same report additionally lists each of the 5 starter-kit drop-zones (see
`references/starter-kit-dropzones.md`): current path (`starter_kit/<leaf>/`)
vs. `{workspace_root}/inputs/starter-kit/<leaf>/`, with the same `mv`/`git mv`
suggestion (option (b) shape) if the human wants to re-root a drop-zone's
content. Drop-zones have no marker mechanism, so option (a) doesn't apply to
them — after a human-run `mv`, the next `init`/`reconcile` simply regenerates
`.pointer.md` at the new location (it already follows "current location," per
that section).

Whichever option the human picks, **`--adopt-workspace-root` itself takes no
further action** — the marker write (option a) or the next `reconcile` pass
(after option b's `mv`) is what actually changes state, using D20's
already-shipped primitives. This is intentional: §15.7 never auto-moves
content, and `workspace_root` changes *defaults only* (§16.2/S16).
