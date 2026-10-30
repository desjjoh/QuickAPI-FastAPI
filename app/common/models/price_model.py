"""Shared exact price contract for item inputs, outputs and filters."""

import re
from decimal import Context, Decimal, localcontext
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer, WithJsonSchema
from pydantic_core import PydanticCustomError

MIN_PRICE = Decimal('0.01')
MAX_PRICE = Decimal('99999999.99')
PRICE_PATTERN = r'^[0-9]+(?:\.[0-9]{1,2})?$'


def validate_price(value: object) -> Decimal:
    if isinstance(value, str):
        if re.fullmatch(PRICE_PATTERN, value) is None:
            raise PydanticCustomError(
                'price_format',
                'Price must be an unsigned plain decimal string with at most two decimal places',
            )

        price = Decimal(value)
    elif not isinstance(value, bool) and isinstance(value, (int, float, Decimal)):
        price = Decimal(str(value))
    else:
        raise PydanticCustomError(
            'price_type', 'Price must be a number or unsigned plain decimal string'
        )

    if not price.is_finite() or not MIN_PRICE <= price <= MAX_PRICE:
        raise PydanticCustomError(
            'price_range', 'Price must be between 0.01 and 99999999.99'
        )

    # A fixed context makes validation independent of another library's decimal
    # context. Equality rejects rounding; accepted values normalize to cents.
    with localcontext(Context(prec=10)):
        cents = price.quantize(MIN_PRICE)

    if price != cents:
        raise PydanticCustomError(
            'price_precision', 'Price must have at most two decimal places'
        )

    return cents


Price = Annotated[
    Decimal,
    BeforeValidator(validate_price),
    PlainSerializer(float, return_type=float, when_used='json'),
    WithJsonSchema(
        {
            'anyOf': [
                {
                    'type': 'number',
                    'minimum': 0.01,
                    'maximum': 99999999.99,
                    'multipleOf': 0.01,
                },
                {'type': 'string', 'pattern': PRICE_PATTERN},
            ]
        },
        mode='validation',
    ),
    WithJsonSchema(
        {'type': 'number', 'minimum': 0.01, 'maximum': 99999999.99, 'multipleOf': 0.01},
        mode='serialization',
    ),
]
