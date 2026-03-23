"""单元测试：Asset Library 管理器（无需外部依赖）"""

import pytest
from pathlib import Path
from PIL import Image
from src.orchestrator.asset_library import AssetLibrary, AssetRecord


@pytest.fixture
def library(tmp_path) -> AssetLibrary:
    return AssetLibrary(library_root=str(tmp_path / "asset_library"))


@pytest.fixture
def sample_image(tmp_path) -> str:
    path = str(tmp_path / "img.jpg")
    Image.new("RGB", (100, 100), color=(42, 42, 42)).save(path)
    return path


@pytest.fixture
def another_image(tmp_path) -> str:
    path = str(tmp_path / "img2.jpg")
    Image.new("RGB", (100, 100), color=(99, 99, 99)).save(path)
    return path


def test_add_new_asset(library, sample_image):
    record = library.add(
        file_path=sample_image,
        source="gemini_web",
        prompt="测试图片",
        tags=["product_ui", "blue"],
        size="1080x1440",
    )
    assert record.id.startswith("asset_")
    assert record.hash.startswith("md5:")
    assert record.source == "gemini_web"
    assert "product_ui" in record.tags
    assert Path(library.get_full_path(record)).exists()


def test_dedup_same_file(library, sample_image):
    """相同文件 hash 不应重复入库。"""
    r1 = library.add(sample_image, source="gemini_web", prompt="p1")
    r2 = library.add(sample_image, source="gemini_web", prompt="p2")
    assert r1.id == r2.id
    assert len(library._index.assets) == 1


def test_different_files_both_added(library, sample_image, another_image):
    r1 = library.add(sample_image, source="screenshot", prompt="s1")
    r2 = library.add(another_image, source="screenshot", prompt="s2")
    assert r1.id != r2.id
    assert len(library._index.assets) == 2


def test_find_by_tags(library, sample_image, another_image):
    library.add(sample_image, source="gemini_api", prompt="a", tags=["product_ui", "blue"])
    library.add(another_image, source="gemini_api", prompt="b", tags=["product_ui", "red"])
    results = library.find_by_tags(["product_ui"])
    assert len(results) == 2
    results_blue = library.find_by_tags(["product_ui", "blue"])
    assert len(results_blue) == 1


def test_find_by_hash_miss(library, sample_image):
    """未入库的文件应返回 None。"""
    result = library.find_by_hash(sample_image)
    assert result is None


def test_find_by_hash_hit(library, sample_image):
    library.add(sample_image, source="gemini_web", prompt="test")
    result = library.find_by_hash(sample_image)
    assert result is not None


def test_mark_used(library, sample_image):
    record = library.add(sample_image, source="screenshot", prompt="")
    library.mark_used(record.id, "campaigns/prod/daily/2026-03-17/output/final/post.jpg")
    updated = library.get_by_id(record.id)
    assert updated.reuse_count == 1
    assert len(updated.used_in) == 1


def test_index_persists(tmp_path, sample_image):
    """重新加载 library 后数据应仍然存在。"""
    root = str(tmp_path / "asset_library")
    lib1 = AssetLibrary(library_root=root)
    lib1.add(sample_image, source="gemini_web", prompt="persist test", tags=["test"])

    lib2 = AssetLibrary(library_root=root)
    assert len(lib2._index.assets) == 1
    assert lib2._index.assets[0].tags == ["test"]


def test_note_and_disabled_roundtrip(tmp_path, sample_image):
    root = str(tmp_path / "asset_library")
    lib = AssetLibrary(library_root=root)
    r = lib.add(sample_image, source="user_upload", prompt="u", note="n1", tags=["test"])
    lib.update_note(r.id, "updated")
    assert lib.get_by_id(r.id).note == "updated"
    assert len(lib.list_active_assets()) == 1
    assert len(lib.find_by_tags(["test"])) == 1
    lib.set_disabled(r.id, True)
    assert len(lib.list_active_assets()) == 0
    assert lib.find_by_tags(["test"]) == []


def test_load_legacy_index_without_note_field(tmp_path, sample_image):
    root = tmp_path / "asset_library"
    root.mkdir(parents=True)
    legacy = {
        "version": "1.0",
        "assets": [
            {
                "id": "asset_abc",
                "hash": "md5:deadbeef",
                "type": "image",
                "file": "images/x.jpg",
                "size": "1x1",
                "created_at": "2020-01-01",
                "source": "screenshot",
                "prompt": "p",
                "tags": [],
                "platform": "xiaohongshu",
                "used_in": [],
                "reuse_count": 0,
            }
        ],
    }
    import json
    (root / "index.json").write_text(json.dumps(legacy), encoding="utf-8")
    img_file = root / "images" / "x.jpg"
    img_file.parent.mkdir(parents=True)
    img_file.write_bytes(b"fake")

    lib = AssetLibrary(library_root=str(root))
    a = lib.get_by_id("asset_abc")
    assert a is not None
    assert a.note == ""
    assert a.disabled is False
