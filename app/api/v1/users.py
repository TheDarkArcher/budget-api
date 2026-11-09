"""User endpoints."""

from fastapi import APIRouter

from app.api.dependencies import CurrentUserDep
from app.schemas.users import UserResponse

router = APIRouter(tags=["users"])


@router.get("/me", response_description="The current user")
def me(user: CurrentUserDep) -> UserResponse:
    """Return the user the request acts as.

    Args:
        user: The current user.

    Returns:
        The current user's id and name.
    """
    return UserResponse(id=user.id, name=user.name)
