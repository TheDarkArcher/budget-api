---
name: test-helper-modules
description: tests/ helper modules (fakes.py, problems.py) are top-level imports; helpers containing assert need register_assert_rewrite; duplicated caplog check
metadata:
  type: project
---

- tests/ has no `__init__.py`; helpers such as `tests/fakes.py` and `tests/problems.py` are imported as top-level modules (`from fakes import ...`, `from problems import ...`).
- pytest only rewrites asserts in test modules, conftest.py and modules passed to `pytest.register_assert_rewrite`. A tests/ helper module that contains `assert` must be registered in conftest.py, as `problems` is (`pytest.register_assert_rewrite("problems")`). Without that, a failure shows a bare `AssertionError` with no value introspection. Flag a new assert-bearing helper that isn't registered. `fakes.py` has no asserts, so it needs no registration.
- Both tests/test_problems.py and tests/test_health.py check the logged exception with the same `any(record.exc_info is not None and ... in str(record.exc_info[1]) for record in caplog.records)` expression. Flag a third copy; it belongs in a shared helper in tests/problems.py.
