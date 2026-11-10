# Budget Tracker API

Budget Tracker is a web app that gives you a clear picture of where your
money goes. It records income and expenses, organises them into categories,
and shows how spending changes over time.

This repository is the backend: the REST API and its PostgreSQL database.
The frontend lives in a separate repository *(link once it exists)*. Goals,
architecture, data model and roadmap are in the
[design document](docs/DESIGN.md).

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Compose for containerisation
- [uv](https://docs.astral.sh/uv/) for Python version and package management

## Quick start

```bash
cp .env.example .env
docker compose up -d
docker compose run --rm migrate
```

The API is now at <http://localhost:8000>:

- <http://localhost:8000/docs> shows the interactive API docs.
- <http://localhost:8000/health/ready> should return `"status": "ok"`.

Code changes in `app/` reload automatically. Stop everything with
`docker compose down`; add `-v` to also delete the database.

## Configuration

All settings are environment variables, read from `.env`.
[`.env.example`](.env.example) lists every one with a comment explaining it.

If port 5432 is already in use on your machine (for example by a local
PostgreSQL install), set `POSTGRES_HOST_PORT` to a free port such as `5433`,
and use the same port in `DATABASE_URL`.

## Running the API without Docker

The database still runs in Docker; the API runs directly on your machine:

```bash
uv sync
docker compose up -d db
uv run poe migrate
uv run poe dev
```

## Tests and code quality

```bash
uv run poe check    # everything: lint, formatting, types and tests
uv run poe lint     # ruff and mypy only
uv run poe test     # tests with coverage; extra arguments go to pytest
uv run poe format   # fix formatting and auto-fixable lint issues
uv run poe          # list every task
```

The tests start their own PostgreSQL container, so Docker must be running.
To run some of the tests, pass pytest arguments, e.g.
`uv run poe test tests/test_health.py -k ready`.

## Database migrations

Migrations are hand-written SQL, managed with Alembic. See
[`migrations/README`](migrations/README) for creating one.

```bash
uv run alembic revision -m "Add payees table"   # create a migration
uv run poe migrate                              # apply all migrations
uv run poe migrate downgrade -1                 # undo the last one
```

Inside Docker, `docker compose run --rm migrate` does the same, using the
API image. Pass Alembic arguments after it, e.g.
`docker compose run --rm migrate downgrade -1`. Migrations never run when
the API starts.

A migration that has been committed should not be edited and a new one
should be added instead.

## Health checks

- `GET /health/live` reports whether the API process is running.
- `GET /health/ready` also checks the database, and returns `503` if it
  isn't reachable.

Both include the app `version`, and a `build` label identifying the exact
commit when one was provided at build time:

```bash
APP_BUILD=$(uv run poe -q build-label) docker compose up -d --build
```

## Project layout

```
app/
  api/            HTTP endpoints
  services/       business rules
  repositories/   SQL for reading and writing data
  database/       database connections
  schemas/        request and response models
  core/           settings shared by every layer
migrations/       Alembic database migrations
scripts/          utility scripts, e.g. the build label
tests/            test suite
docs/             design document
```

## Branching, versioning and releases

- Work happens on short-lived feature branches, merged into `main` through
  pull requests.
- `main` is promoted to `staging`, and `staging` to `production`. Promoting
  is a fast-forward, so production only ever contains code verified on
  staging.
- Releases follow [semantic versioning](https://semver.org). Versions below
  `1.0.0` are pre-release, and the API isn't stable until `1.0.0`.

The full rules are in the
[design document, §9](docs/DESIGN.md#9-engineering-practice).

## Backups

*Coming in milestone 2:* backup and restore commands for the database.

## API documentation

The interactive docs are served at `/docs`, and the OpenAPI schema at
`/openapi.json`. The schema a running app serves reports its build label as
the version.

The schema is also committed as [`openapi.json`](openapi.json), with the
plain version, so API changes show up in review and the frontend can
generate its API types from it. After changing an endpoint or schema,
re-export it and commit the result:

```bash
uv run poe export-openapi
```

The tests fail if the committed file no longer matches the app.

## AI usage

This project is developed with the help of an AI coding assistant,
[Claude Code](https://claude.com/claude-code).

- **What AI is used for:** drafting code, tests, configuration and
  documentation, and reviewing changes against the design document.
- **Human oversight:** every change is proposed, reviewed and approved by
  the maintainer before it is made, and nothing is committed without the
  maintainer's review. Design decisions are made by the maintainer and
  recorded in the [design document](docs/DESIGN.md).
- **Attribution:** commits written by an AI agent carry a `Co-Authored-By`
  trailer naming the model. Commits written by the maintainer don't.
- **Instructions for AI tools:** `AGENTS.md`, and `CLAUDE.md`, which points
  to it, hold the conventions AI assistants follow in this repository.
  You don't need them to work on the project.

## Licence

[MIT](LICENSE)
