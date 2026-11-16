---
name: scripts-subprocess-and-test-conventions
description: How scripts/ call subprocess (S603/S607 noqa precedent) and how script tests import them
metadata:
  type: project
---

- ruff selects "S"; `scripts/build_label.py` (`# noqa: S603` and `# noqa: S607`) and `scripts/backups.py` (`# noqa: S603`) suppress it, each with a justifying comment. AGENTS.md says to ask the maintainer before adding any noqa.
- Tests import scripts as top-level modules (`from backups import ...`) via pytest `pythonpath = ["scripts"]` and mypy `mypy_path`.
- tests/conftest.py has a session-scoped `postgres` testcontainers fixture; script tests create scratch databases in it.
- Project targets Python 3.15 and postgres:18, so `except A, B:` (no parens) and pg_database.datlocale are valid; don't flag them.
- scripts/backups.py `COUNT_NON_EMPTY_SQL` and its tests in tests/test_backups.py are the agreed scope for "is the database empty". Anything they don't count is an accepted gap; don't flag it or suggest widening it.
- Review point for script code: cleanup that only catches the tool's own exception misses OSError and KeyboardInterrupt and can leave partial files behind. backups.py handles this; check new scripts for it.
