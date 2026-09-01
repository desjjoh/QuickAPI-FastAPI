from pydantic import BaseModel, ConfigDict, Field


class RootResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    message: str = Field(
        ...,
        description="A friendly greeting from the API",
        examples=["Hello World! Welcome to FastAPI!"],
    )
