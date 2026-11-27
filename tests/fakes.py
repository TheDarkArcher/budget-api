"""Fake data-access repositories that record what is written, for service tests."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.errors import ArchivedError, NameConflictError
from app.core.list_options import NameSort
from app.repositories.item_categories import ItemCategoryRepository
from app.repositories.lists import LookupResourceCriteria, RecordPage
from app.repositories.payees import Payee, PayeeRepository
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


class FakePayeeRepository(PayeeRepository):
    """Keeps payees in memory, by id, with the id of the user who owns each.

    Refuses a name the user already has, ignoring case, and any change to an
    archived payee, as the database does. Archives payees at ``now``. Lists
    every one of the user's payees on one page, recording the criteria it was
    given rather than applying them.
    """

    def __init__(self) -> None:
        self.payees: dict[UUID, tuple[UUID, Payee]] = {}
        self.list_criteria: LookupResourceCriteria[NameSort] | None = None
        self.now = datetime(2026, 11, 2, tzinfo=UTC)

    def create(self, user_id: UUID, name: str) -> Payee:
        if self.get_by_name(user_id, name) is not None:
            raise NameConflictError
        payee = Payee(id=uuid4(), name=name, archived_at=None)
        self.payees[payee.id] = (user_id, payee)
        return payee

    def get(self, user_id: UUID, payee_id: UUID) -> Payee | None:
        owner, payee = self.payees.get(payee_id, (None, None))
        return payee if owner == user_id else None

    def update(self, user_id: UUID, payee_id: UUID, name: str) -> Payee | None:
        payee = self.get(user_id, payee_id)
        if payee is None:
            return None
        if payee.archived_at is not None:
            raise ArchivedError
        clash = self.get_by_name(user_id, name)
        if clash is not None and clash.id != payee_id:
            raise NameConflictError
        updated = replace(payee, name=name)
        self.payees[payee_id] = (user_id, updated)
        return updated

    def archive(self, user_id: UUID, payee_id: UUID) -> Payee | None:
        payee = self.get(user_id, payee_id)
        if payee is None or payee.archived_at is not None:
            return None
        archived = replace(payee, archived_at=self.now)
        self.payees[payee_id] = (user_id, archived)
        return archived

    def unarchive(self, user_id: UUID, payee_id: UUID) -> Payee | None:
        payee = self.get(user_id, payee_id)
        if payee is None or payee.archived_at is None:
            return None
        unarchived = replace(payee, archived_at=None)
        self.payees[payee_id] = (user_id, unarchived)
        return unarchived

    def list(
        self, user_id: UUID, criteria: LookupResourceCriteria[NameSort]
    ) -> RecordPage[Payee]:
        self.list_criteria = criteria
        payees = [payee for owner, payee in self.payees.values() if owner == user_id]
        return RecordPage(payees, len(payees))

    def get_by_name(self, user_id: UUID, name: str) -> Payee | None:
        return next(
            (
                payee
                for owner, payee in self.payees.values()
                if owner == user_id and payee.name.lower() == name.lower()
            ),
            None,
        )


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
