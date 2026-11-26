"""Tests for when a request's database transaction commits."""

from collections.abc import Generator
from contextlib import contextmanager
from uuid import UUID

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from problems import assert_problem
from sqlalchemy import Connection
from sqlalchemy.exc import OperationalError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.dependencies import ConnectionDep
from app.database.engine import ConnectionOpener
from app.main import create_app
from app.repositories.users import SQLUserRepository

WRITTEN_USER_ID = UUID("00000000-0000-7000-8000-0000000000c1")


class ResponseStartRecorder:
    def __init__(self, app: ASGIApp, events: list[str]) -> None:
        self.app = app
        self.events = events

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def recording_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                self.events.append("response started")
            await send(message)

        await self.app(scope, receive, recording_send)


def create_written_user(connection: ConnectionDep) -> None:
    SQLUserRepository(connection).create(WRITTEN_USER_ID, "Written")


def recording_opener(connection: Connection, events: list[str]) -> ConnectionOpener:
    @contextmanager
    def open_savepoint() -> Generator[Connection]:
        with connection.begin_nested():
            yield connection
        events.append("committed")

    return open_savepoint


def failing_endpoint_commit_opener(connection: Connection) -> ConnectionOpener:
    # The current-user resolver's lookup opens the first connection, and the
    # endpoint the second, whose commit fails.
    opened = 0

    @contextmanager
    def open_savepoint() -> Generator[Connection]:
        nonlocal opened
        opened += 1
        savepoint = connection.begin_nested()
        try:
            yield connection
        finally:
            savepoint.rollback()
        if opened > 1:
            raise OperationalError("COMMIT", None, Exception("connection lost"))

    return open_savepoint


@pytest.fixture
def create_route(probe_router: APIRouter) -> None:
    probe_router.add_api_route(
        "/test/create", create_written_user, methods=["POST"], status_code=201
    )


@pytest.mark.usefixtures("dummy_user", "create_route")
def test_a_created_record_is_committed_before_its_response_starts(
    connection: Connection,
) -> None:
    events: list[str] = []
    app = create_app(open_connection=recording_opener(connection, events))
    with TestClient(ResponseStartRecorder(app, events)) as client:
        response = client.post("/api/v1/test/create")
    assert response.status_code == 201
    assert response.json() is None
    # The current-user resolver's lookup commits, then the endpoint's work.
    assert events == ["committed", "committed", "response started"]


@pytest.mark.usefixtures("dummy_user", "create_route")
def test_a_failed_commit_returns_internal_error_problem(
    connection: Connection,
) -> None:
    app = create_app(open_connection=failing_endpoint_commit_opener(connection))
    with TestClient(app) as client:
        response = client.post("/api/v1/test/create")
    problem_body = assert_problem(response, 500)
    assert problem_body == {
        "type": "about:blank",
        "title": "Internal Server Error",
        "status": 500,
        "detail": "An unexpected error occurred.",
    }
