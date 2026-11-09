"""SQL for the ``users`` table."""

from uuid import UUID

from sqlalchemy import Connection, text


def insert(connection: Connection, user_id: UUID, name: str) -> bool:
    """Insert a user with the given id, unless one already exists.

    Args:
        connection: The connection to run the insert on.
        user_id: The new user's id.
        name: The new user's name.

    Returns:
        ``True`` if the user was inserted, ``False`` if a user with that id
        already existed.
    """
    inserted = connection.execute(
        text(
            "INSERT INTO users (id, name) VALUES (:id, :name)"
            " ON CONFLICT (id) DO NOTHING RETURNING id"
        ),
        {"id": user_id, "name": name},
    ).first()
    return inserted is not None
