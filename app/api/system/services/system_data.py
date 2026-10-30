"""Typed collection results without HTTP model validation."""

from datetime import datetime
from typing import Literal, TypedDict


class HealthData(TypedDict):
    alive: bool
    uptime: float
    timestamp: datetime


class InfoData(TypedDict):
    name: str
    version: str
    environment: Literal['development', 'production', 'test']
    hostname: str
    pid: int
    python_version: str
    platform: str
    architecture: str
    started_at: datetime
    timezone: str


class CpuData(TypedDict):
    cores: int
    model: str
    load_average: tuple[float, float, float]


class MemoryData(TypedDict):
    total_bytes: int
    available_bytes: int
    used_bytes: int
    percentage: float


class ProcessData(TypedDict):
    rss_bytes: int
    heap_total_bytes: int
    heap_used_bytes: int
    external_bytes: int
    active_handles: int


class OsData(TypedDict):
    platform: str
    release: str


class SystemData(TypedDict):
    uptime: float
    timestamp: int
    event_loop_lag: float
    db: Literal['connected', 'disconnected']
    cpu: CpuData
    memory: MemoryData
    process: ProcessData
    os: OsData
