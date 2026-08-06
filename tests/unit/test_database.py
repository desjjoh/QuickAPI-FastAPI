import os
import unittest
from unittest.mock import patch

import pytest

os.environ.setdefault("APP_NAME", "QuickAPI Tests")
os.environ.setdefault("APP_VERSION", "1.0.0")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("PORT", "5000")
os.environ.setdefault(
    "DATABASE_URL", "mysql+asyncmy://quickapi:test@localhost:3306/quickapi_test"
)

from app.config import database

pytestmark = pytest.mark.unit


class CreateEngineTest(unittest.TestCase):
    def test_create_engine_uses_configured_database_url(self) -> None:
        configured_url = (
            "mysql+asyncmy://configured:secret@db.example:3306/configured_db"
        )

        with (
            patch.object(database.settings, "DATABASE_URL", configured_url),
            patch.object(database, "create_async_engine") as create_async_engine,
        ):
            engine = database.create_engine()

        create_async_engine.assert_called_once_with(configured_url, echo=False)
        self.assertIs(engine, create_async_engine.return_value)


if __name__ == "__main__":
    unittest.main()
