import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.integration
def test_health() -> None:
    """健康检查返回稳定结构，可供平台识别。"""

    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
