from pydantic import BaseModel, Field
from typing import Optional


class HealthOut(BaseModel):
    status: str = Field(..., description="Current status of the service (alive, ready, unhealthy).")
    error: Optional[str] = Field(None, description="Optional error detail if status is unhealthy.")


class MetricsOut(BaseModel):
    uptime_seconds: float = Field(..., description="Seconds since application startup.")
    app: str = Field(..., description="Application name.")
    version: str = Field(..., description="Build or release version string.")
    debug: bool = Field(..., description="Indicates whether the app is running in debug mode.")
