"""Tests for paged lists: their parameters, SQL and response."""

from collections.abc import Callable, Iterator
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

import pytest
from fastapi import APIRouter, FastAPI, Query
from fastapi.testclient import TestClient
from problems import (
    assert_problem,
    parameter_validation_problem,
    without_error_details,
)
from records import add_item, add_item_category, add_payee, add_tag, add_user
from sql import run
from sqlalchemy import Connection, text, tstring

from app.api.dependencies import ConnectionDep, CurrentUserDep
from app.core.dummy_user import DUMMY_USER_ID
from app.core.list_options import ArchivedFilter, NameSort, SortOrder
from app.repositories.lists import LookupResourceCriteria
from app.repositories.sql_lists import (
    SQL_NAME_ORDER,
    SQL_NAME_SORTS,
    SQLLookupResourceLists,
)
from app.schemas.base import ApiModel
from app.schemas.pagination import (
    ArchivableLookupResourceParameters,
    LookupResourceParameters,
    Page,
)

# ===================
# |   Probe lists   |
# ===================


ITEM_CATEGORY_ORDER = {
    SortOrder.ASC: text("lower(item_category_name), lower(name), id"),
    SortOrder.DESC: text("lower(item_category_name) DESC, lower(name) DESC, id DESC"),
}


class ProbeRecord(ApiModel):
    record_name: str


class ProbeItemSort(StrEnum):
    NAME = "name"
    ITEM_CATEGORY = "itemCategory"


class ProbeItemParameters(LookupResourceParameters[ProbeItemSort]):
    pass


def lookup_resource_criteria[Sort: StrEnum](
    parameters: LookupResourceParameters[Sort], archived: ArchivedFilter
) -> LookupResourceCriteria[Sort]:
    """Build the criteria a list request asked for."""
    return LookupResourceCriteria(
        q=parameters.q,
        archived=archived,
        sort=parameters.sort,
        order=parameters.order,
        page=parameters.page,
        page_size=parameters.page_size,
    )


def list_payees(
    connection: ConnectionDep,
    user: CurrentUserDep,
    parameters: Annotated[ArchivableLookupResourceParameters, Query()],
) -> Page[ProbeRecord]:
    payees = tstring(
        t"SELECT id, name, archived_at FROM payees WHERE user_id = {user.id}"
    )
    criteria = lookup_resource_criteria(parameters, parameters.archived)
    page = SQLLookupResourceLists(connection, SQL_NAME_SORTS).fetch_page(
        payees, criteria
    )
    records = [ProbeRecord(record_name=row.name) for row in page.records]
    return Page.build(records, parameters, page.total_items)


def list_tags(
    connection: ConnectionDep,
    user: CurrentUserDep,
    parameters: Annotated[LookupResourceParameters, Query()],
) -> Page[ProbeRecord]:
    tags = tstring(
        t"SELECT id, name, NULL AS archived_at FROM tags WHERE user_id = {user.id}"
    )
    criteria = lookup_resource_criteria(parameters, ArchivedFilter.ALL)
    page = SQLLookupResourceLists(connection, SQL_NAME_SORTS).fetch_page(tags, criteria)
    records = [ProbeRecord(record_name=row.name) for row in page.records]
    return Page.build(records, parameters, page.total_items)


def list_items(
    connection: ConnectionDep,
    user: CurrentUserDep,
    parameters: Annotated[ProbeItemParameters, Query()],
) -> Page[ProbeRecord]:
    items = tstring(t"""
        SELECT
            items.id,
            items.name,
            items.archived_at,
            item_categories.name AS item_category_name
        FROM items
            JOIN item_categories ON item_categories.id = items.item_category_id
        WHERE items.user_id = {user.id}
    """)
    criteria = lookup_resource_criteria(parameters, ArchivedFilter.ALL)
    sorts = {
        ProbeItemSort.NAME: SQL_NAME_ORDER,
        ProbeItemSort.ITEM_CATEGORY: ITEM_CATEGORY_ORDER,
    }
    page = SQLLookupResourceLists(connection, sorts).fetch_page(items, criteria)
    records = [ProbeRecord(record_name=row.name) for row in page.records]
    return Page.build(records, parameters, page.total_items)


# ============================
# |   Helpers and fixtures   |
# ============================


def expected_single_page(listed: list[str], page_size: int = 25) -> dict[str, Any]:
    """The body of a list whose records, in order, all fit on one page."""
    return {
        "data": [{"recordName": name} for name in listed],
        "page": 1,
        "pageSize": page_size,
        "totalItems": len(listed),
        "totalPages": 1 if listed else 0,
    }


@pytest.fixture
def probe_client(
    probe_router: APIRouter, make_app: Callable[[], FastAPI]
) -> Iterator[TestClient]:
    probe_router.add_api_route("/test/payees", list_payees, methods=["GET"])
    probe_router.add_api_route("/test/tags", list_tags, methods=["GET"])
    probe_router.add_api_route("/test/items", list_items, methods=["GET"])

    with TestClient(make_app()) as client:
        yield client


@pytest.fixture
def payees(connection: Connection, dummy_user: None) -> None:
    """Payees of the dummy user, in neither name nor case order."""
    for name in ("cherry", "Apple", "banana", "Damson", "Elder"):
        add_payee(connection, DUMMY_USER_ID, name)
    add_payee(connection, DUMMY_USER_ID, "Archived", archived=True)


# ==============
# |   Paging   |
# ==============


@pytest.mark.usefixtures("payees")
def test_list_defaults_to_the_first_page_of_active_records_by_name(
    probe_client: TestClient,
) -> None:
    response = probe_client.get("/api/v1/test/payees")
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"recordName": "Apple"},
            {"recordName": "banana"},
            {"recordName": "cherry"},
            {"recordName": "Damson"},
            {"recordName": "Elder"},
        ],
        "page": 1,
        "pageSize": 25,
        "totalItems": 5,
        "totalPages": 1,
    }


@pytest.mark.usefixtures("payees")
@pytest.mark.parametrize(
    ("page", "listed"),
    [
        (1, ["Apple", "banana"]),
        (3, ["Elder"]),
        (4, []),
        (10**30, []),
    ],
)
def test_page_holds_its_records_and_the_totals(
    probe_client: TestClient, page: int, listed: list[str]
) -> None:
    response = probe_client.get(
        "/api/v1/test/payees", params={"page": page, "pageSize": 2}
    )
    assert response.status_code == 200
    assert response.json() == {
        "data": [{"recordName": name} for name in listed],
        "page": page,
        "pageSize": 2,
        "totalItems": 5,
        "totalPages": 3,
    }


@pytest.mark.usefixtures("payees")
def test_last_page_is_full_when_the_total_is_a_multiple_of_the_page_size(
    probe_client: TestClient,
) -> None:
    listed = ["Apple", "banana", "cherry", "Damson", "Elder"]
    response = probe_client.get(
        "/api/v1/test/payees", params={"page": 1, "pageSize": 5}
    )
    assert response.status_code == 200
    assert response.json() == expected_single_page(listed, page_size=5)


@pytest.mark.usefixtures("dummy_user")
def test_empty_result_has_no_pages(probe_client: TestClient) -> None:
    response = probe_client.get("/api/v1/test/payees")
    assert response.status_code == 200
    assert response.json() == {
        "data": [],
        "page": 1,
        "pageSize": 25,
        "totalItems": 0,
        "totalPages": 0,
    }


# ===============================
# |   Searching and filtering   |
# ===============================


@pytest.mark.usefixtures("payees")
@pytest.mark.parametrize(
    ("archived", "listed"),
    [
        ("false", ["Apple", "banana", "cherry", "Damson", "Elder"]),
        ("true", ["Archived"]),
        ("all", ["Apple", "Archived", "banana", "cherry", "Damson", "Elder"]),
    ],
)
def test_archived_chooses_which_records_are_listed(
    probe_client: TestClient, archived: str, listed: list[str]
) -> None:
    response = probe_client.get("/api/v1/test/payees", params={"archived": archived})
    assert response.status_code == 200
    assert response.json() == expected_single_page(listed)


@pytest.mark.usefixtures("dummy_user")
def test_records_that_are_never_archived_take_no_archived_filter(
    probe_client: TestClient, connection: Connection
) -> None:
    add_tag(connection, DUMMY_USER_ID, "Snack")
    response = probe_client.get("/api/v1/test/tags", params={"archived": "true"})
    assert response.status_code == 200
    assert response.json() == expected_single_page(["Snack"])


@pytest.mark.usefixtures("dummy_user")
@pytest.mark.parametrize(
    ("q", "listed"),
    [
        ("CORNER", ["Corner Store"]),
        ("ner st", ["Corner Store"]),
        ("  corner \t", ["Corner Store"]),
        ("é", ["CAFÉ"]),
        ("%", ["50% Off"]),
        ("_", ["snake_case"]),
        ("/", ["and/or"]),
        ("\\", ["back\\slash"]),
        ("missing", []),
        (f" {'x' * 100} ", []),
    ],
)
def test_q_matches_names_that_contain_it(
    probe_client: TestClient, connection: Connection, q: str, listed: list[str]
) -> None:
    for name in (
        "Corner Store",
        "CAFÉ",
        "50% Off",
        "snake_case",
        "and/or",
        "back\\slash",
    ):
        add_payee(connection, DUMMY_USER_ID, name)
    response = probe_client.get("/api/v1/test/payees", params={"q": q})
    assert response.status_code == 200
    assert response.json() == expected_single_page(listed)


@pytest.mark.usefixtures("payees")
@pytest.mark.parametrize("q", ["", "   "])
def test_blank_q_is_ignored(probe_client: TestClient, q: str) -> None:
    listed = ["Apple", "banana", "cherry", "Damson", "Elder"]
    response = probe_client.get("/api/v1/test/payees", params={"q": q})
    assert response.status_code == 200
    assert response.json() == expected_single_page(listed)


# ===============
# |   Sorting   |
# ===============


@pytest.mark.usefixtures("payees")
def test_order_desc_lists_names_in_reverse(probe_client: TestClient) -> None:
    listed = ["Elder", "Damson", "cherry", "banana", "Apple"]
    response = probe_client.get(
        "/api/v1/test/payees", params={"sort": "name", "order": "desc"}
    )
    assert response.status_code == 200
    assert response.json() == expected_single_page(listed)


def test_equal_sort_keys_are_ordered_by_id_in_the_same_order(
    connection: Connection,
) -> None:
    # One user's names are unique, so the tie is between two users' payees.
    for payee_id, name in (("b", "SAME"), ("a", "same")):
        run(
            connection,
            "INSERT INTO payees (id, user_id, name) VALUES (:id, :user, :name)",
            id=UUID(f"00000000-0000-7000-8000-00000000000{payee_id}"),
            user=add_user(connection, name),
            name=name,
        )

    everyones_payees = tstring(t"SELECT id, name, archived_at FROM payees")
    lists = SQLLookupResourceLists(connection, SQL_NAME_SORTS)

    def listed(order: SortOrder, page: int = 1, page_size: int = 2) -> list[str]:
        criteria = LookupResourceCriteria(
            q="",
            archived=ArchivedFilter.ALL,
            sort=NameSort.NAME,
            order=order,
            page=page,
            page_size=page_size,
        )
        fetched = lists.fetch_page(everyones_payees, criteria)
        return [row.name for row in fetched.records]

    assert listed(SortOrder.ASC) == ["same", "SAME"]
    assert listed(SortOrder.DESC) == ["SAME", "same"]
    assert listed(SortOrder.ASC, page=1, page_size=1) == ["same"]
    assert listed(SortOrder.ASC, page=2, page_size=1) == ["SAME"]


@pytest.mark.usefixtures("dummy_user")
def test_order_reverses_every_key_of_a_sort(
    probe_client: TestClient, connection: Connection
) -> None:
    for category, items in (("pantry", ("Zest", "rice")), ("Dairy", ("Milk",))):
        category_id = add_item_category(connection, DUMMY_USER_ID, category)
        for item in items:
            add_item(connection, DUMMY_USER_ID, category_id, item)
    ascending = probe_client.get("/api/v1/test/items", params={"sort": "itemCategory"})
    assert ascending.status_code == 200
    assert ascending.json() == expected_single_page(["Milk", "rice", "Zest"])
    descending = probe_client.get(
        "/api/v1/test/items", params={"sort": "itemCategory", "order": "desc"}
    )
    assert descending.status_code == 200
    assert descending.json() == expected_single_page(["Zest", "rice", "Milk"])


# ==========================
# |   Allowed parameters   |
# ==========================


@pytest.mark.usefixtures("dummy_user")
@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("q", "x" * 101),
        ("q", "nul\x00"),
        ("archived", "maybe"),
        ("archived", ""),
        ("sort", "archivedAt"),
        ("sort", "itemCategory"),
        ("order", "up"),
        ("order", "DESC"),
        ("page", "0"),
        ("page", "-1"),
        ("page", "first"),
        ("pageSize", "0"),
        ("pageSize", "201"),
        ("pageSize", "many"),
    ],
)
def test_parameter_outside_its_allowed_values_returns_validation_problem(
    probe_client: TestClient, parameter: str, value: str
) -> None:
    response = probe_client.get("/api/v1/test/payees", params={parameter: value})
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == parameter_validation_problem(
        parameter
    )


@pytest.mark.usefixtures("dummy_user")
@pytest.mark.parametrize("page_size", [1, 200])
def test_page_size_accepts_its_limits(probe_client: TestClient, page_size: int) -> None:
    response = probe_client.get("/api/v1/test/payees", params={"pageSize": page_size})
    assert response.status_code == 200
    assert response.json() == expected_single_page([], page_size=page_size)


@pytest.mark.usefixtures("dummy_user")
def test_snake_case_parameter_name_is_ignored(probe_client: TestClient) -> None:
    response = probe_client.get("/api/v1/test/payees", params={"page_size": 5})
    assert response.status_code == 200
    assert response.json() == expected_single_page([])
