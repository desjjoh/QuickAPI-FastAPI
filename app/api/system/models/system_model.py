from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

NonNegativeFloat = Annotated[float, Field(ge=0)]


class StrictSystemModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class CpuDiagnostics(StrictSystemModel):
    cores: int = Field(ge=1, description="Logical CPU count; at least one.")
    model: str = Field(min_length=1, description="Processor identifier or 'unknown'.")
    load_average: tuple[NonNegativeFloat, NonNegativeFloat, NonNegativeFloat] = Field(
        description="One-, five-, and fifteen-minute system load averages."
    )


class MemoryDiagnostics(StrictSystemModel):
    total_bytes: int = Field(ge=0)
    available_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    percentage: float = Field(ge=0, le=100)


class ProcessDiagnostics(StrictSystemModel):
    rss_bytes: int = Field(
        ge=0,
        description="Maximum resident-set size reported for this process.",
    )
    heap_total_bytes: int = Field(
        ge=0,
        description="Peak traced Python allocator bytes, or zero if tracing is off.",
    )
    heap_used_bytes: int = Field(
        ge=0,
        description="Current traced Python allocator bytes, or zero if tracing is off.",
    )
    external_bytes: int = Field(
        ge=0,
        description="Zero: Python has no portable equivalent of external memory.",
    )
    active_handles: int = Field(
        ge=0,
        description="Number of unfinished tasks in the current asyncio event loop.",
    )


class OsDiagnostics(StrictSystemModel):
    platform: str = Field(min_length=1)
    release: str = Field(min_length=1)


class SystemResponse(StrictSystemModel):
    uptime: NonNegativeFloat = Field(description="Application uptime in seconds.")
    timestamp: int = Field(ge=0, description="Unix timestamp in milliseconds.")
    event_loop_lag: NonNegativeFloat = Field(
        description="Approximate event-loop lag in milliseconds."
    )
    db: Literal["connected", "disconnected"]
    cpu: CpuDiagnostics
    memory: MemoryDiagnostics
    process: ProcessDiagnostics
    os: OsDiagnostics
