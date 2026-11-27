---
name: candidate-issues
description: Candidate issues found in reviews and how many reviews each has appeared in; remove an open entry once the maintainer fixes it; rejected and settled items stay under Accepted
metadata:
  type: project
---

Each open entry carries a count of the reviews it has come up in. Review each
run on its own merits; this list is not a checklist.

Open:

- `PayeeRequest.name` (and later request name fields) declares `minLength: 1`,
  but the server trims first, so a whitespace-only name passes the schema and
  is refused with a 422. The description says so and there is no `pattern`.
  Suggestion. Seen in 1 review (2026-11-26, payee create/get). The maintainer
  has planned a fix, so don't raise it again unless the planned fix isn't in
  the contract.
- Transaction category PUT and `type`: whether the PUT body declares `type`
  (DESIGN.md says only that `type` can't be changed by a PUT and that a
  different one is a 422), and whether an omitted `type` is refused or keeps
  the stored value. The design is silent on both. The maintainer will settle
  it when transaction categories are built. Warning. Seen in 3 reviews on
  2026-11-27, of the 8.7 "Request bodies" and "Updates" rules. Raise it only
  if transaction categories are built without an answer.

Accepted (don't raise again), from the 2026-11-27 re-review of the 8.7
"Request bodies" and "Query parameters" rules:

- Declined: listing the refused read-only response fields (`id`, `archivedAt`,
  `type`, `total`, nested references) in the design; the client maps a fetched
  record to a request itself.
- Declined: separate POST and PUT line schemas for transactions.
- Settled: `additionalProperties: false` on closed request schemas comes from
  Pydantic's `extra="forbid"` and is already in `openapi.json` (for example on
  `PayeeRequest`), so don't ask for it in the design.
- Settled: the `errors` pointer names each unknown field, and the status and
  problem type are `/problems/validation` (422) through the Conventions
  catch-all.
