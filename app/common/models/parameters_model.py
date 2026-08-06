from typing import Annotated
from uuid import uuid4

from fastapi import Path

HEX16_PATTERN = r"^[0-9a-f]{16}$"


HexId = Annotated[
    str,
    Path(
        title="16-character hex ID",
        description="Must be exactly 16 hex characters (0-9, a-f).",
        pattern=HEX16_PATTERN,
        min_length=16,
        max_length=16,
        examples=[uuid4().hex[:16]],
    ),
]
