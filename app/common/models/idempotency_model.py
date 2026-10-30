"""Domain-independent declarations and normalization for durable JSON mutations."""

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException, Request
from pydantic import BaseModel, SecretBytes, SecretStr

IDEMPOTENCY_MARKER = '__quickapi_idempotency__'
# A compatibility label, not a new hash prefix: existing persisted hashes stay valid.
FINGERPRINT_FORMAT = 'quickapi-json-v1'
RETENTION_SECONDS = 86400
CLEANUP_INTERVAL_SECONDS = 3600
KEY_ERROR = 'Idempotency-Key must be one opaque 1\u2013128 character printable ASCII value without whitespace or commas.'


@dataclass(frozen=True)
class IdempotencyPolicy:
    operation: str
    route: str
    caller_scope: str | Callable[[Request], str]

    def __post_init__(self) -> None:
        if not 1 <= len(self.operation) <= 128 or not 1 <= len(self.route) <= 512:
            raise ValueError(
                'Idempotency requires a bounded operation and stable public route template.'
            )

        if (
            isinstance(self.caller_scope, str)
            and not 1 <= len(self.caller_scope) <= 128
        ):
            raise ValueError(
                'Idempotency caller scope must contain 1\u2013128 characters.'
            )


def idempotent[Endpoint: Callable[..., Any]](
    *,
    operation: str,
    route: str,
    caller_scope: str | Callable[[Request], str],
) -> Callable[[Endpoint], Endpoint]:
    policy = IdempotencyPolicy(operation, route, caller_scope)

    def declare(endpoint: Endpoint) -> Endpoint:
        setattr(endpoint, IDEMPOTENCY_MARKER, policy)

        return endpoint

    return declare


def read_key(request: Request) -> str | None:
    values = request.headers.getlist('idempotency-key')

    if not values:
        return None

    if (
        len(values) != 1
        or re.fullmatch(r'[\x21-\x2b\x2d-\x7e]{1,128}', values[0]) is None
    ):
        raise HTTPException(400, KEY_ERROR)

    return values[0]


def normalized(value: Any) -> Any:
    if isinstance(value, BaseModel):
        # Omitted optional fields stay distinct from explicit null (notably PATCH).
        # Non-null defaults normalize identically to explicitly supplied values.
        # Fingerprint validated values, never a response serializer's masked or
        # excluded representation. Computed properties are not request inputs.
        result = {
            field.alias or name: normalized(getattr(value, name))
            for name, field in type(value).model_fields.items()
            if name in value.model_fields_set or getattr(value, name) is not None
        }

        result.update(normalized(value.model_extra or {}))

        return result

    if isinstance(value, (SecretStr, SecretBytes)):
        return normalized(value.get_secret_value())

    if isinstance(value, Enum):
        return normalized(value.value)

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, bytes):
        return value.decode('utf-8')

    if isinstance(value, Mapping):
        return {
            key: normalized(item)
            for key, item in cast(Mapping[str, Any], value).items()
        }

    if isinstance(value, (list, tuple)):
        return [normalized(item) for item in cast(list[Any] | tuple[Any, ...], value)]

    return value


def _encode(value: Any) -> str:
    if not isinstance(value, bool) and isinstance(value, (int, float, Decimal)):
        number = value if isinstance(value, Decimal) else Decimal(str(value))

        if not number.is_finite():
            raise ValueError('Fingerprint numbers must be finite.')

        if number.is_zero():
            return '0'

        parts = number.as_tuple()
        exponent = parts.exponent

        if not isinstance(exponent, int):
            raise ValueError('Fingerprint numbers must be finite.')

        coefficient = ''.join(str(digit) for digit in parts.digits)
        significant = coefficient.rstrip('0')
        exponent += len(coefficient) - len(significant)

        # Exact digits avoid float rounding and exponent expansion for Decimal.
        return (
            ('-' if parts.sign else '')
            + significant
            + (f'e{exponent}' if exponent else '')
        )

    if isinstance(value, dict):
        mapping = cast(dict[str, Any], value)

        if any(not isinstance(key, str) for key in cast(dict[object, Any], mapping)):
            raise TypeError('Fingerprint object keys must be strings.')

        return (
            '{'
            + ','.join(
                json.dumps(key, ensure_ascii=False) + ':' + _encode(mapping[key])
                for key in sorted(mapping)
            )
            + '}'
        )

    if isinstance(value, list):
        return '[' + ','.join(_encode(item) for item in cast(list[Any], value)) + ']'

    return json.dumps(value, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value: object) -> str:
    """Hash the frozen quickapi-json-v1 encoding; see its reference vectors."""
    encoded = _encode(normalized(value))

    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()
