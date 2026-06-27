from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok_status_and_service_name() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "queryops-backend"}


def test_health_allows_local_frontend_origin() -> None:
    client = TestClient(app)

    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
