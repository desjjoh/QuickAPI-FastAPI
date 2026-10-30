from fastapi import Depends, Response, status
from fastapi.responses import FileResponse
from prometheus_client import CONTENT_TYPE_LATEST

from app.api.system.models.info_model import InfoResponse
from app.api.system.models.live_model import HealthResponse
from app.api.system.models.ready_model import ReadyResponse
from app.api.system.models.root_model import RootResponse
from app.api.system.models.system_model import SystemResponse
from app.api.system.services.system_service import (
    SystemDiagnosticsService,
    SystemInfoService,
    SystemService,
    get_system_diagnostics_service,
    get_system_info_service,
    get_system_service,
)
from app.common.handlers.flexible_router import FlexibleRouter

router = FlexibleRouter(tags=["System"])
diagnostics_router = FlexibleRouter(tags=["System"])
metrics_router = FlexibleRouter(tags=["System"])


## GET /favicon.ico
@router.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
async def favicon(service: SystemService = Depends(get_system_service)) -> FileResponse:
    path = service.favicon()

    return FileResponse(path, media_type="image/x-icon")


## GET /
@router.get(
    "/",
    summary="Return a simple greeting message.",
    description="Root endpoint showing application greeting.",
    response_model=RootResponse,
    status_code=status.HTTP_200_OK,
)
async def root(service: SystemService = Depends(get_system_service)) -> RootResponse:
    message = service.root()

    return RootResponse(message=message)


## GET /health
@router.get(
    "/health",
    summary="Report basic process liveness.",
    description="Reports whether the API process is alive, without checking dependencies.",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
)
async def live_probe(
    service: SystemService = Depends(get_system_service),
) -> HealthResponse:
    data = service.live()

    return HealthResponse.from_alive(**data)


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
async def ready_probe(
    response: Response, service: SystemService = Depends(get_system_service)
) -> ReadyResponse:
    ready = await service.ready()
    payload = ReadyResponse.from_state(ready=ready)
    response.status_code = (
        status.HTTP_200_OK if payload.ready else status.HTTP_503_SERVICE_UNAVAILABLE
    )

    return payload


## GET /info
@diagnostics_router.get(
    "/info",
    summary="Return application and runtime metadata.",
    description="Requires DIAGNOSTICS_ENABLED; returns unauthenticated application/runtime metadata.",
    response_model=InfoResponse,
    status_code=status.HTTP_200_OK,
)
async def info(
    service: SystemInfoService = Depends(get_system_info_service),
) -> InfoResponse:
    data = service.info()

    return InfoResponse.model_validate(data)


## GET /system
@diagnostics_router.get(
    "/system",
    summary="Return system-level diagnostics.",
    description="Requires DIAGNOSTICS_ENABLED and deployment-level access restrictions; returns bounded diagnostics.",
    response_model=SystemResponse,
    status_code=status.HTTP_200_OK,
)
async def system(
    service: SystemDiagnosticsService = Depends(get_system_diagnostics_service),
) -> SystemResponse:
    data = await service.collect()

    return SystemResponse.model_validate(data)


## GET /metrics
@metrics_router.get(
    "/metrics",
    summary="Return Prometheus metrics.",
    description=(
        "Requires METRICS_ENABLED and deployment-level access restrictions. "
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
                        "http_requests_total{method=\"GET\",route=\"/api/v1/items/\",status=\"200\"} 42"
                    )
                }
            },
        }
    },
)
async def metrics(service: SystemService = Depends(get_system_service)) -> Response:
    data = service.metrics()

    return Response(data, media_type=CONTENT_TYPE_LATEST)
