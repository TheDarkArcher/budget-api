# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Breaking changes are listed under their own **Breaking** heading.

## [Unreleased]

### Added

- Health endpoints at the root, outside `/api/v1`: `GET /health/live` checks
  only that the process responds, and `GET /health/ready` checks each
  subsystem, returning 200 when all pass and 503 when any fail. Both report
  the version and build label.
- The v1 database schema: users, transaction categories, item categories,
  payees, tags, items with their sizes and tags, transactions with their
  lines, idempotency keys, and the `transaction_totals` and
  `items_information` views.
- Configuration from environment variables, documented in `.env.example`.
- Docker Compose setup with PostgreSQL 18 and a one-off `migrate` service.
- Interactive API documentation at `/docs` and the OpenAPI schema at
  `/openapi.json`. The served schema reports the running build's label as its
  version, e.g. `0.1.0-dev.11+23e3a68`.
- The OpenAPI schema committed as `openapi.json`, with the plain version, so
  clients can generate their API types from it without running the API.
- Every operation in the OpenAPI schema has an explicit camelCase
  `operationId`, such as `getCurrentUser`, a short summary and a description
  written for clients, so generated clients get readable method names.
- User provisioning: a new user is given the default transaction categories
  (Salary, Groceries, Rent and Bills), item categories (Food & Drink,
  Household, Personal Care and General / Other) and the links between them.
- A dummy user that acts as the system's sole user until full user
  management exists. It is provisioned with the default categories and
  links.
- Seeding of the dummy user: `docker compose run --rm migrate` seeds it after
  upgrading the database, and `uv run poe seed` does the same outside Docker.
  Seeding again leaves the existing dummy user unchanged.
- `GET /api/v1/me`, which returns the current user's id and name. Every
  request to a versioned API path, such as `/api/v1`, acts as the dummy
  user. If the dummy user doesn't exist, the request is refused with a 403
  problem before it is routed or parsed, whatever else is wrong with it.
- Error responses as RFC 9457 problem details (`application/problem+json`),
  documented in `openapi.json`. 409 and 422 responses carry a named `type`,
  such as `/problems/name-conflict` or `/problems/validation`, so clients
  can tell them apart; every other status uses `about:blank`. Validation
  problems list each problem in an `errors` entry that points into the body
  or names the query or header parameter. A malformed id in the path returns
  404, so an operation whose only input is its path documents no 422. An
  unexpected error returns a 500 problem with no internal detail.
- Cross-origin requests from the origins listed in `CORS_ALLOWED_ORIGINS`,
  so a browser frontend served from another origin can call the API.
  Browsers may send the `Content-Type` and `Idempotency-Key` headers and can
  read the `Location` header of a response.
- A query parameter sent more than once to a versioned API path is refused,
  unless it takes a list of values. The refusal is a `/problems/validation`
  problem whose `errors` entry tells the client to send it only once.
- Database backups: `uv run poe backup` dumps the database to a timestamped
  file in `backups/`. Dumps are readable only by their owner.
- Database restores: `uv run poe restore <file>` restores a dump. A restore
  refuses while anything is connected to the database. An empty database is
  replaced without asking, and recreated empty if the restore fails. A
  database that isn't empty is only replaced with `--force`, and is kept
  until the restore succeeds.
- Payee endpoints under `/api/v1/payees`: list, create, get, update
  (`PUT`), delete, archive and unarchive, each scoped to the current user,
  so another user's payee returns 404. Payee names are unique per user,
  ignoring case and including archived payees; a clashing name returns a
  `/problems/name-conflict` problem whose `existing` member names the payee
  that has it. Updating an archived payee returns `/problems/archived`, and
  deleting a payee a transaction uses returns `/problems/in-use/transaction`.
  Archiving an archived payee, or unarchiving an active one, changes nothing,
  so either request is safe to repeat.
- Paged lists: list endpoints take `page` and `pageSize` (1 to 200, default
  25) and return `data` with `page`, `pageSize`, `totalItems` and
  `totalPages`. Lookup lists also take `q` to search names, `archived`
  (`false`, `true` or `all`, default `false`), and `sort` and `order`.
- An optional `Idempotency-Key` header on requests that create a record. A
  repeat with the same key and request within 24 hours returns the original
  response instead of creating a second record, and a repeat sent while the
  first is still running waits for it. The same key with a different request
  returns a `/problems/idempotency-key-mismatch` problem.
- Request bodies refuse fields they don't declare, at the top level or in a
  nested object, with a `/problems/validation` problem whose `errors` entries
  point at each such field. Query parameters an endpoint doesn't declare are
  still ignored.

[Unreleased]: https://github.com/TheDarkArcher/budget-api/commits/main
