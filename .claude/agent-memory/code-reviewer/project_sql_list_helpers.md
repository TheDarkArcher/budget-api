---
name: project-sql-list-helpers
description: How the SQL list helpers in app/repositories/sql_lists.py are designed, and what a list's query and criteria must provide
metadata:
  type: project
---

app/repositories/sql_lists.py pages, searches and sorts lists for SQL repositories. It wraps the repository's own t-string query in hand-written SQL in SQLAlchemy `tstring()` t-strings.

- **Classes:** `SQLLists` pages any query and leaves the matching records and sort keys to its subclasses. `SQLLookupResourceLists`, built with the connection and the resource's sorts, adds the lookup resources' name search and archived filter.
- **Interfaces:** by the maintainer's decision, for now, the SQL list helpers have no interfaces of their own, and `translate_sql_constraint_errors` stays a function; don't suggest either. An SQL repository builds its own list helper from its connection rather than being given one, so it can't be given another storage's.
- **Criteria:** `LookupResourceCriteria` in app/repositories/lists.py has no defaults. Its sort is an enum of the resource's sorts, shared by the schema and the repository, and the order has no default on the SQL side.
- **Records that are never archived:** their query must select `NULL AS archived_at`, and they must be listed with `ArchivedFilter.ALL`.
- **Sorting:** `SQL_NAME_ORDER` sorts by `lower(name)` then `id`, matching the `lower(name)` unique indexes.
