"""Allowlisted diagnostics: no exception text, arguments, SQL, or raw traceback."""

import hashlib
from typing import Any

_NAMES = frozenset(
    {
        "Exception",
        "DatabaseUnavailableError",
        "RuntimeError",
        "ValueError",
        "TypeError",
        "KeyError",
        "OSError",
        "PermissionError",
        "FileNotFoundError",
        "ConnectionResetError",
        "BrokenPipeError",
        "HTTPException",
        "ValidationError",
        "DBAPIError",
        "SQLAlchemyError",
        "ConnectionError",
        "ConnectionRefusedError",
        "TimeoutError",
        "CancelledError",
        "IntegrityError",
        "OperationalError",
        "InterfaceError",
        "DataError",
        "ProgrammingError",
        "InvalidRequestError",
    }
)
_CODES = {
    2: "ENOENT",
    13: "EACCES",
    104: "ECONNRESET",
    111: "ECONNREFUSED",
    110: "ETIMEDOUT",
    10061: "ECONNREFUSED",
    1062: "ER_DUP_ENTRY",
    1213: "ER_LOCK_DEADLOCK",
    1205: "ER_LOCK_WAIT_TIMEOUT",
    1406: "ER_DATA_TOO_LONG",
    1048: "ER_BAD_NULL_ERROR",
}


def error_diagnostics(error: object) -> dict[str, Any]:
    try:
        if not isinstance(error, BaseException):
            return {"errorType": "UnknownError"}

        name = type(error).__name__
        result: dict[str, Any] = {
            "errorType": name if name in _NAMES else "UnknownError"
        }
        code = error.__dict__.get("code")

        if code in {
            "DB_POOL_CLOSED",
            "DB_POOL_CAPACITY",
            "DB_POOL_ACQUIRE_TIMEOUT",
            "DB_CONNECT_TIMEOUT",
            "DB_CONNECTION_FAILED",
            "DB_TLS_REQUIRED",
        }:
            result["errorCode"] = code

        original = error.__dict__.get("orig", error)

        if isinstance(original, BaseException):
            args = original.args

            if args and type(args[0]) is int and args[0] in _CODES:
                result["errorCode"] = _CODES[args[0]]

        frames: list[str] = []
        traceback = error.__traceback__

        while traceback is not None and len(frames) < 64:
            code = traceback.tb_frame.f_code

            frames.append(f"{code.co_filename}:{code.co_name}:{traceback.tb_lineno}")
            traceback = traceback.tb_next

        if frames:
            result["errorFingerprint"] = hashlib.sha256(
                "\n".join(frames).encode()
            ).hexdigest()

        return result
    except Exception:
        return {"errorType": "UnknownError"}
