from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


class CORSConfig:
    def __init__(self, origins: list[str]):
        self.origins: list[str] = origins


def apply_cors(app: FastAPI, config: CORSConfig) -> None:
    allowed_methods: list[str] = ["GET", "POST", "PUT", "PATCH", "DELETE"]
    expose_headers: list[str] = []
    allow_headers: list[str] = [
        "content-type",
        "authorization",
        "x-api-key",
        "x-csrf-token",
        "x-request-id",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.origins,
        allow_credentials=True,
        allow_methods=allowed_methods,
        allow_headers=allow_headers,
        expose_headers=expose_headers,
    )
