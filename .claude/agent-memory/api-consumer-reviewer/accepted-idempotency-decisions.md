---
name: accepted-idempotency-decisions
description: Maintainer decisions on the Idempotency bullets in DESIGN.md 8.7 and the `Idempotency-Key` header description (2026-11-25); don't re-raise
metadata:
  type: project
---

Declined by the maintainer on 2026-11-25 (don't re-raise):

- A repeated `Idempotency-Key` header's 422 isn't stated in DESIGN.md: the
  problem types table gives `/problems/validation` for any Conventions rule
  without a type of its own.
- No replay marker: a repeat returns the original response, a retrying client
  has little use for the difference, and a marker can be added later without
  breaking clients.
- No stated limit on the wait for a running first request: it depends on the
  `database_statement_timeout` setting, and a repeat that times out gets a 500
  and is safe to send again.
- The 1-255 key limit's counting (characters or bytes) stays unstated: it only
  matters for non-ASCII keys near 255.
- No OpenAPI `example` on the header: "Try it out" in `/docs` would send the
  same example key every time, giving replays or mismatches.

**Why:** the maintainer agreed to decline these in a re-review.
**How to apply:** don't raise them again unless the contract contradicts them.
