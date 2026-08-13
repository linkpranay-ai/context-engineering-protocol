**Context package(s):** libdoc-lazy-languages_user-story_20260813@b0489975

# User Stories: Lazy TypeConverter.languages for Libdoc performance

Context package consulted: libdoc-lazy-languages_user-story_20260813@b0489975 (9 context_items across 2 aspects — root cause, and Libdoc's call path into it).

## Actors

- Robot Framework core maintainer/contributor (implied by `context_items` describing internal `TypeConverter`/`Languages` construction behavior and the real upstream fix commit — ctx_001, ctx_004, ctx_006, ctx_009)
- Libdoc user documenting a large keyword library (implied by ctx_002/ctx_003/ctx_006's description of Libdoc's per-argument-type doc-generation loop, and ctx_006's real bug report from a 10,000+-keyword library)

## Stories

### US-001

As a Robot Framework core maintainer, I want `TypeConverter.languages` to be lazily initialized instead of eagerly constructed in `__init__`, so that callers that never read `.languages` (like Libdoc) don't pay the cost of building a `Languages` instance for nothing.

Grounded in: `ctx_001`, `ctx_004`, `ctx_008`, `ctx_009`

### US-002

As a Libdoc user documenting a large (1,000+ keyword) dynamic library, I want doc generation to not construct one throwaway `Languages` instance per documented argument type, so that Libdoc's run time doesn't roughly double on big libraries the way issue #5254 reported.

Grounded in: `ctx_002`, `ctx_003`, `ctx_006`, `ctx_007`

### US-003

As a Robot Framework core maintainer, I want confidence that both real Libdoc call sites (`TypeDoc.for_type` and `_get_type_docs`) keep working correctly once `TypeConverter.languages` becomes lazy, so that the fix doesn't silently break doc generation on either path.

Grounded in: `ctx_005`

### US-004

As a Robot Framework core maintainer, I want assurance that the execution engine's own use of `TypeConverter` (which always passes a real `Languages` instance already) is unaffected by making the None-default path lazy, so that runtime argument-conversion behavior doesn't regress.

Grounded in: `ctx_009`

### US-005

As a Robot Framework contributor picking up this performance issue, I want to know this exact fix already exists in the project's real history (commit `6d0c6a4630bf6b906253c802e2bf5b266a1a8893`, "Fixes #5254", reporting "roughly 50% performance enhancement with really big libraries") and postdates this pinned `v7.1.1` clone, so that this task is understood as reproducing and applying a known, already-validated fix rather than inventing one from scratch.

Grounded in: `ctx_006`
