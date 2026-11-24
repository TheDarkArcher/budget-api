---
name: openapi-problem-documentation
description: How error responses are documented as problem+json in OpenAPI (documented_problem, BudgetAPI.openapi transform, no 422 on path-only operations) and what changes to it must keep
metadata:
  type: project
---

`documented_problem(description)` in app/api/openapi.py builds a FastAPI `responses` entry with `model: Problem` and content key `application/problem+json`. FastAPI also writes the schema under the route's own media type (`application/json`), so `document_problem_responses` moves it, and replaces FastAPI's automatic `HTTPValidationError` 422 with the `Problem` schema. `BudgetAPI.openapi()` in app/main.py runs the transform once, guarded by `openapi_schema is None`. The maintainer chose this design (move after generation, a FastAPI subclass rather than assigning `app.openapi`); don't suggest replacing it.

**How to apply:** a change to the transform, or a route outside `/api/v1`, must keep these properties; flag one that breaks them:
- The transform is idempotent and tolerates a documented problem with no `application/json` key (a non-JSON `response_class`).
- It reads only HTTP-method keys of a path item, not `parameters`, `summary` and the like.
- Every `$ref` resolves: the `Problem` component must exist wherever a `$ref` to it appears, so when no operation's `model: Problem` defines it, the transform adds it (`add_problem_schemas`), in the same shape FastAPI generates.
- Members the API leaves out (`errors`, `pointer`, `parameter`) are documented as optional, never nullable; `type` is required.
- 409 and 422 responses use `ProblemError` or a domain error, never `HTTPException`: the `HTTPException` handler sends `about:blank`, while the documented `type` promises a named type for 409 and 422.
- A path-only operation (`has_only_path_input`: no `requestBody`, every parameter `in: path`) documents no 422, because a malformed path id returns 404. Flag a change that gives such an operation a 422, or removes the 422 from one with a body, query or header input. A declared problem+json 422, such as an idempotency mismatch, is never removed.
