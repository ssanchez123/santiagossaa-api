"""Tests for info endpoint."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_info_endpoint() -> None:
    """Info endpoint returns request metadata."""
    response = client.get("/api/v1/info")
    assert response.status_code == 200
    data = response.json()
    assert "method" in data
    assert "url" in data
    assert data["method"] == "GET"


def test_root_endpoint() -> None:
    """Root endpoint returns server info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert "version" in data