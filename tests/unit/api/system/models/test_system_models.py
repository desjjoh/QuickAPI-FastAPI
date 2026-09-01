from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.api.system.models.live_model import HealthResponse
from app.api.system.models.ready_model import ReadyCheck, ReadyResponse
from app.api.system.models.root_model import RootResponse

pytestmark = pytest.mark.unit


def valid_health_data() -> dict[str, object]:
    return {
        "alive": True,
        "status": "alive",
        "uptime": 1.25,
        "timestamp": datetime.now(UTC),
    }


def test_root_response_retains_message_and_rejects_extra_fields() -> None:
    response = RootResponse(message="Hello World! Welcome to FastAPI!")

    assert response.message == "Hello World! Welcome to FastAPI!"
    with pytest.raises(ValidationError):
        RootResponse.model_validate(
            {"message": "Hello World! Welcome to FastAPI!", "extra": True}
        )


@pytest.mark.parametrize(
    "timestamp",
    ["not-a-timestamp", datetime.now()],
)
def test_health_response_rejects_malformed_or_naive_timestamps(
    timestamp: object,
) -> None:
    data = valid_health_data()
    data["timestamp"] = timestamp

    with pytest.raises(ValidationError):
        HealthResponse.model_validate(data)


def test_health_response_rejects_non_utc_timestamp() -> None:
    data = valid_health_data()
    data["timestamp"] = datetime.now(timezone(timedelta(hours=1)))

    with pytest.raises(ValidationError):
        HealthResponse.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [("uptime", -0.1), ("status", "starting"), ("extra", True)],
)
def test_health_response_rejects_invalid_fields(field: str, value: object) -> None:
    data = valid_health_data()
    data[field] = value

    with pytest.raises(ValidationError):
        HealthResponse.model_validate(data)


@pytest.mark.parametrize(
    ("alive", "status"),
    [(True, "dead"), (False, "alive")],
)
def test_health_response_rejects_contradictory_state(
    alive: bool,
    status: str,
) -> None:
    data = valid_health_data()
    data.update(alive=alive, status=status)

    with pytest.raises(ValidationError):
        HealthResponse.model_validate(data)


@pytest.mark.parametrize(
    ("alive", "status"),
    [(True, "alive"), (False, "dead")],
)
def test_health_response_factory_derives_status(alive: bool, status: str) -> None:
    response = HealthResponse.from_alive(
        alive=alive,
        uptime=0.0,
        timestamp=datetime.now(UTC),
    )

    assert response.status == status


@pytest.mark.parametrize(
    "data",
    [
        {
            "ready": True,
            "status": "ready",
            "timestamp": datetime.now(),
            "checks": [],
        },
        {
            "ready": True,
            "status": "not_ready",
            "timestamp": datetime.now(UTC),
            "checks": [],
        },
        {
            "ready": True,
            "status": "ready",
            "timestamp": datetime.now(UTC),
            "checks": [
                ReadyCheck(name="database", status="down", response_time_ms=0.0)
            ],
        },
    ],
)
def test_ready_response_rejects_invalid_contracts(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ReadyResponse.model_validate(data)
