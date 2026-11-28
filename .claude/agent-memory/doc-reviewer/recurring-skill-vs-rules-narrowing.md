---
name: recurring-skill-vs-rules-narrowing
description: Skills that say "where the two differ, the rules win" must not narrow or restate a rule from AGENTS.md or DESIGN.md
metadata:
  type: feedback
---

Skills in `.claude/skills/` open by naming the AGENTS.md and DESIGN.md rules they follow and saying those rules win where the skill differs. When a skill moves rules out of AGENTS.md (as the `tests` skill did), check each sentence against both AGENTS.md and DESIGN.md.

**Why:** an earlier draft of the `tests` skill restated DESIGN.md's regression-test entry (mark, one-line comment, issue number) and narrowed "every bug fix" to "released code", which contradicts the rules it says win.

**How to apply:**
- The maintainer decided that skills follow DESIGN.md and AGENTS.md rather than update them, and that a rule of thumb (such as "a bug means one in released code") stays out of both; don't re-flag its absence.
- A convention that only a skill states, such as the `tests` skill's assertion, helper, naming and layout conventions, is that skill's own rule, not a narrowing.
- Flag a skill sentence that narrows or widens an AGENTS.md or DESIGN.md rule, or copies one that stays in the source; propose a link instead.
- Verify helper-module claims in the `tests` skill against `tests/*.py` (each opens with a docstring; only `problems` is registered for assert rewriting in `tests/conftest.py`).
