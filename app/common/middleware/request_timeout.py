from __future__ import annotations

import asyncio

from fastapi import status
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.handlers.exception_handler import http_exception_handler


async def empty_receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


class RequestTimeoutASGIMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        header_timeout: float = 5.0,
        chunk_timeout: float = 2.0,
        total_timeout: float = 10.0,
    ) -> None:
        self.app = app
        self.header_timeout = header_timeout
        self.chunk_timeout = chunk_timeout
        self.total_timeout = total_timeout

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        try:
            await self._run(scope, receive, send)

        except HTTPException as exc:
            request: Request = Request(scope, receive=receive)
            response: JSONResponse = await http_exception_handler(request, exc)

            await response(scope, empty_receive, send)

    async def _run(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:

        start_time: float = asyncio.get_event_loop().time()
        received_headers: bool = False

        async def timed_receive() -> Message:
            nonlocal received_headers

            now: float = asyncio.get_event_loop().time()

            if not received_headers:
                if now - start_time > self.header_timeout:
                    raise HTTPException(
                        status_code=status.HTTP_408_REQUEST_TIMEOUT,
                        detail="Request header timeout exceeded.",
                    )

            try:
                message: Message = await asyncio.wait_for(
                    receive(),
                    timeout=(
                        self.chunk_timeout if received_headers else self.header_timeout
                    ),
                )

            except TimeoutError:
                raise HTTPException(
                    status_code=status.HTTP_408_REQUEST_TIMEOUT,
                    detail="Request chunk timeout exceeded.",
                )

            if message["type"] == "http.request":
                received_headers = True

                if (now - start_time) > self.total_timeout:
                    raise HTTPException(
                        status_code=status.HTTP_408_REQUEST_TIMEOUT,
                        detail="Total request timeout exceeded.",
                    )

            return message

        await self.app(scope, timed_receive, send)
