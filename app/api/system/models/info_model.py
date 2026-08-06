from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

SEMVER_REGEX = r"^\d+\.\d+\.\d+$"


class InfoResponse(BaseModel):
    name: str = Field(
        ...,
        description="Application name.",
        examples=["quickapi"],
    )

    version: Annotated[str, StringConstraints(pattern=SEMVER_REGEX)] = Field(
        ...,
        description="Application semantic version.",
        examples=["1.0.0"],
    )

    environment: Literal["development", "production", "test"] = Field(
        ...,
        description="Current environment mode.",
        examples=["development"],
    )

    hostname: str = Field(
        ...,
        description="Server hostname.",
        examples=["server-001"],
    )

    pid: int = Field(
        ...,
        description="Process ID.",
        examples=[12345],
    )
