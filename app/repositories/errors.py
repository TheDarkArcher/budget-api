"""Translation of writes the database refuses into domain errors."""

from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from functools import partial

import psycopg
from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

from app.core.errors import (
    ArchivedError,
    Blocker,
    DomainError,
    InUseError,
    NameConflictError,
    TypeChangeError,
)

# The domain error for each constraint a request can break. Others, such as an
# item size's value or unit changing, are bugs no request can cause, so they
# stay unmapped and surface as an unexpected error.
CONSTRAINT_ERRORS: Mapping[str, Callable[[], DomainError]] = {
    "transaction_categories_user_id_name_key": NameConflictError,
    "item_categories_user_id_name_key": NameConflictError,
    "payees_user_id_name_key": NameConflictError,
    "tags_user_id_name_key": NameConflictError,
    "items_user_id_name_key": NameConflictError,
    "transactions_user_id_transaction_category_id_fkey": partial(
        InUseError, Blocker.TRANSACTION
    ),
    "transactions_user_id_payee_id_fkey": partial(InUseError, Blocker.TRANSACTION),
    "transaction_lines_item_size_id_fkey": partial(InUseError, Blocker.TRANSACTION),
    "items_user_id_item_category_id_fkey": partial(InUseError, Blocker.ITEM),
    "transaction_categories_item_category_link": partial(
        InUseError, Blocker.ITEM_CATEGORY
    ),
    "transaction_categories_type_immutable": TypeChangeError,
    "archived_record_immutable": ArchivedError,
    "transaction_category_item_categories_category_archived": ArchivedError,
}


@contextmanager
def translate_constraint_errors(connection: Connection) -> Generator[None]:
    """Run writes in a savepoint, raising a refused constraint as a domain error.

    The savepoint is rolled back on failure, so the transaction stays usable,
    for example to look up the record a duplicate name clashes with.

    Args:
        connection: The connection the writes run on.

    Yields:
        Nothing; the writes run inside the ``with`` block.

    Raises:
        DomainError: If the database refused a write under a mapped constraint.
        IntegrityError: If it refused a write under any other constraint.
    """
    try:
        with connection.begin_nested():
            yield
    except IntegrityError as exc:
        constraint = (
            exc.orig.diag.constraint_name
            if isinstance(exc.orig, psycopg.Error)
            else None
        )
        domain_error = CONSTRAINT_ERRORS.get(constraint or "")
        if domain_error is None:
            raise
        raise domain_error() from exc
