import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.system.models.info_model import InfoResponse
from app.api.system.models.live_model import HealthResponse
from app.api.system.models.ready_model import ReadyCheck, ReadyResponse
from app.api.system.models.root_model import RootResponse
from app.api.system.models.system_model import SystemResponse
from app.api.system.services.system_service import (
    SystemDiagnosticsService,
    SystemInfoService,
)
from app.common.handlers.lifecycle_handler import LifecycleHandler

router: APIRouter = APIRouter(tags=["System"])
_start_time: float = time.perf_counter()
_favicon_path: Path = Path(__file__).resolve().parents[3] / "public" / "favicon.ico"


## GET /favicon.ico
@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(_favicon_path, media_type="image/x-icon")


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
    description="Reports whether the API process is alive, without checking dependencies.",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
)
async def live_probe(request: Request) -> HealthResponse:
    lifecycle: LifecycleHandler = request.app.state.lifecycle
    alive: bool = lifecycle.is_alive()
    uptime: float = round(
        time.perf_counter() - request.app.state.monotonic_start,
        3,
    )
    timestamp: datetime = request.app.state.initialization_timestamp + timedelta(
        seconds=uptime
    )

    return HealthResponse.from_alive(
        alive=alive,
        uptime=uptime,
        timestamp=timestamp,
    )


## GET /ready
@router.get(
    "/ready",
    summary="Report application readiness state.",
    description="Reports whether startup is complete and required services are healthy.",
    response_model=ReadyResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Application or one of its required services is not ready.",
            "model": ReadyResponse,
        }
    },
)
async def ready_probe(request: Request) -> JSONResponse:
    lifecycle: LifecycleHandler = request.app.state.lifecycle
    app_ready: bool = lifecycle.is_ready()
    results = await lifecycle.check_services()
    checks = [
        ReadyCheck(
            name=result.name,
            status=result.status,
            response_time_ms=result.response_time_ms,
        )
        for result in results
    ]
    ready = app_ready and all(result.is_up for result in results)
    payload = ReadyResponse.from_state(ready=ready, checks=checks)
    return JSONResponse(
        status_code=(
            status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
        ),
        content=payload.model_dump(mode="json"),
    )


## GET /info
@router.get(
    "/info",
    summary="Return application and runtime metadata.",
    description="Returns public application identity and Python runtime metadata.",
    response_model=InfoResponse,
    status_code=status.HTTP_200_OK,
)
async def info(request: Request) -> InfoResponse:
    service: SystemInfoService = request.app.state.system_info
    return service.info()


## GET /system
@router.get(
    "/system",
    summary="Return system-level diagnostics.",
    description="Returns bounded host, process, event-loop, and database diagnostics.",
    response_model=SystemResponse,
    status_code=status.HTTP_200_OK,
)
async def system(request: Request) -> SystemResponse:
    service: SystemDiagnosticsService = request.app.state.system_diagnostics
    return await service.collect()


## GET /metrics
@router.get(
    "/metrics",
    summary="Return Prometheus metrics.",
    description=(
        "Returns Prometheus plaintext exposition data with media type "
        f"`{CONTENT_TYPE_LATEST}`; this response has no JSON schema."
    ),
    response_class=Response,
    responses={
        200: {
            "description": "Prometheus metrics in plaintext format.",
            "content": {
                CONTENT_TYPE_LATEST: {
                    "example": (
                        "# HELP http_requests_total Total HTTP requests\n"
                        "# TYPE http_requests_total counter\n"
                        "http_requests_total{method=\"GET\",path=\"/ready\",status=\"200\"} 42"
                    )
                }
            },
        }
    },
)
async def metrics() -> Response:
    data = generate_latest()
    return Response(data, media_type=CONTENT_TYPE_LATEST)
