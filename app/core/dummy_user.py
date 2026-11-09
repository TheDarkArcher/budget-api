"""The placeholder user every request acts as until Milestone 3 adds real users."""

from uuid import UUID

# Version 7 format, like generated ids, but clearly not a real timestamp.
DUMMY_USER_ID = UUID("00000000-0000-7000-8000-000000000001")
DUMMY_USER_NAME = "Dummy user"
