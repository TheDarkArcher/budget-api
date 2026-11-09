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
  lines, and the `transaction_totals` and `items_information` views.
- Configuration from environment variables, documented in `.env.example`.
- Docker Compose setup with PostgreSQL 18 and a one-off `migrate` service.
- Interactive API documentation at `/docs` and the OpenAPI schema at
  `/openapi.json`.
- User provisioning: a new user is given the default transaction categories
  (Salary, Groceries, Rent and Bills), item categories (Food & Drink,
  Household, Personal Care and General / Other) and the links between them.
- A dummy user that acts as the system's sole user until full user
  management exists. It is provisioned with the default categories and
  links.
- Seeding of the dummy user: `docker compose run --rm migrate` seeds it after
  upgrading the database, and `uv run poe seed` does the same outside Docker.
  Seeding again leaves the existing dummy user unchanged.

[Unreleased]: https://github.com/TheDarkArcher/budget-api/commits/main
