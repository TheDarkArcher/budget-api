"""Version 1 of the API.

The current-user resolver runs in front of every request, whether or not
its endpoint asks for the user.
"""

from fastapi import APIRouter

from app.api.problems import documented_problem
from app.api.v1 import users

router = APIRouter(
    prefix="/api/v1",
    responses={403: documented_problem("The current user is not authorised")},
)
router.include_router(users.router)
