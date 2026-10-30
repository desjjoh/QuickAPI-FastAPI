"""Opt-in transaction ownership around FastAPI's normal response preparation."""

import re
from collections.abc import Callable, Coroutine
from contextlib import AsyncExitStack
from inspect import iscoroutinefunction
from typing import Any

from fastapi import Request, Response
from fastapi.datastructures import DefaultPlaceholder
from fastapi.dependencies.models import Dependant
from fastapi.params import Body, Form
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import event
from starlette.concurrency import run_in_threadpool

from app.common.handlers.request_activity import request_activity
from app.common.models.error_model import ErrorResponse
from app.common.models.idempotency_model import (
    IDEMPOTENCY_MARKER,
    IdempotencyPolicy,
    read_key,
)
from app.common.services.idempotency_service import execution_context, pinned_execution
from app.config import database

TRANSACTION_SESSION_KEY = database.TRANSACTION_SESSION_KEY
_MARKER = '__quickapi_transactional__'


def _validate_idempotent_inputs(dependant: Dependant, path: str) -> None:
    if (
        dependant.request_param_name
        or dependant.http_connection_param_name
        or dependant.header_params
        or dependant.cookie_params
    ):
        raise RuntimeError(
            'Idempotent endpoints must declare business inputs as body/path/query parameters, not raw requests, headers or cookies. Use dependencies for authorization and services.'
        )

    aliases = {field.alias for field in dependant.path_params}

    if set(re.findall(r'{([^}]+)}', path)) - aliases:
        raise RuntimeError(
            'Every idempotent route path parameter must be declared on its endpoint.'
        )

    for fields in (
        dependant.body_params,
        dependant.path_params,
        dependant.query_params,
    ):
        if len({field.alias for field in fields}) != len(fields):
            raise RuntimeError(
                'Idempotent input parameter aliases must be unique within each input category.'
            )

    for field in dependant.body_params:
        info = field.field_info

        if (
            isinstance(info, Form)
            or not isinstance(info, Body)
            or not (
                info.media_type == 'application/json'
                or info.media_type.endswith('+json')
            )
        ):
            raise RuntimeError('Idempotent routes support declared JSON bodies only.')

    pending = list(dependant.dependencies)

    while pending:
        dependency = pending.pop()

        if dependency.body_params or dependency.path_params or dependency.query_params:
            raise RuntimeError(
                'Idempotent body/path/query inputs must be declared directly on the endpoint; dependencies may provide authorization and services, not hidden mutation inputs.'
            )

        pending.extend(dependency.dependencies)


def transactional[Endpoint: Callable[..., Any]](endpoint: Endpoint) -> Endpoint:
    """Mark an ApplicationRoute endpoint without replacing its signature."""
    setattr(endpoint, _MARKER, True)

    return endpoint


class ApplicationRoute(APIRoute):
    openapi_extra: dict[str, Any] | None

    def __init__(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        # Preserve prepared JSONResponse semantics across FastAPI's model-byte
        # fast path, including render validation inside the owned transaction.
        response_class = kwargs.setdefault('response_class', JSONResponse)

        if isinstance(response_class, DefaultPlaceholder):
            kwargs['response_class'] = response_class.value

        if getattr(endpoint, IDEMPOTENCY_MARKER, None) is not None:
            kwargs['responses'] = {
                400: {
                    'description': 'Invalid or duplicate Idempotency-Key header.',
                    'model': ErrorResponse,
                },
                409: {
                    'description': 'Idempotency-Key input conflict or matching request already processing.',
                    'model': ErrorResponse,
                },
                **(kwargs.get('responses') or {}),
            }

        super().__init__(path, endpoint, **kwargs)

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        policy = getattr(self.endpoint, IDEMPOTENCY_MARKER, None)

        if policy is not None:
            if not isinstance(policy, IdempotencyPolicy) or not getattr(
                self.endpoint, _MARKER, False
            ):
                raise RuntimeError('Idempotency requires a transactional JSON route.')

            _validate_idempotent_inputs(self.dependant, self.path_format)

            original = self.endpoint

            if original is None:
                raise RuntimeError('Idempotent route requires an endpoint.')

            body_fields = self.dependant.body_params
            path_fields = self.dependant.path_params
            query_fields = self.dependant.query_params

            async def validated_endpoint(**values: Any) -> Any:
                execution = execution_context.get()

                if execution is not None:
                    body = (
                        values[body_fields[0].name]
                        if len(body_fields) == 1
                        else (
                            {field.alias: values[field.name] for field in body_fields}
                            if body_fields
                            else None
                        )
                    )
                    replay = await execution.begin(
                        {
                            'body': body,
                            'params': (
                                {
                                    field.alias: values[field.name]
                                    for field in path_fields
                                }
                                if path_fields
                                else None
                            ),
                            'query': (
                                {
                                    field.alias: values[field.name]
                                    for field in query_fields
                                }
                                if query_fields
                                else None
                            ),
                        }
                    )

                    if replay is not None:
                        return replay

                if iscoroutinefunction(original):
                    return await original(**values)

                return await run_in_threadpool(original, **values)

            self.dependant.call = validated_endpoint
            extra: dict[str, Any] = dict(self.openapi_extra or {})
            parameters: list[dict[str, Any]] = list(extra.get('parameters', []))

            if not any(
                parameter.get('name', '').lower() == 'idempotency-key'
                for parameter in parameters
            ):
                parameters.append(
                    {
                        'in': 'header',
                        'name': 'Idempotency-Key',
                        'required': False,
                        'description': 'Optional durable mutation retry key. Reuse the original key and validated input, including expected_version.',
                        'schema': {
                            'type': 'string',
                            'minLength': 1,
                            'maxLength': 128,
                            'pattern': r'^[\x21-\x2b\x2d-\x7e]+$',
                        },
                    }
                )

            self.openapi_extra = {**extra, 'parameters': parameters}

        prepare = super().get_route_handler()

        async def handle(request: Request) -> Response:
            if not getattr(self.endpoint, _MARKER, False):
                return await prepare(request)

            if TRANSACTION_SESSION_KEY in request.scope:
                raise RuntimeError('A mutation transaction already owns this request.')

            activity = request_activity(request.scope)

            activity.assert_active()
            activity.owns_mutation = True
            key = read_key(request) if policy is not None else None

            # Explicit begin is required, including for any attempted use after
            # commit. A borrowed session cannot silently start a second transaction.
            async with (
                database.SessionLocal(autobegin=False) as session,
                AsyncExitStack() as resources,
            ):
                if session.in_transaction():
                    raise RuntimeError('A mutation requires a fresh transaction owner.')

                execution = (
                    await resources.enter_async_context(
                        pinned_execution(session, request, policy, key)
                    )
                    if key is not None and policy is not None
                    else None
                )
                token = execution_context.set(execution)

                request.scope[TRANSACTION_SESSION_KEY] = session

                # Session.begin() is logical: actual checkout/connect can happen
                # later. Guard after acquisition and BEGIN, before business SQL.
                def acquired(*_: object) -> None:
                    activity.assert_active()

                event.listen(session.sync_session, 'after_begin', acquired)

                try:
                    async with session.begin():
                        activity.assert_active()
                        response = await prepare(request)

                        if (
                            not isinstance(response, JSONResponse)
                            or response.background is not None
                        ):
                            raise RuntimeError(
                                'Transactional routes require buffered JSON without background tasks.'
                            )

                        if response.status_code >= 400:
                            await session.rollback()
                        else:
                            if execution is not None:
                                await execution.complete(response)

                            await session.flush()
                            # Check the clock, not just the timer callback: work
                            # may have delayed the loop or caught cancellation.
                            activity.assert_active()

                    return response
                finally:
                    execution_context.reset(token)
                    event.remove(session.sync_session, 'after_begin', acquired)
                    request.scope.pop(TRANSACTION_SESSION_KEY, None)

        return handle
