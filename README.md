# Budget Tracker API

Budget Tracker API is a web backend API that gives you a clear picture of
where your money goes. It records income and expenses, organises them into
categories, and shows how spending changes over time.

This repository holds the REST API and its PostgreSQL database. No frontend
for using the API is provided as part of this project. Goals, architecture,
data model and roadmap are in the [design document](docs/DESIGN.md).

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Compose for containerisation
- [uv](https://docs.astral.sh/uv/) for Python version and package management

## Quick start

```bash
cp .env.example .env
docker compose up -d
docker compose run --rm migrate
```

The last command applies the database migrations and then seeds the dummy
user, as described in [Seeding](#seeding). The API is now at
<http://localhost:8000>:

- <http://localhost:8000/docs> shows the interactive API docs.
- <http://localhost:8000/health/ready> should return `"status": "ok"`.

Code changes in `app/` reload automatically. Stop everything with
`docker compose down`; add `-v` to also delete the database.

## Configuration

All settings are environment variables, read from `.env`.
[`.env.example`](.env.example) lists every one with a comment explaining it.

If port 5432 is already in use on your machine (for example by a local
PostgreSQL install), set `POSTGRES_HOST_PORT` to a free port such as `5433`.
`DATABASE_URL` in `.env` follows it.

## Running the API without Docker

The database still runs in Docker; the API runs directly on your machine:

```bash
uv sync
docker compose up -d db
uv run poe migrate
uv run poe seed
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
`docker compose run --rm migrate downgrade -1`. When the arguments are
exactly `upgrade head`, the default, it then seeds the dummy user (see
[Seeding](#seeding)); `uv run poe migrate` never seeds. Migrations never
run when the API starts.

A migration that has been committed should not be edited and a new one
should be added instead.

## Seeding

Until user management exists, all budgeting data belongs to a single dummy
user. Seeding creates that user with the default transaction categories,
item categories and the links between them.

```bash
uv run poe migrate   # the database must be migrated first
uv run poe seed      # create the dummy user, unless they already exist
```

Inside Docker, `docker compose run --rm migrate` does both, as described in
[Database migrations](#database-migrations). Seeding again leaves an
existing dummy user unchanged.

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
  repositories/   data storage interfaces and their implementations
  database/       database connections
  schemas/        request and response models
  core/           settings and constants shared by every layer
migrations/       Alembic database migrations
scripts/          utility scripts
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
[Engineering Practice](docs/DESIGN.md#9-engineering-practice) section of the
design document.

## Backups

Back up the database regularly, and before anything risky such as an
upgrade:

```bash
uv run poe backup                     # dump the database into backups/
uv run poe restore backups/<file>     # restore a dump
```

Both use PostgreSQL's tools in the `db` container, so it must be running
(`docker compose up -d db`). Dumps are named by date and time, such as
`db_backup_20261111T143000.dump`, and kept in the git-ignored `backups/`
folder.

A restore replaces the database the dump was taken from. It refuses if that
database isn't empty (i.e. it has tables, functions, other schema objects
or large objects in it) unless you add `--force`. It also refuses while
anything is connected to the database, so stop the app first with
`docker compose stop api`.

An empty database, such as the one Docker Compose creates, is simply
replaced, and recreated empty if the restore fails. One that isn't empty is
set aside while restoring, and put back if the restore fails. If even that
fails, the error names the database the original data was set aside in. A
database named `<name>_before_restore_<timestamp>` holds the data from
before a restore that didn't finish cleanly, or whose set-aside copy
couldn't be dropped; drop it once you no longer need it.

Dumps hold all of the data, so they're set to only be readable by the user
that generated them. A restore runs the SQL inside the dump, so only restore
dumps you trust.

## API documentation

The interactive docs are served at `/docs`, and the OpenAPI schema at
`/openapi.json`. The schema a running app serves reports its build label as
the version.

The schema is also committed as [`openapi.json`](openapi.json), with the
plain version, so API changes show up in review and a frontend can
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
- **Human oversight:** changes are made at the maintainer's request, and the
  maintainer reviews every change before it is committed. Commit messages
  are approved by the maintainer or follow an approved pattern. Design
  decisions are made by the maintainer and recorded in the
  [design document](docs/DESIGN.md).
- **Attribution:** commits written by an AI agent carry a `Co-Authored-By`
  trailer naming the model. Commits written by the maintainer don't.
- **Instructions for AI tools:** `AGENTS.md`, and `CLAUDE.md`, which points
  to it, hold the conventions AI assistants follow in this repository.
  You don't need them to work on the project.

## Licence

[MIT](LICENSE)
