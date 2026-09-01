import datetime as dt

import pytest
from pydantic import ValidationError

from app.api.system.models.info_model import InfoResponse

pytestmark = pytest.mark.unit

INVALID_FIELDS: list[tuple[str, object]] = [
    ("version", "1.2"),
    ("environment", "staging"),
    ("pid", 0),
    ("pid", "42"),
    ("started_at", dt.datetime(2026, 1, 1)),
    (
        "started_at",
        dt.datetime(
            2026,
            1,
            1,
            tzinfo=dt.timezone(dt.timedelta(hours=1)),
        ),
    ),
    ("timezone", "Mars/Olympus_Mons"),
]


def valid_payload() -> dict[str, object]:
    return {
        "name": "QuickAPI",
        "version": "1.2.3",
        "environment": "test",
        "hostname": "api-1",
        "pid": 42,
        "python_version": "3.12.1",
        "platform": "Linux",
        "architecture": "x86_64",
        "started_at": dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        "timezone": "Etc/UTC",
    }


def test_info_response_accepts_only_the_complete_strict_shape() -> None:
    payload = valid_payload()
    result = InfoResponse.model_validate(payload)
    assert result.model_dump() == payload

    for key in payload:
        incomplete: dict[str, object] = payload.copy()
        incomplete.pop(key)
        with pytest.raises(ValidationError):
            InfoResponse.model_validate(incomplete)


@pytest.mark.parametrize(
    ("field", "value"),
    INVALID_FIELDS,
)
def test_info_response_rejects_invalid_fields(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        invalid_payload: dict[str, object] = valid_payload()
        invalid_payload[field] = value
        InfoResponse.model_validate(invalid_payload)


def test_info_response_forbids_undeclared_configuration() -> None:
    with pytest.raises(ValidationError):
        InfoResponse.model_validate(valid_payload() | {"DATABASE_URL": "secret"})
