import os

from fastapi.testclient import TestClient


def test_healthz_shape_is_composite() -> None:
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")
    os.environ.setdefault("ADMIN_USER", "admin")
    os.environ.setdefault("ADMIN_PASSWORD", "secret")
    os.environ.setdefault("NEO4J_PASSWORD", "jainkb_password")

    from services.core_service.main import app

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "neo4j" in data
    assert "postgres" in data
    assert "graph_node_count" in data
