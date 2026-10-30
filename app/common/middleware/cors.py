from __future__ import annotations

from collections.abc import Iterable

from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.handlers.exception_handler import http_exception_handler


class CustomCORSASGIMiddleware:

    def __init__(
        self,
        app: ASGIApp,
        *,
        origin: str | list[str],
        methods: Iterable[str],
        allowed_headers: Iterable[str],
        exposed_headers: Iterable[str],
        credentials: bool = False,
        max_age: int = 86400,
    ) -> None:
        self.app = app
        self.opts_origin = origin
        self.opts_methods = list(dict.fromkeys(m.upper() for m in methods))
        self.opts_allowed_headers = list(allowed_headers)
        self.opts_exposed_headers = list(exposed_headers)
        self.credentials = credentials
        self.max_age = max_age

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        response_headers: dict[str, str] = {}

        async def send_wrapper(message: Message) -> None:
            if message['type'] == 'http.response.start':
                outgoing = MutableHeaders(scope=message)
                vary = {
                    token.strip().lower(): token.strip()
                    for value in outgoing.getlist('vary')
                    for token in value.split(',')
                    if token.strip()
                }

                for name in ['Origin'] + (
                    ['Access-Control-Request-Method', 'Access-Control-Request-Headers']
                    if scope['method'] == 'OPTIONS'
                    else []
                ):
                    vary.setdefault(name.lower(), name)

                outgoing['vary'] = '*' if '*' in vary else ', '.join(vary.values())

                for name, value in response_headers.items():
                    outgoing[name] = value

            await send(message)

        try:
            await self._run_cors_logic(scope, receive, send_wrapper, response_headers)
        except HTTPException as exc:
            request = Request(scope, receive=receive)
            response = await http_exception_handler(request, exc)

            await response(scope, receive, send_wrapper)

    async def _run_cors_logic(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        response_headers: dict[str, str],
    ) -> None:
        method = scope['method']
        headers = self._extract_headers(scope)
        origin = headers.get('origin')

        if not self._is_allowed_origin(origin):
            raise HTTPException(
                status_code=403,
                detail=f"CORS origin '{origin}' not allowed.",
            )

        if origin:
            response_headers['access-control-allow-origin'] = origin

        if (
            origin
            and method == 'OPTIONS'
            and headers.get('access-control-request-method')
        ):
            requested_method = headers['access-control-request-method']
            requested_headers = (
                [
                    item.strip().lower()
                    for item in headers.get('access-control-request-headers', '').split(
                        ','
                    )
                ]
                if 'access-control-request-headers' in headers
                else []
            )
            allowed_headers = {item.lower() for item in self.opts_allowed_headers}

            if requested_method not in self.opts_methods or any(
                item not in allowed_headers for item in requested_headers
            ):
                raise HTTPException(
                    status_code=403,
                    detail='CORS preflight method or headers not allowed.',
                )

        response_headers.update(
            {
                'access-control-allow-methods': ', '.join(self.opts_methods),
                'access-control-allow-headers': ', '.join(self.opts_allowed_headers),
                'access-control-expose-headers': ', '.join(self.opts_exposed_headers),
                'access-control-max-age': str(self.max_age),
            }
        )
        if self.credentials:
            response_headers['access-control-allow-credentials'] = 'true'

        if method == 'OPTIONS':
            await Response(status_code=204)(scope, receive, send)

            return

        await self.app(scope, receive, send)

    @staticmethod
    def _extract_headers(scope: Scope) -> dict[str, str]:
        return {
            key.decode().lower(): value.decode()
            for key, value in scope.get("headers", [])
        }

    def _is_allowed_origin(self, origin: str | None) -> bool:
        if not origin:
            return True

        opts: str | list[str] = self.opts_origin

        if opts == "*" or (isinstance(opts, list) and "*" in opts):
            return True

        if isinstance(opts, list):
            return origin in opts

        return opts == origin
