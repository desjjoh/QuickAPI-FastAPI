import os

os.environ.setdefault("APP_NAME", "QuickAPI")
os.environ.setdefault("APP_VERSION", "1.0.0")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("PORT", "8000")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
