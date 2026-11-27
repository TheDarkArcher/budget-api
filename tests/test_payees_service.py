"""Tests for the payee business rules, with fake data access."""

from uuid import UUID

import pytest
from fakes import FakePayeeRepository

from app.core.errors import NotFoundError
from app.repositories.payees import Payee
from app.services.payees import PayeeNameConflictError, create_payee, get_payee

USER_ID = UUID("0192f0c4-0000-7000-8000-000000000001")
OTHER_USER_ID = UUID("0192f0c4-0000-7000-8000-000000000002")
UNKNOWN_ID = UUID("0192f0c4-0000-7000-8000-0000000000ff")


def test_create_payee_stores_an_active_payee_for_the_user(
    fake_payee_repo: FakePayeeRepository,
) -> None:
    payee = create_payee(fake_payee_repo, USER_ID, "Corner Store")
    assert fake_payee_repo.payees == {
        payee.id: (USER_ID, Payee(id=payee.id, name="Corner Store", archived_at=None))
    }


def test_create_payee_raises_name_conflict_naming_the_payee_with_the_name(
    fake_payee_repo: FakePayeeRepository,
) -> None:
    existing = fake_payee_repo.create(USER_ID, "Corner Store")
    with pytest.raises(PayeeNameConflictError) as raised:
        create_payee(fake_payee_repo, USER_ID, "corner store")
    assert raised.value.existing == existing


def test_get_payee_returns_the_users_payee(
    fake_payee_repo: FakePayeeRepository,
) -> None:
    created = fake_payee_repo.create(USER_ID, "Corner Store")
    assert get_payee(fake_payee_repo, USER_ID, created.id) == created


def test_get_payee_raises_not_found_for_another_users_payee(
    fake_payee_repo: FakePayeeRepository,
) -> None:
    created = fake_payee_repo.create(OTHER_USER_ID, "Corner Store")
    with pytest.raises(NotFoundError):
        get_payee(fake_payee_repo, USER_ID, created.id)


def test_get_payee_raises_not_found_for_an_unknown_id(
    fake_payee_repo: FakePayeeRepository,
) -> None:
    with pytest.raises(NotFoundError):
        get_payee(fake_payee_repo, USER_ID, UNKNOWN_ID)
