---
name: accepted-transactions-createdat
description: Accepted trade-off - transactions don't expose createdAt; the documented sort order is enough to place a new row
metadata:
  type: project
---

The maintainer rejected exposing `createdAt` on transactions (2026-11-17).
DESIGN.md's `GET /transactions` row (API Design) says "Newest first: by
`occurredOn`, then by creation time", which already tells a client where a new
transaction goes: first within its date.

**Why:** clients don't need to re-sort transactions themselves, so the field
would add nothing a client uses.
**How to apply:** don't raise a missing `createdAt` while the `GET /transactions`
row keeps the creation-time tie-break; re-evaluate if that sort rule changes.
