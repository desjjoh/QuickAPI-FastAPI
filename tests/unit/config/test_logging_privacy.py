import io
import json
import logging
import re
import sys

import pytest
import structlog

from app.common.helpers.error_diagnostics import error_diagnostics
from app.config import logging as config

pytestmark = pytest.mark.unit
SECRET = "private-value-never-log"


@pytest.mark.parametrize("production", [False, True])
def test_private_payloads_and_raw_exception_details_are_excluded(
    production: bool,
) -> None:
    stream = io.StringIO()
    logger = config.create_logger(production=production, level="DEBUG", stream=stream)

    try:
        raise ValueError(SECRET)
    except ValueError as error:
        logger.error(
            "HTTP request failed.",
            error=error,
            err=error,
            reason=error,
            body={"value": SECRET},
            headers={"authorization": SECRET},
            sql=SECRET,
            password=SECRET,
            extra={"token": SECRET},
        )

    output = stream.getvalue()

    assert SECRET not in output
    assert "Traceback" not in output
    assert len(output.splitlines()) == 1
    if production:
        data = json.loads(output)

        assert data["error"]["errorType"] == "ValueError"
        assert re.fullmatch(r"[0-9a-f]{64}", data["error"]["errorFingerprint"])
        assert data["err"] == data["reason"] == data["error"]
        assert data["time"].endswith("Z")
    else:
        assert "errorFingerprint" not in output and "errorType" not in output
        assert "HTTP request failed." in output


@pytest.mark.parametrize(
    "level,expected", [("DEBUG", 5), ("INFO", 4), ("WARN", 3), ("ERROR", 2)]
)
def test_native_levels_filter_output(level: str, expected: int) -> None:
    stream = io.StringIO()
    logger = config.create_logger(production=True, level=level, stream=stream)

    for method in ["debug", "info", "warning", "error", "critical"]:
        getattr(logger, method)("Fixed event.")

    assert len(stream.getvalue().splitlines()) == expected


def test_context_isolated_and_no_raw_path() -> None:
    stream = io.StringIO()
    logger = config.create_logger(production=True, level="DEBUG", stream=stream)

    with structlog.contextvars.bound_contextvars(
        request_id="test-request", method="GET", path=SECRET, ip="127.0.0.1"
    ):
        logger.debug(
            "Request completed.",
            route="/items/{id}",
            status=200,
            durationMs=1.5,
            outcome="completed",
            headersSent=True,
        )

    logger.info("Application ready.")
    first, second = map(json.loads, stream.getvalue().splitlines())

    assert first["requestId"] == "test-request"
    assert first["route"] == "/items/{id}" and first["levelLabel"] == "debug"
    assert "requestId" not in second and SECRET not in stream.getvalue()


def test_console_layout_and_control_characters() -> None:
    stream = io.StringIO()
    logger = config.create_logger(production=False, level="DEBUG", stream=stream)

    logger.info("Safe\nInjected\x1b[31m", requestId="id\rspoof")
    output = re.sub(r"\x1b\[[0-9;]*m", "", stream.getvalue())

    assert len(output.splitlines()) == 1
    assert re.match(
        r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} \[\d+\] \[info    \]", output
    )
    assert "\\u000a" in output and "\\u001b" in output


def test_codes_are_allowlisted_and_hostile_errors_cannot_break_logging() -> None:
    assert error_diagnostics(OSError(13, SECRET))["errorCode"] == "EACCES"
    assert "errorCode" not in error_diagnostics(OSError(123456, SECRET))
    assert error_diagnostics({"secret": SECRET}) == {"errorType": "UnknownError"}

    class HostileError(Exception):
        def __getattribute__(self, name: str) -> object:
            raise RuntimeError(SECRET)

    assert error_diagnostics(HostileError()) == {"errorType": "UnknownError"}


def test_dependency_handler_never_formats_messages_arguments_or_tracebacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = io.StringIO()

    monkeypatch.setattr(
        config,
        "log",
        config.create_logger(production=True, level="DEBUG", stream=stream),
    )
    handler = config.SafeDependencyHandler()

    try:
        raise RuntimeError(SECRET)
    except RuntimeError:
        record = logging.LogRecord(
            "uvicorn.error",
            logging.ERROR,
            __file__,
            1,
            SECRET,
            (SECRET,),
            sys.exc_info(),
        )

    handler.emit(record)
    data = json.loads(stream.getvalue())

    assert data["msg"] == "Server event." and SECRET not in stream.getvalue()
    assert data["error"]["errorType"] == "RuntimeError"


def test_nonfinite_metadata_does_not_break_json() -> None:
    stream = io.StringIO()
    logger = config.create_logger(production=True, level="DEBUG", stream=stream)

    logger.info("Safe event.", durationMs=float("nan"))
    assert "durationMs" not in json.loads(stream.getvalue())


@pytest.mark.parametrize("production", [False, True])
def test_ascii_output_fallback_preserves_valid_json(
    monkeypatch: pytest.MonkeyPatch,
    production: bool,
) -> None:
    class AsciiOutput(io.StringIO):
        encoding = "ascii"

        def write(self, text: str) -> int:
            text.encode("ascii")

            return super().write(text)

    output = AsciiOutput()

    monkeypatch.setattr(sys, "stdout", output)
    logger = config.create_logger(production=production, level="INFO")

    logger.info("Application ready.", requestId="\u00e9")
    if production:
        assert json.loads(output.getvalue())["requestId"] == "\u00e9"
    else:
        assert "\\xe9" in output.getvalue() and len(output.getvalue().splitlines()) == 1


def test_non_exception_driver_payload_has_no_diagnostics() -> None:
    failure = RuntimeError(SECRET)
    failure.__dict__["orig"] = {"password": SECRET}

    assert error_diagnostics(failure) == {"errorType": "RuntimeError"}
