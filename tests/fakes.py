"""Fake data-access repositories that record what is written, for service tests."""

from uuid import UUID, uuid4

from app.repositories.item_categories import ItemCategoryRepository
from app.repositories.transaction_categories import (
    CategoryType,
    TransactionCategoryRepository,
)
from app.repositories.users import User, UserRepository


class FakeItemCategoryRepository(ItemCategoryRepository):
    """Records the item categories written, handing out a new id for each."""

    def __init__(self) -> None:
        self.item_categories: dict[UUID, tuple[UUID, str]] = {}

    def create(self, user_id: UUID, name: str) -> UUID:
        category_id = uuid4()
        self.item_categories[category_id] = (user_id, name)
        return category_id


class FakeTransactionCategoryRepository(TransactionCategoryRepository):
    """Records the transaction categories and links written.

    Hands out a new id for each category.
    """

    def __init__(self) -> None:
        self.transaction_categories: dict[UUID, tuple[UUID, str, CategoryType]] = {}
        self.links: list[tuple[UUID, UUID]] = []

    def create(self, user_id: UUID, name: str, category_type: CategoryType) -> UUID:
        category_id = uuid4()
        self.transaction_categories[category_id] = (user_id, name, category_type)
        return category_id

    def link_item_category(
        self, transaction_category_id: UUID, item_category_id: UUID
    ) -> None:
        self.links.append((transaction_category_id, item_category_id))


class FakeUserRepository(UserRepository):
    """Keeps users in memory, by id."""

    def __init__(self) -> None:
        self.users: dict[UUID, User] = {}

    def get(self, user_id: UUID) -> User | None:
        return self.users.get(user_id)

    def create(self, user_id: UUID, name: str) -> bool:
        if user_id in self.users:
            return False
        self.users[user_id] = User(id=user_id, name=name)
        return True
