from typing import Annotated

from fastapi import Path

ENTITY_ID_PATTERN = r"^[A-Za-z0-9]{16}$"


EntityId = Annotated[
    str,
    Path(
        title="16-character alphanumeric ID",
        description="Must be exactly 16 ASCII letters or digits (A-Z, a-z, 0-9).",
        pattern=ENTITY_ID_PATTERN,
        min_length=16,
        max_length=16,
        examples=['A1b2C3d4E5f6G7h8'],
    ),
]
