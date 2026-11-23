---
name: constraint-error-mapping
description: How database constraint names map to domain errors and problem types; verified names and accepted decisions
metadata:
  type: project
---

- `app/repositories/errors.py` `CONSTRAINT_ERRORS` maps constraint names to `app/core/errors.py` domain errors; `translate_constraint_errors` runs writes in a savepoint and re-raises unmapped `IntegrityError`. The API maps domain errors to problems in `app/api/problems.py`. The mapping lives in the repository layer, not `app/api/`, by the maintainer's decision; don't suggest moving it.
- Constraint names come from the two migrations: unique indexes `<table>_user_id_name_key`, FKs `transactions_user_id_*_fkey`, `items_user_id_item_category_id_fkey`, auto-named `transaction_lines_item_size_id_fkey`, and trigger-raised names (`archived_record_immutable`, `transaction_categories_type_immutable`, `transaction_categories_item_category_link`, `transaction_category_item_categories_category_archived`). Check a new mapping against `RAISE ... CONSTRAINT =` in the migrations.
- The linked-delete trigger skips a category a transaction uses, so the FK reports in-use/transaction first (DESIGN.md 8.9).
- Unmapped on purpose: item size value/unit/item-id triggers (`user_id_immutable` too). A domain error with no case in `domain_problem` (`app/api/problems.py`) re-raises into the logged 500 until its problem type is added; don't flag a mapped error for lacking a problem case unless the change claims to report it.
