import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

# Never use DATABASE_URL or .env for tests: migrations run only in a temporary DB.
_test_dir = TemporaryDirectory(prefix="taskhub-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_test_dir.name) / 'test.db'}"
os.environ["DATABASE_HOST"] = ""
os.environ["CORS_ORIGINS"] = "http://localhost:3000,http://localhost:5173"
os.environ["JWT_SECRET_KEY"] = "test-only-secret-key-never-use-in-production-0123456789"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
# Tests must not send mail or contact a real cache from the developer's .env.
os.environ["EMAIL_ENABLED"] = "false"
os.environ["REDIS_URL"] = ""

from database import Base, engine  # noqa: E402
from main import api, app  # noqa: E402
from models import User, UserRole  # noqa: E402
from routers.dependencies import get_current_user  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    command.check(cfg)
    yield
    engine.dispose()
    _test_dir.cleanup()


@pytest.fixture
def anonymous_client(migrated_database):
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client(anonymous_client):
    # Existing CRUD/query-count tests run as admin to isolate business logic.
    # Auth/permission tests use anonymous_client and exercise real dependencies.
    api.dependency_overrides[get_current_user] = lambda: User(
        id=uuid4(), name="Test actor", username="test_actor", email="actor@example.com",
        is_active=True, role=UserRole.ADMIN,
    )
    try:
        yield anonymous_client
    finally:
        api.dependency_overrides.pop(get_current_user, None)
