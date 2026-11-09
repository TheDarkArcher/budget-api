"""SQL for the ``item_categories`` table."""

from uuid import UUID

from sqlalchemy import Connection, text


def insert(connection: Connection, user_id: UUID, name: str) -> UUID:
    """Insert an item category.

    Args:
        connection: The connection to run the insert on.
        user_id: The id of the user who owns the category.
        name: The category's name.

    Returns:
        The new category's id.
    """
    category_id: UUID = connection.execute(
        text(
            "INSERT INTO item_categories (user_id, name)"
            " VALUES (:user_id, :name) RETURNING id"
        ),
        {"user_id": user_id, "name": name},
    ).scalar_one()
    return category_id
