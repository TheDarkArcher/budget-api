---
name: accepted-screens-review-decisions
description: Maintainer decisions from the 2026-11-17 and 2026-11-18 screens review that are settled; don't re-raise them
metadata:
  type: project
---

Settled by the maintainer in the review of the API against the frontend
screens:

- Usage and impact counts on lookup lists, count sorting, the fuller
  transaction list (row shape, repeatable filters, `sort`, `q`) and 90-day usage
  ordering are deferred to Milestone 2. Pickers sort by name until then.
- No cascade count on archive or unarchive; the UI notice needs none.
- No unpaged lookup list; clients page through it (DESIGN.md 8.7). The
  per-item sizes list is the unpaged exception.
- Manual line ordering is Milestone 2.
- Archived-category links stay in place and still count for an edited
  transaction's link check.

**Why:** the maintainer reviewed each finding on 2026-11-17 and 2026-11-18 and
chose.
**How to apply:** don't raise these again unless the contract contradicts the
decision.
