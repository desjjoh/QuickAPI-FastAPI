"""Accept either trailing-slash spelling with one documented canonical route."""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter


class FlexibleRouter(APIRouter):
    def add_api_route(
        self, path: str, endpoint: Callable[..., Any], **kwargs: Any
    ) -> None:
        # FastAPI supplies this when copying already-registered routes during
        # include_router(). Preserve both copies without generating aliases again.
        if kwargs.get('route_class_override') is not None or path == '/':
            super().add_api_route(path, endpoint, **kwargs)

            return

        canonical = path.rstrip('/')
        alias_options: dict[str, Any] = {**kwargs, 'include_in_schema': False}

        super().add_api_route(canonical, endpoint, **kwargs)
        super().add_api_route(canonical + '/', endpoint, **alias_options)
