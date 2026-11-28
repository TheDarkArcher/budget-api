---
name: tests
description: Conventions for this repository's pytest tests - which behaviour to test and in which layer, comparing whole bodies, the shared helpers in tests/, naming, module order and regression tests. Use whenever writing, changing or reviewing a test or a test helper.
---

# Writing tests

What to test, and how regression tests are written, is set by the Tests section of `AGENTS.md` and the Testing section of `docs/DESIGN.md`. This skill follows them; where it differs from either, they win. The conventions for assertions, helpers, names and module layout are this skill's own.

## What to test
- Before writing a test, name the rule in `docs/DESIGN.md` it covers and the layer that enforces it: the rule's *Enforced in* note, or for a rule without one, the layer its section describes. If no rule covers the behaviour, leave the test out, or ask whether the design should state it.
- Test each rule in the layer that enforces it, with the kind of test the Testing section describes for that layer, covering only what that layer decides.
- Apply the same check to a suggestion, from a reviewer or anyone else, to add coverage.
- Write a regression test as the Regression tests entry in the Testing section describes. Put the mark on the test, since pytest ignores marks on fixtures.

## Assertions
- Compare a response body whole with `==`, so a failure shows every differing, missing and extra member at once.
- Strip values that can't be predicted with a helper rather than inline: `without_error_details` for Pydantic's error messages, `with_parsed_archive_time` for archive times. A new kind of unpredictable value gets a helper that checks the value is present, and of the right type where that matters, then removes or parses it.
- Check fields one by one only when no strip helper can work, and say why in a comment.
- The OpenAPI document is the exception: a test checks the parts of it that the test covers.

## Shared helpers
Reuse a shared helper before writing a value or check out by hand. The shared helpers are the modules in `tests/` other than the `test_` modules, and the fixtures in `tests/conftest.py`; each module's docstring says what it is for. A new helper module opens with a docstring like theirs.

When the same value, query or check is written out a second time, move it into a helper: in the module when only that module uses it, or in a shared helper module when several modules use it, or every resource will.

A helper module that uses `assert` is registered in `tests/conftest.py` with `pytest.register_assert_rewrite`, so its failures show the compared values.

## Names
- A test of an error names the problem it returns, such as `..._returns_not_found_problem` or `..._returns_validation_problem`, since several problem types share a status. Where one error wins over another, the name says so with `..._even_if_...`.
- A helper's name says what kind of value it returns: `expected_...` for a value a test expects, `..._count` for a count.

## Module layout
Order a test module's top-level code as constants, helper classes, helper functions, fixtures, then tests. A constant built from a helper class follows that class.

Split a module whose tests fall into more than one group into sections. A module whose tests form one group has no banners, whatever else it holds.

- A banner opens each section. Its title has three spaces of padding on each side, and its `=` lines are as wide as the title line:

  ```python
  # ===============
  # |   Repeats   |
  # ===============
  ```

- Put two blank lines before and after a banner, or one before it when it follows the imports.
- A `Probe …` section comes first when the module has probe routes. It holds the module's constants, probe models and probe routes; the order above applies within each section.
- A `Helpers and fixtures` section follows. When the module has no `Probe …` section, it also holds the constants.
- Each group of tests then has its own section.
