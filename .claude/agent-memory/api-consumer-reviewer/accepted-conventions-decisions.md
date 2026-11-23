---
name: accepted-conventions-decisions
description: Maintainer decisions on DESIGN.md 8.7 Conventions and 8.9 Errors wording (2026-11-24); don't re-raise
metadata:
  type: project
---

- Money is a sub-bullet of Decimal numbers in 8.7, above the rule that all
  other decimal numbers drop trailing zeros.
- A request decimal such as `"5."` is not accepted (a digit is required on each
  side of the decimal point).
- Paging can't be turned off; clients page through every list.

**Why:** the maintainer stated these as deliberate when asking for the
2026-11-24 review of the Conventions and Errors streamlining.
**How to apply:** don't suggest moving the money rule, accepting `"5."` or
adding an unpaged mode.

Declined later on 2026-11-24 (don't re-raise):

- The retry consequence of "Only successful creates are stored" (a failed
  create can be corrected and retried with the same key) stays unstated.
- The error-order item 5 sentence (a valid PUT on an archived record returns
  409 whatever its references or names) stays dropped.
- Conventions states rules without status codes; the `/problems/validation`
  row in 8.9 covers them.

Fixed on 2026-11-24 (current in DESIGN.md): the 8.8 409 and 422 rows read
"Any 409/422 problem type in Errors", and the 8.9 Format bullet says a
failing readiness check returns the health body, not a problem.
