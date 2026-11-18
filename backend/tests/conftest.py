"""Pytest fixtures and test setup for ArchSchool backend test suite.

Ensures zero dependency on PostgreSQL during test runs by directing
database operations to an isolated SQLite file and disabling external
network services (such as Expo push notifications).
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Generator

import pytest

# ----------------------------------------------------------------------
# 1. CRITICAL: Set environment overrides BEFORE importing any app modules
# ----------------------------------------------------------------------
_TEST_TEMP_DIR = Path(tempfile.mkdtemp(prefix="archschool_test_"))
_TEST_DB_FILE = _TEST_TEMP_DIR / "test_temp.db"
_TEST_UPDATES_DIR = _TEST_TEMP_DIR / "updates"

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_FILE.as_posix()}"
os.environ["PUSH_NOTIFICATIONS_ENABLED"] = "false"
os.environ["UPDATES_DIR"] = _TEST_UPDATES_DIR.as_posix()
os.environ["KEEP_BUNDLES_COUNT"] = "3"
os.environ["MIN_APK_VERSION"] = "1.0.0"

# Add backend root to sys.path so 'app' is resolvable
import sys
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

# Now safely import application modules
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.main import app
from app import models


@pytest.fixture(scope="session", autouse=True)
def initialize_test_database():
    """Ensure database schema is created on the SQLite test file, and dispose cleanly."""
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    if _TEST_TEMP_DIR.exists():
        shutil.rmtree(_TEST_TEMP_DIR, ignore_errors=True)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide a transactional database session per test, rolled back afterward."""
    session: Session = SessionLocal()
    try:
        # Clear updates table between tests to ensure test isolation
        if hasattr(models, "AppUpdate"):
            session.query(models.AppUpdate).delete()
            session.commit()
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Provide a TestClient instance with get_db dependency overridden to the test session."""
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def test_updates_dir(monkeypatch, tmp_path) -> Path:
    """Create a completely isolated updates storage directory tree for file streaming tests."""
    updates_path = tmp_path / "updates"
    bundles_path = updates_path / "bundles"
    apk_path = updates_path / "apk"
    meta_path = updates_path / "meta"

    bundles_path.mkdir(parents=True, exist_ok=True)
    apk_path.mkdir(parents=True, exist_ok=True)
    meta_path.mkdir(parents=True, exist_ok=True)

    # Monkeypatch settings so the update router resolves paths from here
    monkeypatch.setattr(settings, "UPDATES_DIR", str(updates_path))
    return updates_path
