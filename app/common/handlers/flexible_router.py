"""Express-style HTTP matching without changing parameter values or schema paths."""

import re
from collections.abc import Callable
from functools import cache
from typing import Any

from fastapi import APIRouter
from fastapi.routing import APIRoute
from starlette.routing import BaseRoute, Match, Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class FlexibleRoute(APIRoute):
    def __init__(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        super().__init__(path, endpoint, **kwargs)
        self.path_regex = re.compile(self.path_regex.pattern, re.IGNORECASE)
        self.canonical_path = self.path.rstrip('/') or '/'

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        match, child = super().matches(scope)

        if (
            match is Match.PARTIAL
            and scope['method'] == 'HEAD'
            and 'GET' in self.methods
        ):
            # Respect an explicit HEAD handler even when it was registered later.
            router = scope.get('router') or getattr(scope.get('app'), 'router', None)

            for route in getattr(router, 'routes', ()):
                if (
                    isinstance(route, Route)
                    and route is not self
                    and 'HEAD' in (route.methods or ())
                    and route.matches(scope)[0] is Match.FULL
                ):
                    return match, child

            return Match.FULL, child

        return match, child

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope['method'] == 'HEAD'
            and 'HEAD' not in self.methods
            and 'GET' in self.methods
        ):
            await self.app(scope, receive, send)

            return

        await super().handle(scope, receive, send)


@cache
def _flexible_route_class(route_class: type[APIRoute]) -> type[APIRoute]:
    if issubclass(route_class, FlexibleRoute):
        return route_class

    # FastAPI copies this class during nested include_router() calls. Compose with
    # ApplicationRoute so transaction ownership and response preparation survive.
    return type(f'Flexible{route_class.__name__}', (FlexibleRoute, route_class), {})


def configure_framework_routes(routes: list[BaseRoute]) -> None:
    """Apply the same matching to FastAPI's built-in docs/schema routes."""
    for route in routes:
        if isinstance(route, Route) and not isinstance(route, APIRoute):
            route.path_regex = re.compile(
                route.path_regex.pattern.removesuffix('$') + '/?$', re.IGNORECASE
            )


class HeadResponseASGIMiddleware:
    """Suppress HEAD bodies, including errors outside the selected route."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http' or scope['method'] != 'HEAD':
            await self.app(scope, receive, send)

            return

        async def send_head(message: Message) -> None:
            if message['type'] == 'http.response.body':
                message = {**message, 'body': b''}

            await send(message)

        await self.app(scope, receive, send_head)


class FlexibleRouter(APIRouter):
    def __init__(self, **kwargs: Any) -> None:
        kwargs['route_class'] = _flexible_route_class(
            kwargs.get('route_class', APIRoute)
        )

        super().__init__(**kwargs)

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
