---
name: candidate-issues
description: Candidate issues found in reviews and how many reviews each has appeared in; remove an entry once the maintainer fixes or rejects it
metadata:
  type: project
---

Each entry is a count of the reviews it has come up in. Review each run on its
own merits; this list is not a checklist.

Open:

- `PayeeRequest.name` (and later request name fields) declares `minLength: 1`,
  but the server trims first, so a whitespace-only name passes the schema and
  is refused with a 422. The description says so and there is no `pattern`.
  Suggestion. Seen in 1 review (2026-11-26, payee create/get). The maintainer
  has planned a fix, so don't raise it again unless the planned fix isn't in
  the contract.
