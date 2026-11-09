"""Tests for the user business rules, with the data access mocked."""

from dataclasses import dataclass, field
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection

from app.repositories import item_categories, transaction_categories
from app.services import users
from app.services.users import provision_user

USER_ID = UUID("0192f0c4-0000-7000-8000-000000000001")
CONNECTION = cast("Connection", object())


@dataclass
class FakeRepositories:
    """Records what is written, handing out a new id for each row."""

    transaction_categories: dict[UUID, tuple[UUID, str, str]] = field(
        default_factory=dict
    )
    item_categories: dict[UUID, tuple[UUID, str]] = field(default_factory=dict)
    links: list[tuple[UUID, UUID]] = field(default_factory=list)
    connections: set[int] = field(default_factory=set)

    def insert_transaction_category(
        self, connection: Connection, user_id: UUID, name: str, category_type: str
    ) -> UUID:
        self.connections.add(id(connection))
        category_id = uuid4()
        self.transaction_categories[category_id] = (user_id, name, category_type)
        return category_id

    def insert_item_category(
        self, connection: Connection, user_id: UUID, name: str
    ) -> UUID:
        self.connections.add(id(connection))
        category_id = uuid4()
        self.item_categories[category_id] = (user_id, name)
        return category_id

    def link_item_category(
        self,
        connection: Connection,
        transaction_category_id: UUID,
        item_category_id: UUID,
    ) -> None:
        self.connections.add(id(connection))
        self.links.append((transaction_category_id, item_category_id))


@pytest.fixture
def repositories(monkeypatch: pytest.MonkeyPatch) -> FakeRepositories:
    fake = FakeRepositories()
    monkeypatch.setattr(
        transaction_categories, "insert", fake.insert_transaction_category
    )
    monkeypatch.setattr(
        transaction_categories, "link_item_category", fake.link_item_category
    )
    monkeypatch.setattr(item_categories, "insert", fake.insert_item_category)
    return fake


def test_creates_the_default_transaction_categories(
    repositories: FakeRepositories,
) -> None:
    provision_user(CONNECTION, USER_ID)
    assert sorted(repositories.transaction_categories.values()) == sorted(
        [
            (USER_ID, "Salary", "income"),
            (USER_ID, "Groceries", "expense"),
            (USER_ID, "Rent", "expense"),
            (USER_ID, "Bills", "expense"),
        ]
    )


def test_creates_the_default_item_categories(repositories: FakeRepositories) -> None:
    provision_user(CONNECTION, USER_ID)
    assert sorted(repositories.item_categories.values()) == sorted(
        [
            (USER_ID, "Food & Drink"),
            (USER_ID, "Household"),
            (USER_ID, "Personal Care"),
            (USER_ID, "General / Other"),
        ]
    )


def test_links_the_default_categories(repositories: FakeRepositories) -> None:
    provision_user(CONNECTION, USER_ID)
    links = [
        (
            repositories.transaction_categories[transaction_category][1],
            repositories.item_categories[item_category][1],
        )
        for transaction_category, item_category in repositories.links
    ]
    assert sorted(links) == sorted(
        [
            ("Salary", "General / Other"),
            ("Groceries", "Food & Drink"),
            ("Groceries", "Household"),
            ("Groceries", "Personal Care"),
            ("Rent", "General / Other"),
            ("Bills", "Household"),
            ("Bills", "General / Other"),
        ]
    )


def test_writes_everything_on_the_callers_connection(
    repositories: FakeRepositories,
) -> None:
    provision_user(CONNECTION, USER_ID)
    assert repositories.connections == {id(CONNECTION)}


def test_a_misspelt_item_category_link_fails_instead_of_adding_a_category(
    repositories: FakeRepositories, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(users.DEFAULT_CATEGORY_LINKS, "Groceries", ("Food and Drink",))
    with pytest.raises(KeyError, match="Food and Drink"):
        provision_user(CONNECTION, USER_ID)
    assert "Food and Drink" not in {
        name for _, name in repositories.item_categories.values()
    }


def test_a_misspelt_transaction_category_link_fails_instead_of_adding_a_category(
    repositories: FakeRepositories, monkeypatch: pytest.MonkeyPatch
) -> None:
    links = dict(users.DEFAULT_CATEGORY_LINKS)
    links["Grocerise"] = links.pop("Groceries")
    monkeypatch.setattr(users, "DEFAULT_CATEGORY_LINKS", links)
    with pytest.raises(KeyError, match="Groceries"):
        provision_user(CONNECTION, USER_ID)
    assert "Grocerise" not in {
        name for _, name, _ in repositories.transaction_categories.values()
    }


def test_default_links_only_use_default_categories() -> None:
    # A stray or misspelt entry would otherwise be silently ignored.
    links = users.DEFAULT_CATEGORY_LINKS
    assert links.keys() == users.DEFAULT_TRANSACTION_CATEGORIES.keys()
    linked = {name for names in links.values() for name in names}
    assert linked <= set(users.DEFAULT_ITEM_CATEGORIES)
