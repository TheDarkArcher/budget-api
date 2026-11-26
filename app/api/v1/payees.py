"""Payee endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Request, Response, status

from app.api.dependencies import (
    CurrentUserDep,
    IdempotentCreateDep,
    PayeeRepositoryDep,
)
from app.api.idempotency import NewRecord
from app.api.openapi import documented_problem
from app.api.routing import SingleValueRoute
from app.schemas.payees import PayeeRequest, PayeeResponse
from app.services import payees

router = APIRouter(prefix="/payees", tags=["payees"], route_class=SingleValueRoute)

# camelCase on the wire, as the rest of the API is.
PayeeIdPath = Annotated[UUID, Path(alias="payeeId")]
PAYEE_NOT_FOUND = documented_problem(
    "The current user has no payee with this id, or the id is malformed"
)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    operation_id="createPayee",
    summary="Create a payee",
    description="Create an active payee for the current user.",
    responses={
        201: {
            "model": PayeeResponse,
            "description": "The new payee",
            "headers": {
                "Location": {
                    "description": "The new payee's path.",
                    "schema": {"type": "string"},
                }
            },
        }
    },
)
def create_payee(
    body: PayeeRequest,
    request: Request,
    creation: IdempotentCreateDep,
    payee_repo: PayeeRepositoryDep,
    user: CurrentUserDep,
) -> Response:
    """Create an active payee for the current user.

    Args:
        body: The payee to create.
        request: The request, to build the new payee's path.
        creation: The create request, replayed if it repeats an earlier one.
        payee_repo: The repository to store the payee in.
        user: The current user.

    Returns:
        The 201 response holding the new payee.
    """

    def create() -> NewRecord:
        payee = payees.create_payee(payee_repo, user.id, body.name)
        location = request.app.url_path_for("get_payee", payeeId=str(payee.id))
        return NewRecord(PayeeResponse.from_payee(payee), location)

    return creation.run(body, create)


@router.get(
    "/{payeeId}",
    operation_id="getPayee",
    summary="Get a payee",
    description="Return one of the current user's payees, archived or not.",
    response_description="The payee",
    responses={404: PAYEE_NOT_FOUND},
)
def get_payee(
    payee_id: PayeeIdPath, payee_repo: PayeeRepositoryDep, user: CurrentUserDep
) -> PayeeResponse:
    """Return one of the current user's payees, archived or not.

    Args:
        payee_id: The id of the payee to return.
        payee_repo: The repository to look the payee up in.
        user: The current user.

    Returns:
        The payee.
    """
    return PayeeResponse.from_payee(payees.get_payee(payee_repo, user.id, payee_id))
