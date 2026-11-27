"""Payee endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request, Response, status

from app.api.dependencies import (
    CurrentUserDep,
    IdempotentCreateDep,
    PayeeRepositoryDep,
)
from app.api.idempotency import NewRecord
from app.api.openapi import documented_problem
from app.api.problems import NAME_CONFLICT, ProblemError
from app.api.routing import SingleValueRoute
from app.schemas.pagination import ArchivableLookupResourceParameters
from app.schemas.payees import (
    PayeeNameConflictProblem,
    PayeePage,
    PayeeReference,
    PayeeRequest,
    PayeeResponse,
)
from app.services import payees

router = APIRouter(prefix="/payees", tags=["payees"], route_class=SingleValueRoute)

# camelCase on the wire, as the rest of the API is.
PayeeIdPath = Annotated[UUID, Path(alias="payeeId")]
PAYEE_NOT_FOUND = documented_problem(
    "The current user has no payee with this id, or the id is malformed"
)


@router.get(
    "",
    operation_id="listPayees",
    summary="List payees",
    description="Return one page of the current user's payees, active ones by"
    " default, sorted by name.",
    response_description="The page of payees",
)
def list_payees(
    parameters: Annotated[ArchivableLookupResourceParameters, Query()],
    payee_repo: PayeeRepositoryDep,
    user: CurrentUserDep,
) -> PayeePage:
    """Return one page of the current user's payees.

    Args:
        parameters: Which payees to list, and which page of them.
        payee_repo: The repository to list the payees from.
        user: The current user.

    Returns:
        The page of payees.
    """
    page = payees.list_payees(payee_repo, user.id, parameters.criteria())
    records = [PayeeResponse.from_payee(payee) for payee in page.records]
    return PayeePage.build(records, parameters, page.total_items)


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
        },
        409: documented_problem(
            "The current user already has a payee with this name, ignoring case,"
            " archived or not; `existing` names it",
            PayeeNameConflictProblem,
        ),
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

    Raises:
        ProblemError: A name conflict, if the user already has a payee with
            the name.
    """

    def create() -> NewRecord:
        try:
            payee = payees.create_payee(payee_repo, user.id, body.name)
        except payees.PayeeNameConflictError as error:
            raise name_conflict_problem(error) from error
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


@router.put(
    "/{payeeId}",
    operation_id="updatePayee",
    summary="Update a payee",
    description="Update the entire payee, one of the current user's active ones."
    " Archive or unarchive a payee with its own endpoints.",
    response_description="The updated payee",
    responses={
        404: PAYEE_NOT_FOUND,
        409: documented_problem(
            "The payee is archived (`/problems/archived`), or the current user"
            " already has another payee with this name, ignoring case, archived"
            " or not (`/problems/name-conflict`, with `existing` naming it)"
        ),
    },
)
def update_payee(
    payee_id: PayeeIdPath,
    body: PayeeRequest,
    payee_repo: PayeeRepositoryDep,
    user: CurrentUserDep,
) -> PayeeResponse:
    """Update the entire payee, one of the current user's active ones.

    Args:
        payee_id: The id of the payee to update.
        body: The payee's new values.
        payee_repo: The repository the payee is stored in.
        user: The current user.

    Returns:
        The updated payee.

    Raises:
        ProblemError: A name conflict, if the user already has another payee
            with the name.
    """
    try:
        payee = payees.update_payee(payee_repo, user.id, payee_id, body.name)
    except payees.PayeeNameConflictError as error:
        raise name_conflict_problem(error) from error
    return PayeeResponse.from_payee(payee)


@router.delete(
    "/{payeeId}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deletePayee",
    summary="Delete a payee",
    description="Delete one of the current user's payees, archived or not. A"
    " payee that a transaction uses can't be deleted; archive it instead.",
    response_description="The payee was deleted",
    responses={
        404: PAYEE_NOT_FOUND,
        409: documented_problem(
            "A transaction uses the payee (`/problems/in-use/transaction`), so it"
            " can't be deleted; archive it instead"
        ),
    },
)
def delete_payee(
    payee_id: PayeeIdPath, payee_repo: PayeeRepositoryDep, user: CurrentUserDep
) -> None:
    """Delete one of the current user's payees, archived or not.

    Args:
        payee_id: The id of the payee to delete.
        payee_repo: The repository the payee is stored in.
        user: The current user.
    """
    payees.delete_payee(payee_repo, user.id, payee_id)


@router.post(
    "/{payeeId}/archive",
    operation_id="archivePayee",
    summary="Archive a payee",
    description="Archive one of the current user's payees, which hides it from"
    " lists by default. Archiving an archived payee changes nothing, so its"
    " `archivedAt` keeps its first value and the request is safe to repeat.",
    response_description="The archived payee",
    responses={404: PAYEE_NOT_FOUND},
)
def archive_payee(
    payee_id: PayeeIdPath, payee_repo: PayeeRepositoryDep, user: CurrentUserDep
) -> PayeeResponse:
    """Archive one of the current user's payees, leaving an archived one unchanged.

    Args:
        payee_id: The id of the payee to archive.
        payee_repo: The repository the payee is stored in.
        user: The current user.

    Returns:
        The archived payee.
    """
    return PayeeResponse.from_payee(payees.archive_payee(payee_repo, user.id, payee_id))


@router.post(
    "/{payeeId}/unarchive",
    operation_id="unarchivePayee",
    summary="Unarchive a payee",
    description="Unarchive one of the current user's payees. Unarchiving an"
    " active payee changes nothing, so the request is safe to repeat.",
    response_description="The active payee",
    responses={404: PAYEE_NOT_FOUND},
)
def unarchive_payee(
    payee_id: PayeeIdPath, payee_repo: PayeeRepositoryDep, user: CurrentUserDep
) -> PayeeResponse:
    """Unarchive one of the current user's payees, leaving an active one unchanged.

    Args:
        payee_id: The id of the payee to unarchive.
        payee_repo: The repository the payee is stored in.
        user: The current user.

    Returns:
        The active payee.
    """
    return PayeeResponse.from_payee(
        payees.unarchive_payee(payee_repo, user.id, payee_id)
    )


def name_conflict_problem(error: payees.PayeeNameConflictError) -> ProblemError:
    """Build the name conflict problem for a payee's name.

    Args:
        error: The conflict, naming the payee that already has the name.

    Returns:
        The problem, with ``existing`` naming that payee.
    """
    return ProblemError(
        NAME_CONFLICT,
        f"A payee named '{error.existing.name}' already exists.",
        existing=PayeeReference.from_payee(error.existing),
    )
