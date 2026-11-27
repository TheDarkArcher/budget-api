"""Tests for repeating create requests safely with an ``Idempotency-Key``."""

import time
from collections.abc import Callable, Generator, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx2
import pytest
from fastapi import APIRouter, FastAPI, Response
from fastapi.testclient import TestClient
from problems import assert_problem, without_error_details
from pydantic import Field
from records import add_payee, add_user
from sql import count, one, run
from sqlalchemy import Connection, Engine, text

from app.api.dependencies import ConnectionDep, CurrentUserDep, IdempotentCreateDep
from app.api.idempotency import IdempotentCreate, NewRecord
from app.api.problems import IDEMPOTENCY_KEY_MISMATCH, ProblemError
from app.core.errors import NameConflictError
from app.repositories.idempotency_keys import SQLIdempotencyKeyRepository
from app.schemas.base import ApiModel, RequestBody
from app.schemas.fields import DecimalString, Name

# =====================
# |   Probe creates   |
# =====================


KEY = "8e03978e-40d5-43e8-bc93-6894a57f9324"
PATH = "/api/v1/payees"
# How long a repeat has to start waiting, or to finish once it can.
DEADLINE_SECONDS = 10


class PayeeBody(RequestBody):
    name: Name
    credit_limit: DecimalString = Decimal(0)
    tag_ids: list[UUID] = Field(default_factory=list)


class PayeeResponse(ApiModel):
    payee_id: UUID
    name: str


BODY = PayeeBody(name="Milk Shop")
OTHER_BODY = PayeeBody(name="Corner Store")


def idempotent_create(
    connection: Connection,
    user: UUID | None,
    key: str | None = KEY,
    method: str = "POST",
    path: str = PATH,
) -> IdempotentCreate:
    repo = SQLIdempotencyKeyRepository(connection)
    return IdempotentCreate(repo, user, method, path, key)


def payee_creator(connection: Connection, owner: UUID) -> Callable[[], NewRecord]:
    # Every payee has its own name, so only the key can make a repeat wait.
    def create() -> NewRecord:
        name = f"Payee {uuid4()}"
        payee = add_payee(connection, owner, name)
        record = PayeeResponse(payee_id=payee, name=name)
        return NewRecord(record, f"{PATH}/{payee}")

    return create


def create_payee(
    connection: Connection, user: UUID, body: PayeeBody = BODY, key: str | None = KEY
) -> Response:
    # In a transaction, as get_connection gives every endpoint.
    with connection.begin_nested():
        return idempotent_create(connection, user, key).run(
            body, payee_creator(connection, user)
        )


def post_probe_payee(
    body: PayeeBody,
    creation: IdempotentCreateDep,
    connection: ConnectionDep,
    user: CurrentUserDep,
) -> Response:
    return creation.run(body, payee_creator(connection, user.id))


# ============================
# |   Helpers and fixtures   |
# ============================


def post_payee(client: TestClient, keys: list[str]) -> httpx2.Response:
    return client.post(
        "/api/v1/test/payees",
        json={"name": "Milk Shop"},
        headers=[("Idempotency-Key", key) for key in keys],
    )


def expected_created_response(
    connection: Connection, user: UUID
) -> tuple[int, bytes, str, str]:
    """The response the create of the user's only payee should send."""
    payee, name = connection.execute(
        text("SELECT id, name FROM payees WHERE user_id = :user"), {"user": user}
    ).one()
    return (
        201,
        f'{{"payeeId":"{payee}","name":"{name}"}}'.encode(),
        "application/json",
        f"/api/v1/payees/{payee}",
    )


def sent(response: Response) -> tuple[int, bytes, str, str]:
    return (
        response.status_code,
        bytes(response.body),
        response.headers["content-type"],
        response.headers["location"],
    )


def payees_count(connection: Connection, user: UUID) -> int:
    return count(
        connection, "SELECT count(*) FROM payees WHERE user_id = :user", user=user
    )


def age_key(connection: Connection, age: timedelta) -> None:
    run(
        connection,
        "UPDATE idempotency_keys SET created_at = now() - CAST(:age AS interval)"
        " WHERE key = :key",
        age=age,
        key=KEY,
    )


def wait_until_blocked(engine: Engine, waiting: int, blocking: int) -> None:
    deadline = time.monotonic() + DEADLINE_SECONDS
    with engine.connect() as connection:
        while blocking not in one(
            connection, "SELECT pg_blocking_pids(:pid)", pid=waiting
        ):
            assert time.monotonic() < deadline, "the repeat never waited"
            time.sleep(0.01)


@contextmanager
def waiting_repeat(
    engine: Engine, user: UUID
) -> Generator[tuple[Connection, Response, Future[Response]]]:
    """Create a payee, leave it uncommitted, and repeat the request meanwhile."""

    def repeat() -> Response:
        response = create_payee(second, user)
        second.commit()
        return response

    # The first request's connection closes before the thread is waited for, so
    # a failing test never leaves the repeat waiting.
    with (
        engine.connect() as second,
        ThreadPoolExecutor(max_workers=1) as executor,
        engine.connect() as first,
    ):
        response = create_payee(first, user)
        first_pid = one(first, "SELECT pg_backend_pid()")
        second_pid = one(second, "SELECT pg_backend_pid()")
        second.rollback()
        future = executor.submit(repeat)
        wait_until_blocked(engine, waiting=second_pid, blocking=first_pid)
        yield first, response, future


@pytest.fixture
def user(connection: Connection) -> UUID:
    return add_user(connection, "Alice")


@pytest.fixture
def other_user(connection: Connection) -> UUID:
    return add_user(connection, "Bob")


@pytest.fixture
def probe_client(
    probe_router: APIRouter, make_app: Callable[[], FastAPI]
) -> Iterator[TestClient]:
    probe_router.add_api_route("/test/payees", post_probe_payee, methods=["POST"])

    with TestClient(make_app()) as client:
        yield client


@pytest.fixture
def committed_user(engine: Engine) -> Iterator[UUID]:
    with engine.begin() as connection:
        user = add_user(connection, "Carol")
    yield user
    with engine.begin() as connection:
        run(connection, "DELETE FROM payees WHERE user_id = :user", user=user)
        run(connection, "DELETE FROM users WHERE id = :user", user=user)


# ==============================
# |   Idempotency-Key header   |
# ==============================


@pytest.mark.usefixtures("dummy_user")
@pytest.mark.parametrize(
    "key", [pytest.param("", id="empty"), pytest.param("k" * 256, id="too long")]
)
def test_idempotency_key_outside_its_length_returns_validation_problem(
    probe_client: TestClient, key: str
) -> None:
    response = post_payee(probe_client, [key])
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == {
        "type": "/problems/validation",
        "title": "Validation failed",
        "status": 422,
        "detail": "The request isn't valid; see errors for each problem.",
        "errors": [{"parameter": "Idempotency-Key"}],
    }


@pytest.mark.usefixtures("dummy_user")
@pytest.mark.parametrize(
    "key", [pytest.param("k", id="shortest"), pytest.param("k" * 255, id="longest")]
)
def test_idempotency_key_within_its_length_is_accepted(
    probe_client: TestClient, key: str
) -> None:
    assert post_payee(probe_client, [key]).status_code == 201


@pytest.mark.usefixtures("dummy_user")
def test_idempotency_key_sent_twice_returns_validation_problem(
    probe_client: TestClient,
) -> None:
    response = post_payee(probe_client, ["a", "b"])
    problem_body = assert_problem(response, 422)
    assert problem_body == {
        "type": "/problems/validation",
        "title": "Validation failed",
        "status": 422,
        "detail": "The request isn't valid; see errors for each problem.",
        "errors": [
            {
                "detail": "Send this parameter only once.",
                "parameter": "Idempotency-Key",
            }
        ],
    }


def test_idempotency_key_is_documented_with_its_length_and_lifetime(
    probe_client: TestClient,
) -> None:
    paths = probe_client.get("/openapi.json").json()["paths"]
    parameters = paths["/api/v1/test/payees"]["post"]["parameters"]
    [key] = [
        parameter for parameter in parameters if parameter["name"] == "Idempotency-Key"
    ]
    description = key["description"]
    assert "24 hours" in description
    assert key == {
        "name": "Idempotency-Key",
        "in": "header",
        "required": False,
        "description": description,
        "schema": {
            "type": "string",
            "minLength": 1,
            "maxLength": 255,
            "title": "Idempotency-Key",
        },
    }


# ==============================
# |   Requests without a key   |
# ==============================


def test_request_without_a_key_creates_its_record(
    connection: Connection, user: UUID
) -> None:
    response = create_payee(connection, user, key=None)
    assert sent(response) == expected_created_response(connection, user)


def test_requests_without_a_key_are_never_repeats(
    connection: Connection, user: UUID
) -> None:
    create_payee(connection, user, key=None)
    create_payee(connection, user, key=None)
    assert payees_count(connection, user) == 2


# ===============
# |   Repeats   |
# ===============


def test_repeat_replays_the_original_response_without_creating(
    connection: Connection, user: UUID
) -> None:
    original = create_payee(connection, user)
    repeat = create_payee(connection, user)
    assert sent(repeat) == sent(original) == expected_created_response(connection, user)


@pytest.mark.parametrize(
    ("original", "repeat"),
    [
        pytest.param(
            '{"name": "Milk Shop", "creditLimit": "5"}',
            '{"creditLimit": "5", "name": "Milk Shop"}',
            id="key order",
        ),
        pytest.param(
            '{"name": "Milk Shop"}', '{\n  "name":"Milk Shop"\n}', id="JSON whitespace"
        ),
        pytest.param(
            '{"name": "Milk Shop"}', '{"name": " Milk Shop "}', id="trimmed whitespace"
        ),
        pytest.param(
            '{"name": "Milk Shop", "creditLimit": "5"}',
            '{"name": "Milk Shop", "creditLimit": "5.0"}',
            id="trailing zero",
        ),
        pytest.param(
            '{"name": "Milk Shop"}',
            '{"name": "Milk Shop", "creditLimit": "0", "tagIds": []}',
            id="defaults",
        ),
    ],
)
def test_requests_are_the_same_if_their_bodies_match_after_validation(
    connection: Connection, user: UUID, original: str, repeat: str
) -> None:
    first = create_payee(connection, user, PayeeBody.model_validate_json(original))
    second = create_payee(connection, user, PayeeBody.model_validate_json(repeat))
    assert sent(second) == sent(first)


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        pytest.param("PUT", PATH, BODY, id="method"),
        pytest.param("POST", "/api/v1/tags", BODY, id="path"),
        pytest.param("POST", PATH, OTHER_BODY, id="body"),
    ],
)
def test_key_reused_with_a_different_request_returns_mismatch_problem(
    connection: Connection, user: UUID, method: str, path: str, body: PayeeBody
) -> None:
    create_payee(connection, user)
    creation = idempotent_create(connection, user, method=method, path=path)
    with pytest.raises(ProblemError) as raised:
        creation.run(body, payee_creator(connection, user))
    assert raised.value.problem_type == IDEMPOTENCY_KEY_MISMATCH
    assert payees_count(connection, user) == 1


# =================
# |   Key scope   |
# =================


def test_users_can_use_the_same_key(
    connection: Connection, user: UUID, other_user: UUID
) -> None:
    create_payee(connection, user)
    response = create_payee(connection, other_user)
    assert sent(response) == expected_created_response(connection, other_user)


def test_key_sent_with_no_user_is_kept_apart_from_users_keys(
    connection: Connection, user: UUID, other_user: UUID
) -> None:
    create_payee(connection, user)
    creation = idempotent_create(connection, None)
    original = creation.run(BODY, payee_creator(connection, other_user))
    repeat = creation.run(BODY, payee_creator(connection, other_user))
    assert sent(original) == expected_created_response(connection, other_user)
    assert sent(repeat) == sent(original)


# ====================
# |   Key lifetime   |
# ====================


def test_key_lasts_24_hours(connection: Connection, user: UUID) -> None:
    original = create_payee(connection, user)
    age_key(connection, timedelta(hours=23, minutes=59))
    repeat = create_payee(connection, user)
    assert sent(repeat) == sent(original)


def test_key_can_be_reused_after_24_hours(connection: Connection, user: UUID) -> None:
    create_payee(connection, user)
    age_key(connection, timedelta(hours=24, minutes=1))
    original = create_payee(connection, user, OTHER_BODY)
    repeat = create_payee(connection, user, OTHER_BODY)
    assert sent(repeat) == sent(original)
    assert payees_count(connection, user) == 2


# ======================
# |   Failed creates   |
# ======================


def test_failed_create_is_not_stored(connection: Connection, user: UUID) -> None:
    def fail() -> NewRecord:
        raise NameConflictError

    with pytest.raises(NameConflictError), connection.begin_nested():
        idempotent_create(connection, user).run(BODY, fail)
    response = create_payee(connection, user)
    assert sent(response) == expected_created_response(connection, user)


# ==========================
# |   Concurrent repeats   |
# ==========================


def test_repeat_waits_for_the_first_request_and_replays_its_response(
    engine: Engine, connection: Connection, committed_user: UUID
) -> None:
    with waiting_repeat(engine, committed_user) as (first, original, repeat):
        first.commit()
        replayed = repeat.result(DEADLINE_SECONDS)
    assert sent(original) == expected_created_response(connection, committed_user)
    assert sent(replayed) == sent(original)


def test_repeat_waits_for_the_first_request_and_creates_if_it_fails(
    engine: Engine, connection: Connection, committed_user: UUID
) -> None:
    with waiting_repeat(engine, committed_user) as (first, original, repeat):
        first.rollback()
        created = repeat.result(DEADLINE_SECONDS)
    assert sent(created) == expected_created_response(connection, committed_user)
    assert sent(created) != sent(original)
