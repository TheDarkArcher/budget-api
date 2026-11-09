"""Version 1 of the API.

Every request resolves the current user first, whether or not its endpoint
asks for the user.
"""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.api.v1 import users

router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(get_current_user)],
    responses={403: {"description": "The current user is not authorised"}},
)
router.include_router(users.router)
