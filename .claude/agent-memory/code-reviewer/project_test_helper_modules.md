---
name: test-helper-modules
description: tests/ helper modules are top-level imports; the tests skill holds the test conventions; one user's record ids are a "world"
metadata:
  type: project
---

- The conventions for tests and test helpers, including registering an assert-bearing helper module for assert rewriting, are in `.claude/skills/tests/SKILL.md`. Review changed tests against it.
- tests/ has no `__init__.py`; helpers such as `tests/fakes.py` and `tests/problems.py` are imported as top-level modules (`from fakes import ...`, `from problems import ...`).
- `World` (one user's record ids) and `make_world` live in `tests/records.py`, built from its insert helpers; tests/conftest.py and tests/test_schema.py import both, and tests/test_sql_errors.py imports `World`. Call one user's set of record ids a "world"; flag a second name for the same idea. `make_world` inserts every kind of record except transactions and lines, so tests needing those add them (the `refusals` fixture in test_sql_errors.py does). The `alice` fixture, plain `make_world(connection, "Alice")`, is shared from tests/conftest.py.
