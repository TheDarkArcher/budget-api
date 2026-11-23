---
name: openapi-conventions-test
description: What routes and tests/test_openapi_conventions.py must keep for operation ids, summaries, descriptions and required responses
metadata:
  type: project
---

tests/test_openapi_conventions.py checks the committed `openapi.json` against the rules in DESIGN.md's OpenAPI section.

**Why:** so the committed `openapi.json`, and the clients generated from it, stay consistent with DESIGN.md's OpenAPI section.

**How to apply:** flag a route or a change to tests/test_openapi_conventions.py that breaks these:
- Routes set `operation_id=`, `summary=` and a client-facing `description=` on the decorator, following the rules in DESIGN.md's OpenAPI section; the Google docstring stays for code readers.
- The test derives the required 422 only from query, header or body input, never from a path parameter alone, as [[openapi-problem-documentation]] explains.
