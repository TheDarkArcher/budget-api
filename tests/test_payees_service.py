"""Tests for the payee business rules, with fake data access."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fakes import FakePayeeRepository

from app.core.errors import ArchivedError, NotFoundError
from app.core.list_options import ArchivedFilter, NameSort, SortOrder
from app.repositories.lists import LookupResourceCriteria, RecordPage
from app.repositories.payees import Payee
from app.services.payees import (
    PayeeNameConflictError,
    create_payee,
    get_payee,
    list_payees,
    update_payee,
)

USER_ID = UUID("0192f0c4-0000-7000-8000-000000000001")
OTHER_USER_ID = UUID("0192f0c4-0000-7000-8000-000000000002")
UNKNOWN_ID = UUID("0192f0c4-0000-7000-8000-0000000000ff")
ARCHIVED_AT = datetime(2026, 11, 1, tzinfo=UTC)
CRITERIA = LookupResourceCriteria(
    q="store",
    archived=ArchivedFilter.ALL,
    sort=NameSort.NAME,
    order=SortOrder.DESC,
    page=2,
    page_size=10,
)


def archive(fake_payee_repo: FakePayeeRepository, payee: Payee) -> Payee:
    owner, _ = fake_payee_repo.payees[payee.id]
    archived = replace(payee, archived_at=ARCHIVED_AT)
    fake_payee_repo.payees[payee.id] = (owner, archived)
    return archived


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


def test_list_payees_returns_the_repositorys_page_for_the_users_criteria(
    fake_payee_repo: FakePayeeRepository,
) -> None:
    payee = fake_payee_repo.create(USER_ID, "Corner Store")
    fake_payee_repo.create(OTHER_USER_ID, "Supermarket")
    assert list_payees(fake_payee_repo, USER_ID, CRITERIA) == RecordPage([payee], 1)
    assert fake_payee_repo.list_criteria == CRITERIA


def test_update_payee_renames_the_users_payee(
    fake_payee_repo: FakePayeeRepository,
) -> None:
    payee = fake_payee_repo.create(USER_ID, "Corner Store")
    renamed = update_payee(fake_payee_repo, USER_ID, payee.id, "Corner Shop")
    assert renamed == Payee(id=payee.id, name="Corner Shop", archived_at=None)
    assert fake_payee_repo.payees == {payee.id: (USER_ID, renamed)}


def test_update_payee_raises_not_found_for_another_users_payee(
    fake_payee_repo: FakePayeeRepository,
) -> None:
    payee = fake_payee_repo.create(OTHER_USER_ID, "Corner Store")
    with pytest.raises(NotFoundError):
        update_payee(fake_payee_repo, USER_ID, payee.id, "Corner Shop")


def test_update_payee_raises_archived_for_an_archived_payee_even_if_the_name_is_used(
    fake_payee_repo: FakePayeeRepository,
) -> None:
    fake_payee_repo.create(USER_ID, "Supermarket")
    payee = archive(fake_payee_repo, fake_payee_repo.create(USER_ID, "Corner Store"))
    with pytest.raises(ArchivedError):
        update_payee(fake_payee_repo, USER_ID, payee.id, "Supermarket")


def test_update_payee_raises_name_conflict_naming_the_payee_with_the_name(
    fake_payee_repo: FakePayeeRepository,
) -> None:
    existing = fake_payee_repo.create(USER_ID, "Supermarket")
    payee = fake_payee_repo.create(USER_ID, "Corner Store")
    with pytest.raises(PayeeNameConflictError) as raised:
        update_payee(fake_payee_repo, USER_ID, payee.id, "supermarket")
    assert raised.value.existing == existing
