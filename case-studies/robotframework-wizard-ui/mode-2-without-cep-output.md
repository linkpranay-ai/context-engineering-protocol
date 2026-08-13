# User Stories: Lazy TypeConverter.languages for Libdoc performance

No context package found — proceeding without it.

## Actors

No specific actor named or implied — using generic actors.

- User
- Developer

## Stories

### US-001

As a Developer, I want `TypeConverter.languages` to be lazily initialized instead of eagerly constructed on every `converter_for()` call, so that code paths that never read `.languages` don't pay the construction cost.

Grounded in: bare feature description (no context package available)

### US-002

As a User, I want Libdoc's documentation generation to run quickly on large keyword libraries, so that I don't wait an unnecessarily long time to generate docs.

Grounded in: bare feature description (no context package available)

### US-003

As a Developer, I want the laziness change to not alter behavior for callers that already read `.languages`, so that fixing the performance issue doesn't introduce a regression elsewhere.

Grounded in: bare feature description (no context package available)
