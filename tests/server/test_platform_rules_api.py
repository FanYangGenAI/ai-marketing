"""Integration test: GET /api/platforms/{platform}/rules"""

from fastapi.testclient import TestClient


def test_get_xiaohongshu_rules():
    from server.main import app

    client = TestClient(app)
    r = client.get("/api/platforms/xiaohongshu/rules")
    assert r.status_code == 200
    data = r.json()
    assert data["platform"] == "xiaohongshu"
    assert "hard_rules" in data
    assert data["hard_rules"]["title"]["max_chars"] == 20
    assert data["hard_rules"]["body"]["max_chars"] == 1000
    assert "guidelines" in data


def test_unknown_platform_404():
    from server.main import app

    client = TestClient(app)
    r = client.get("/api/platforms/does-not-exist/rules")
    assert r.status_code == 404
