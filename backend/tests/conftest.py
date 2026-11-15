"""Pytest configuration and shared fixtures for StegaGuard tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Fixture providing a FastAPI TestClient for integration and endpoint tests."""
    return TestClient(app)
