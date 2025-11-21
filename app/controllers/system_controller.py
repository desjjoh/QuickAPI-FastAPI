import os
import socket
import time
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status

from app.config.environment import settings
from app.handlers.lifecycle_handler import lifecycle
from app.models.error_model import ErrorResponse
from app.models.system_model import (
    HealthResponse,
    InfoResponse,
    ReadyResponse,
    RootResponse,
    SystemResponse,
)

router = APIRouter(tags=["System"])
_start_time = time.perf_counter()


## GET /
@router.get(
    "/",
    summary="Return a simple greeting message.",
    description="Root endpoint showing application greeting.",
    response_model=RootResponse,
    status_code=status.HTTP_200_OK,
)
async def root() -> RootResponse:
    return RootResponse(message="Hello World! Welcome to FastAPI!")


## GET /health
@router.get(
    "/health",
    summary="Report basic process liveness.",
    description="Liveness check — verifies the process is alive.",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
)
async def live_probe() -> HealthResponse:
    alive = lifecycle.is_alive()
    timestamp = datetime.now(UTC).isoformat()
    uptime = round(time.perf_counter() - _start_time, 3)

    return HealthResponse(alive=alive, uptime=uptime, timestamp=timestamp)


## GET /ready
@router.get(
    "/ready",
    summary="Report application readiness state.",
    description="Readiness check — verifies that the app has completed startup and all required services are healthy.",
    response_model=ReadyResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Application or one of its required services is not ready.",
            "model": ErrorResponse,
        }
    },
)
async def ready_probe() -> ReadyResponse:
    app_ready = lifecycle.is_ready()
    services_healthy = await lifecycle.are_all_services_healthy()

    if not app_ready and services_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application not ready",
        )

    return ReadyResponse(ready=True)


## GET /info
@router.get(
    "/info",
    summary="Return application and runtime metadata.",
    description="Returns application metadata including name, version, environment, hostname, and PID.",
    response_model=InfoResponse,
    status_code=status.HTTP_200_OK,
)
async def info() -> InfoResponse:
    return InfoResponse(
        name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENV,
        hostname=socket.gethostname(),
        pid=os.getpid(),
    )


## GET /system
@router.get(
    "/system",
    summary="Return system-level diagnostics.",
    description="System diagnostics including memory usage, load averages, event loop lag, and database status.",
    response_model=SystemResponse,
    status_code=status.HTTP_200_OK,
)
async def system() -> SystemResponse:
    event_loop_lag = await lifecycle.get_event_loop_lag(samples=1)
    services_healthy = await lifecycle.are_all_services_healthy()

    db_status: Literal["connected", "disconnected"] = (
        "connected" if services_healthy else "disconnected"
    )

    return SystemResponse(
        uptime_s=round(time.perf_counter() - _start_time, 3),
        timestamp=int(time.time() * 1000),
        event_loop_lag_ms=round(event_loop_lag, 3),
        db=db_status,
    )


# @router.get("/metrics", response_model=MetricsOut)
# async def system_metrics() -> MetricsOut:
#     uptime = time.perf_counter() - _start_time
#     return MetricsOut(
#         uptime_seconds=uptime, app=settings.APP_NAME, version="1.0.0", debug=True
#     )
