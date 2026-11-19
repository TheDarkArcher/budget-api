---
name: migration
description: Write an Alembic migration for this repository's PostgreSQL schema - creating the revision, the SQL and naming conventions, a working downgrade, and the tests that go with it. Use whenever a change needs a new or changed table, column, constraint, index, trigger, view, function or type.
---

# Writing a migration

The rules are in the Database section of `AGENTS.md`, and the schema decisions are in the "Data Model" and "Considerations for Deployment" sections of `docs/DESIGN.md`. This skill is the procedure for following them; where the two differ, the rules win. The current schema is whatever the migrations in `migrations/versions/` build, so read them first.

## 1. Create the revision
- Never edit a migration that's already committed; add a new one. A hook refuses edits to committed migrations, and it must not be worked around.
- Create the file with `uv run alembic revision -m "<Imperative description>"`. Alembic names it by date and revision id, links it to the previous one and formats it; don't write those parts by hand.
- If the change needs a schema decision the design document doesn't cover or conflicts with, ask first, as AGENTS.md requires.

## 2. Write the tests first
- Add database-constraint tests to `tests/test_schema.py` for every rule the migration will enforce: each constraint and trigger refusing what it should, and the changes it must still allow. Use the file's helpers (`fails` with the expected error class, `run`, `one`, `count`) and its `alice` and `bob` fixtures. When a new table needs rows for tests, extend `make_world` and `World` to create them.
- Before writing the upgrade, run the new tests directly and see them fail, as CLAUDE.md directs for tests written first.
- Each refusal test must fail because its constraint or trigger doesn't exist yet, as the Tests section of `AGENTS.md` requires. When the table is new, it fails because the table doesn't exist yet.
- Tests of changes that must still be allowed on an existing table cover behaviour that already exists, so the fail-first rule doesn't apply to them and they may already pass.

## 3. Write the upgrade
- Write the SQL by hand in `op.execute(...)` calls; don't use Alembic's operations or autogenerate. Follow the SQL rules in AGENTS.md.
- Keep each migration compatible with the code of the previous release: add what's new in one release and remove what's old in a later one.
- Seed data doesn't belong in migrations; it belongs in the seed script.
- Follow the "Decisions" in the Data Model section for every new table. In particular:
  - A `uuid` primary key defaulting to `uuidv7()`, `created_at` and `updated_at` columns, and a `<table>_set_updated_at` trigger.
  - Names `NOT NULL` with a `<table>_name_not_blank` check, and unique per user ignoring case through a unique index on `(user_id, lower(name))` named `<table>_user_id_name_key`.
  - Money as `NUMERIC(12,2)`; archiving with a nullable `archived_at`.
  - Each foreign key's `ON DELETE` as the "Deleting" decision says: `RESTRICT` unless it lists `CASCADE` for that relationship.
  - For a user-owned table (one the ER diagram links to `users`): a `<table>_prevent_user_id_change` trigger, composite foreign keys for direct links to other user-owned tables (which need a `<table>_user_id_id_key` unique constraint on `(user_id, id)` in the referenced table), and a user-matching trigger for transitive ones. A user-matching trigger is named `<table>_check_user` and raises `foreign_key_violation` with `CONSTRAINT = '<table>_same_user'`.
- Name every constraint, unique index and index explicitly, in the style of the existing ones: `<table>_<columns>_key`, `<table>_<columns>_fkey`, `<table>_<column>_positive`, `<table>_name_not_blank`, `<table>_<columns>_idx`. The names let the API map database errors to responses.
- A trigger that refuses a change raises with an `ERRCODE` and `CONSTRAINT = '<name>'`, like `prevent_user_id_change()`, so the API can map it the same way.

## 4. Write the downgrade
- Every migration has a working `downgrade()` that undoes its upgrade, in reverse order. Drop views before the tables they read from, and functions and types after everything that uses them; dropping a table drops its triggers and indexes with it.
- When the upgrade changes an existing object, the downgrade restores its previous definition exactly: copy the old function body or view definition into the downgrade.
- A value added to an enum type can't be removed, so the downgrade rebuilds the type without it.

## 5. Run the tests
- The round-trip test in `tests/test_migrations.py` upgrades to head, downgrades to base and upgrades again, checking that the downgrade leaves nothing behind. It must keep passing.
- Run the new constraint tests directly and see them pass now that the upgrade is written.
- Then have the `quality-gates` agent run `tests/test_schema.py` and `tests/test_migrations.py`, as CLAUDE.md requires.

## 6. Keep the design document in step
- If the change alters the data model, update `docs/DESIGN.md` to match, including its ER diagram, Constructs table and Decisions, following the `design-doc` skill.
