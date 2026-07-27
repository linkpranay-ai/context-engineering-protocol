# How a consuming skill should consume COMPILED-GUIDELINES.md

Any skill that reads, writes, modifies, reviews, or judges project code/tests should follow this
before doing that work:

1. Resolve the `compiled_guidelines` path-slot via `ult-repo-layout/SKILL.md`'s
   "Path resolution algorithm (§15.5 + §16.2)" — `starter_kit/project_guidelines/COMPILED-GUIDELINES.md`
   is its pre-D21 default; `{workspace_root}/cache/project-guidelines/COMPILED-GUIDELINES.md`
   if `layout.workspace_root` is set (D20 Phase 2, D21 §16.4). Check whether a
   file exists at that resolved path.
   - **Not present:** proceed exactly as you normally would. Don't ask the user to create one.
   - **Present:** read it fully. Its own "How consuming skills should use this file" section defines
     how to interpret its Global vs. Scoped sections — follow that.

2. As you identify which files/paths/components your task touches, the MOST SPECIFIC matching
   "Scope:" section governs that area and overrides both "Global" in the file and your own
   generic defaults wherever the two disagree. Fall back to "Global" only where nothing more
   specific matches.

3. State, in one line, which guidance you used and where:
   "Project guidance applied: <scope label> for <paths>; Global for <other paths>"
   — or "No compiled project guidelines found — using default conventions" if the file is absent.

4. Staleness nudge (cheap, non-blocking): if any source file listed in the compiled file's
   header has a newer modification time than the compiled file itself, mention it in one line
   ("<source> looks newer than the compiled guidelines — consider re-running
   /ult-compile-guidelines") and continue.

5. Write-back (lightweight, optional): if while doing your work you notice something
   guideline-relevant that this file doesn't cover — a new lint rule, a convention that appears
   to have drifted from what's documented, anything another skill working in this project would
   want to know — append one dated, attributed line to `## Recent Observations (pending
   compile)` in `COMPILED-GUIDELINES.md` (creating the section if it's absent). Non-blocking, no
   user prompt: it's an inbox for the next `/ult-compile-guidelines` run to triage.
   `ult-context-generate/SKILL.md` Step 9.5 is a structured instance of this same contract — it
   persists a human's already-made decision at its Step 9 approval gate, rather than an
   incidental observation.

---

This file is the single source of truth for "how does a consuming skill read the compiled
guidelines file." It is referenced by a one-line pointer from each code-facing skill's own
`SKILL.md`/`.prompt.md` rather than copied into each one — so the protocol is written, reviewed,
and updated in exactly one place. If you're changing this protocol, you don't need to touch the
individual skills; every one of them picks up the change on its next invocation automatically.

It is colocated with `compiling-project-guidelines/SKILL.md` — the skill that produces the
artifact this file describes how to consume — so anyone changing one sees the other and keeps
them in sync.
