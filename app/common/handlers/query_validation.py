"""Validate raw query parameters before model extraction loses duplicates."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError


async def reject_repeated_query_parameters(request: Request) -> None:
    errors: list[dict[str, object]] = []

    for name in request.query_params:
        values = request.query_params.getlist(name)

        if len(values) > 1:
            errors.append(
                {
                    'type': 'value_error',
                    'loc': ('query', name),
                    'msg': 'Query parameter must appear only once',
                    'input': values,
                }
            )

    if errors:
        raise RequestValidationError(errors)
