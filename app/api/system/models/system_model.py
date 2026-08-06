from typing import Literal

from pydantic import BaseModel, Field


class SystemResponse(BaseModel):
    uptime: float = Field(
        ...,
        description="Application uptime in seconds.",
        examples=[123.45],
    )

    timestamp: int = Field(
        ...,
        description="Current timestamp in milliseconds since Unix epoch.",
        examples=[1_732_133_579_791],
    )

    event_loop_lag: float = Field(
        ...,
        description="Approximate event loop lag in milliseconds.",
        examples=[3.21],
    )

    db: Literal["connected", "disconnected"] = Field(
        ...,
        description="Database connectivity status.",
        examples=["connected"],
    )
