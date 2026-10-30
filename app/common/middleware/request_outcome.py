"""Observe transport outcomes once, independently of downstream cleanup."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from starlette.routing import BaseRoute, Match, Mount, Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_KEY = "quickapi.request_outcome"
_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class RequestOutcome:
    outcome: Literal["completed", "aborted"]
    method: str
    route: str
    duration_ms: float
    headers_sent: bool
    status: int | None


def route_template(
    routes: Sequence[BaseRoute], incoming: Scope, terminal: Scope, prefix: str = ""
) -> str:
    """Follow declared mounts without using concrete root_path values as labels."""
    partial: BaseRoute | None = None

    for route in routes:
        match, child = route.matches(incoming)

        if match is Match.FULL:
            if isinstance(route, Mount):
                return route_template(
                    route.routes, {**incoming, **child}, terminal, prefix + route.path
                )

            if isinstance(route, Route) and (
                terminal.get("route") is route
                or terminal.get("endpoint") is route.endpoint
            ):
                return prefix + route.path

            return "<unmatched>"

        if match is Match.PARTIAL and partial is None:
            partial = route

    if isinstance(partial, Route) and (
        terminal.get("route") is partial or terminal.get("endpoint") is partial.endpoint
    ):
        return prefix + partial.path

    return "<unmatched>"


class RequestObservation:
    def __init__(self, scope: Scope, routes: Sequence[BaseRoute]) -> None:
        self.scope = scope
        self.incoming: Scope = dict(scope)
        self.routes = routes
        self.started_at = time.perf_counter()
        self.status: int | None = None
        self.result: RequestOutcome | None = None
        self.callbacks: dict[str, Callable[[RequestOutcome], None]] = {}
        self.subscribers: set[str] = set()

    def subscribe(self, key: str, callback: Callable[[RequestOutcome], None]) -> None:
        if key in self.subscribers:
            return

        self.subscribers.add(key)
        if self.result is not None:
            callback(self.result)
        else:
            self.callbacks[key] = callback

    def settle(self, outcome: Literal["completed", "aborted"]) -> None:
        if self.result is not None:
            return

        elapsed = (time.perf_counter() - self.started_at) * 1000
        method = self.incoming["method"]
        self.result = RequestOutcome(
            outcome=outcome,
            method=method if method in _METHODS else "<other>",
            route=route_template(self.routes, self.incoming, self.scope),
            duration_ms=elapsed,
            headers_sent=self.status is not None,
            status=self.status,
        )
        callbacks = tuple(self.callbacks.values())

        self.callbacks.clear()
        for callback in callbacks:
            callback(self.result)


def abort_request(scope: Scope) -> None:
    observation = scope.get(_KEY)

    if isinstance(observation, RequestObservation):
        observation.settle("aborted")


class RequestOutcomeASGIMiddleware:
    """Wrap the complete stack, including Starlette's final 500 response."""

    def __init__(self, app: ASGIApp, routes: Sequence[BaseRoute] = ()) -> None:
        self.app = app
        self.routes = routes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or isinstance(scope.get(_KEY), RequestObservation):
            await self.app(scope, receive, send)

            return

        observation = RequestObservation(scope, self.routes)
        scope[_KEY] = observation

        async def receive_observed() -> Message:
            try:
                message = await receive()
            except TimeoutError:
                raise
            except OSError:
                observation.settle("aborted")

                raise

            if message["type"] == "http.disconnect":
                observation.settle("aborted")

            return message

        async def send_observed(message: Message) -> None:
            try:
                await send(message)
            except TimeoutError:
                raise
            except OSError:
                observation.settle("aborted")

                raise

            if message["type"] == "http.response.start":
                observation.status = message["status"]
            elif message["type"] == "http.response.body" and not message.get(
                "more_body", False
            ):
                observation.settle("completed")

        try:
            await self.app(scope, receive_observed, send_observed)
        finally:
            observation.settle("aborted")


async def observe_request(
    app: ASGIApp,
    scope: Scope,
    receive: Receive,
    send: Send,
    key: str,
    callback: Callable[[RequestOutcome], None],
) -> None:
    """Subscribe inside the stack; support standalone middleware as well."""
    if scope["type"] != "http":
        await app(scope, receive, send)

        return

    observation = scope.get(_KEY)

    if isinstance(observation, RequestObservation):
        observation.subscribe(key, callback)
        await app(scope, receive, send)

        return

    async def subscribed(inner: Scope, receive: Receive, send: Send) -> None:
        await observe_request(app, inner, receive, send, key, callback)

    await RequestOutcomeASGIMiddleware(subscribed)(scope, receive, send)
