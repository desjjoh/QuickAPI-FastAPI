from pydantic import BaseModel, Field


class ReadyResponse(BaseModel):
    ready: bool = Field(
        ...,
        description="Whether the system is currently ready.",
        examples=[True],
    )
