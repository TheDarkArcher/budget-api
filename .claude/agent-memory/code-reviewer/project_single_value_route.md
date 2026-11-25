---
name: project-single-value-route
description: Repeated query parameters are rejected by SingleValueRoute in app/api/routing.py; every router needs it as route_class
metadata:
  type: project
---

Repeated single-value query parameters are refused by `SingleValueRoute` (app/api/routing.py). It swaps in a `QueryParams` whose `get` returns a `RepeatedParameter` marker, so FastAPI validation fails and `error_entry` in app/api/problems.py gives "Send this parameter only once.".

- FastAPI's `include_router` keeps each route's own class, so every `APIRouter` under `/api/v1` must set `route_class=SingleValueRoute` itself; `tests/test_routing.py` checks every v1 route.
- FastAPI reads list-typed params with `getlist`, so repeatable list parameters still work. Extra (undeclared) keys bypass `get`, which is harmless because they're ignored.
- Review a new router in app/api/v1/ for a missing `route_class`.
