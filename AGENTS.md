## Design Document

- `docs/DESIGN.md` is the design document for this project. It covers the project's goals, architecture, technologies, planned data model, API design and engineering practices
- Before making any code changes, or installing or using any technology for this project, the design document should be read and followed
- If a requested change to the database schema does not match the design document, ask which of these to do:
  - A) Update the design document to match
  - B) Abandon the request because it doesn't match the design document
  - C) Continue with the request without changing the design document
- If the design document is silent, ambiguous or conflicts with a request, ask before proceeding rather than guessing

## Project Structure

- The project uses an `app/` layout
- `docs/` - The project documents
- `tests/` - The project's test suites
- `migrations/` - The Alembic database migrations
- `scripts/` - The general utility scripts
- `app/api/` - Layer for handling API endpoints
- `app/services/` - Layer for the service business logic
- `app/repositories/` - Layer for interacting with data storage
- `app/database/` - Layer for connecting to the database
- `app/schemas/` - Pydantic models for the API's contract
- `app/core/` - Core settings and functions every layer can make use of
- To determine the database schema, read the migrations
- Don't create new packages or new files without being asked. Test modules for new code are exempt from this rule.

## Coding Conventions

- Type-hint every function and method, including their return types.
- Use `pathlib` for path management. Don't use `os.path`.
- Prefer f-strings over `str.format()` or `%` formatting.
- Prefer EAFP where an exception is the natural signal: handle it rather than checking conditions up front.
- Catch specific exceptions only. Never use a bare `except:` or silently swallow `Exception`.
- Write Google-style docstrings for every public function and method (tests and migrations are exempt).
- Validate request bodies with Pydantic models.
- Embrace idiomatic Python like comprehensions, generators, and decorators.
- Use the `logging` module. Don't use `print()` in app code.
- Use `Decimal` for money and quantities, never `float`.
- Match the naming, structure and comment density of the surrounding code. Don't add comments that restate the code.

## Database

- Always use bound parameters. Never build SQL with f-strings or string formatting.
- Never edit a migration that has already been committed; add a new one instead.
- Every migration must have a working `downgrade()`.

## Tests

- In test modules, order top-level code as: constants, helper classes, helper functions, fixtures, then tests.

## Quality Gates

- While in the process of working on an issue, only the tests related to that issue should be run. Once the issue has been finished, the full test suite should be run.
- Add or update tests for every change in behaviour.
- Before a task is done, `ruff check`, `ruff format --check`, `mypy` (strict) and the full pytest suite must pass. Run them all with `uv run poe check`.
- If an endpoint or schema changed, re-export `openapi.json` so the CI drift check passes.
- Don't skip, delete or weaken tests, or add `# type: ignore` or `# noqa`, to get the gates passing without asking first. Fix the code instead, unless asked to change the tests.

## Constraints

- Ask before adding any external dependency. Once approved, add it with `uv add` (`uv add --dev` for dev tools), never `pip install`.
- Preserve the signature and response shape of existing endpoints.
- Don't use blocking I/O inside `async` functions.
- Never hard-code secrets or connection strings; read them from settings.
- Only change what the request asks for. Mention unrelated issues instead of fixing them.
- When asked to review or go over something, propose changes and wait for approval before editing files.
- Declare a task done only after the gates pass and docstrings are updated.

## Git

- Don't commit or push unless asked.
- Never bump the version, create or move tags, edit released changelog sections, or push to `staging` or `production` unless asked. Branching and release rules are in the "Git workflow" and "Versioning" sections of `docs/DESIGN.md`.
- Limit the subject line to 50 characters or less
- Capitalize the subject line
- Do not end the subject line with a period
- Use the imperative mood in the subject line
- Any commits written must carry a `Co-Authored-By` trailer naming the model.

Good
```
Refactor subsystem X for readability
Update getting started documentation
Remove deprecated methods
Release version 1.0.0
Merge pull request #123 from user/branch
```

Bad
```
fixed bug with Y
changing behavior of X
more fixes for broken stuff in one of the subsystems
sweet new API methods
```

- Separate subject from body with a blank line
- Wrap the body at 72 characters, using as much of the line as possible while still ensuring words are not split across lines
- Use the body to explain what and why vs how. Just focus on making clear the reasons why the change was made in the first place: the way things worked before the change (and what was wrong with that), the way they work now, and why it was solved the way it was.

## Ignore

Treat everything in `.gitignore` as off-limits to read or edit, except
`tmp/`, which holds uncommitted working docs (e.g. milestone checklists)
and may be read and edited. On top of that, never open:

- Secrets and `.env` files (`.env.example` is allowed and must be kept up to date)
- Large data files unrelated to the current task
- Vendored or generated code

`openapi.json` and `uv.lock` are generated: never edit them by hand.
Regenerate them with `uv run poe export-openapi` and `uv lock`.
