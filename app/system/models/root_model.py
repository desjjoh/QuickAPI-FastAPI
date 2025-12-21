from pydantic import BaseModel, Field


class RootResponse(BaseModel):
    message: str = Field(
        ...,
        description="A friendly greeting from the API",
        examples=["Hello World! Welcome to FastAPI!"],
    )
