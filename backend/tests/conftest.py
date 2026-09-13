"""
Shared test fixtures for Assay backend tests.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

# This suite covers the deprecated database API. The production default deliberately
# excludes it, so compatibility tests opt in before importing the application.
os.environ.setdefault("ASSAY_ENABLE_LEGACY_API", "1")

from backend.main import app  # noqa: E402
from backend.database import get_session


@pytest.fixture(name="session")
def session_fixture():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    """Create a test client with the in-memory database."""

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
