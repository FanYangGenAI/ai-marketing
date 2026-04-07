"""Integration tests: cold-start HTTP routes (FastAPI TestClient)."""

import json
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture
def campaigns_root(tmp_path):
    root = tmp_path / "campaigns"
    root.mkdir()
    return root


@pytest.fixture
def client(campaigns_root, monkeypatch):
    monkeypatch.setattr("server.routers.campaigns.CAMPAIGNS_ROOT", campaigns_root)
    from server.main import app

    return TestClient(app)


def _png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (4, 4), color=(255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def test_get_assets_empty(client, campaigns_root):
    pdir = campaigns_root / "EmptyP"
    (pdir / "asset_library").mkdir(parents=True)
    r = client.get("/api/products/EmptyP/assets")
    assert r.status_code == 200
    data = r.json()
    assert data["assets"] == []


def test_cold_start_upload_and_patch_delete(client, campaigns_root):
    # Create product layout
    pdir = campaigns_root / "P1"
    for sub in [
        "config",
        "docs",
        "memory",
        "asset_library",
        "attachments",
        "attachments/raw",
        "daily",
    ]:
        (pdir / sub).mkdir(parents=True)
    (pdir / "config" / "product_config.json").write_text(
        json.dumps({"platform": "xiaohongshu", "user_brief": ""}),
        encoding="utf-8",
    )

    r = client.post(
        "/api/products/P1/cold-start/images",
        data={"tag": "brand"},
        files=[("files", ("a.png", _png_bytes(), "image/png"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    aid = body["items"][0]["asset_id"]

    assets = client.get("/api/products/P1/assets").json()
    assert len(assets["assets"]) == 1

    pr = client.patch(f"/api/products/P1/assets/{aid}", json={"note": "logo main"})
    assert pr.status_code == 200
    assert pr.json()["asset"]["note"] == "logo main"

    dr = client.delete(f"/api/products/P1/assets/{aid}")
    assert dr.status_code == 200

    assets2 = client.get("/api/products/P1/assets").json()
    assert assets2["assets"][0]["disabled"] is True


def test_get_package_normalizes_paths_and_allows_null_path(client, campaigns_root):
    """post_package.json may list images with path=null; API must not 500."""
    pdir = campaigns_root / "PX"
    creator = pdir / "daily" / "2026-01-01" / "creator"
    creator.mkdir(parents=True)
    pkg = {
        "platform": "xiaohongshu",
        "title": "t",
        "body": "b",
        "images": [
            {"order": 1, "path": r"a\b\c.png", "caption": ""},
            {"order": 2, "path": None, "caption": "pending"},
        ],
    }
    (creator / "post_package.json").write_text(json.dumps(pkg), encoding="utf-8")

    r = client.get("/api/products/PX/2026-01-01/package")
    assert r.status_code == 200
    data = r.json()
    assert data["images"][0]["path"] == "a/b/c.png"
    assert data["images"][1]["path"] is None
