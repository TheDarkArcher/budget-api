"""Tests for the user business rules, with fake data access."""

from uuid import UUID

import pytest
from fakes import (
    FakeItemCategoryRepository,
    FakeTransactionCategoryRepository,
    FakeUserRepository,
)

from app.repositories.users import User
from app.services import users
from app.services.users import get_user, provision_user

USER_ID = UUID("0192f0c4-0000-7000-8000-000000000001")


def test_creates_the_default_transaction_categories(
    fake_item_category_repo: FakeItemCategoryRepository,
    fake_transaction_category_repo: FakeTransactionCategoryRepository,
) -> None:
    provision_user(fake_item_category_repo, fake_transaction_category_repo, USER_ID)
    assert sorted(
        fake_transaction_category_repo.transaction_categories.values()
    ) == sorted(
        [
            (USER_ID, "Salary", "income"),
            (USER_ID, "Groceries", "expense"),
            (USER_ID, "Rent", "expense"),
            (USER_ID, "Bills", "expense"),
        ]
    )


def test_creates_the_default_item_categories(
    fake_item_category_repo: FakeItemCategoryRepository,
    fake_transaction_category_repo: FakeTransactionCategoryRepository,
) -> None:
    provision_user(fake_item_category_repo, fake_transaction_category_repo, USER_ID)
    assert sorted(fake_item_category_repo.item_categories.values()) == sorted(
        [
            (USER_ID, "Food & Drink"),
            (USER_ID, "Household"),
            (USER_ID, "Personal Care"),
            (USER_ID, "General / Other"),
        ]
    )


def test_links_the_default_categories(
    fake_item_category_repo: FakeItemCategoryRepository,
    fake_transaction_category_repo: FakeTransactionCategoryRepository,
) -> None:
    provision_user(fake_item_category_repo, fake_transaction_category_repo, USER_ID)
    repo_transaction_categories = fake_transaction_category_repo.transaction_categories
    repo_item_categories = fake_item_category_repo.item_categories
    links = [
        (
            repo_transaction_categories[transaction_category][1],
            repo_item_categories[item_category][1],
        )
        for transaction_category, item_category in fake_transaction_category_repo.links
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


def test_a_misspelt_item_category_link_fails_instead_of_adding_a_category(
    fake_item_category_repo: FakeItemCategoryRepository,
    fake_transaction_category_repo: FakeTransactionCategoryRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(users.DEFAULT_CATEGORY_LINKS, "Groceries", ("Food and Drink",))
    with pytest.raises(KeyError, match="Food and Drink"):
        provision_user(fake_item_category_repo, fake_transaction_category_repo, USER_ID)
    assert "Food and Drink" not in {
        name for _, name in fake_item_category_repo.item_categories.values()
    }


def test_a_misspelt_transaction_category_link_fails_instead_of_adding_a_category(
    fake_item_category_repo: FakeItemCategoryRepository,
    fake_transaction_category_repo: FakeTransactionCategoryRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    links = dict(users.DEFAULT_CATEGORY_LINKS)
    links["Grocerise"] = links.pop("Groceries")
    monkeypatch.setattr(users, "DEFAULT_CATEGORY_LINKS", links)
    with pytest.raises(KeyError, match="Groceries"):
        provision_user(fake_item_category_repo, fake_transaction_category_repo, USER_ID)
    assert "Grocerise" not in {
        name
        for _, name, _ in fake_transaction_category_repo.transaction_categories.values()
    }


def test_default_links_only_use_default_categories() -> None:
    # A stray or misspelt entry would otherwise be silently ignored.
    links = users.DEFAULT_CATEGORY_LINKS
    assert links.keys() == users.DEFAULT_TRANSACTION_CATEGORIES.keys()
    linked = {name for names in links.values() for name in names}
    assert linked <= set(users.DEFAULT_ITEM_CATEGORIES)


def test_get_user_returns_the_user(fake_user_repo: FakeUserRepository) -> None:
    fake_user_repo.create(USER_ID, "Someone")
    assert get_user(fake_user_repo, USER_ID) == User(id=USER_ID, name="Someone")


def test_get_user_returns_none_for_an_unknown_id(
    fake_user_repo: FakeUserRepository,
) -> None:
    assert get_user(fake_user_repo, USER_ID) is None
