---
name: accepted-operation-id-decisions
description: Maintainer decisions on the DESIGN.md 8.8 operation id table (2026-11-23); don't re-raise
metadata:
  type: project
---

- The operation id rule in DESIGN.md 8.8 does not spell out irregular plural to
  singular conversions (such as `categories` to `category`). The maintainer
  declined to add them; the rule's own example `createItemCategory` is enough.
- A verb rule for non-GET paths that aren't resources is deferred until such an
  endpoint is planned (DESIGN.md only firms up the next milestone).

**Why:** the maintainer declined or deferred these in the 2026-11-23 re-reviews.
**How to apply:** don't raise plural handling or the verb rule again. Check only
that each planned endpoint matches exactly one row of the table, by its shape,
with the last row covering only `GET` paths.
