"""Smoke tests for application health endpoints."""

from fastapi.testclient import TestClient


def test_health_check_returns_200(client: TestClient) -> None:
    """Verify that /api/health responds with 200 and expected status schema."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert isinstance(data["models_loaded"], list)


def test_root_health_endpoint_alias(client: TestClient) -> None:
    """Verify that root /health alias also responds with 200."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
