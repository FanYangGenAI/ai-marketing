"""Cold-start manifest + ingest (no HTTP)."""

import json
from pathlib import Path

from PIL import Image

from src.cold_start.ingest import ingest_image_files
from src.cold_start.manifest import load_manifest, save_manifest, AttachmentManifest, ManifestItem
from src.cold_start.paths import manifest_path
from src.cold_start.retrieval import load_product_context_for_agents
from src.cold_start.understanding import _persist_profile, _repo_root_from_campaign


def test_repo_root_from_campaign(tmp_path):
    camp = tmp_path / "campaigns" / "X"
    camp.mkdir(parents=True)
    assert _repo_root_from_campaign(camp) == tmp_path


def test_manifest_roundtrip(tmp_path):
    camp = tmp_path / "campaigns" / "P"
    camp.mkdir(parents=True)
    m = AttachmentManifest(
        items=[
            ManifestItem(
                id="att_1",
                path="attachments/raw/a.png",
                kind="image",
                user_tags=["brand"],
                asset_library_id="asset_abcd",
            )
        ]
    )
    save_manifest(camp, m)
    assert manifest_path(camp).exists()
    m2 = load_manifest(camp)
    assert len(m2.items) == 1
    assert m2.items[0].id == "att_1"


def test_ingest_registers_asset_and_manifest(tmp_path):
    camp = tmp_path / "campaigns" / "Prod"
    for sub in ["config", "asset_library", "attachments/raw"]:
        (camp / sub).mkdir(parents=True, exist_ok=True)
    (camp / "config" / "product_config.json").write_text("{}", encoding="utf-8")

    img = tmp_path / "in.png"
    Image.new("RGB", (10, 20), color=(1, 2, 3)).save(img)

    out = ingest_image_files(camp, [img], default_tag="brand")
    assert len(out) == 1
    assert out[0]["asset_id"].startswith("asset_")

    man = load_manifest(camp)
    assert len(man.items) == 1
    assert (camp / man.items[0].path).is_file()


def test_retrieval_includes_profile(tmp_path):
    camp = tmp_path / "campaigns" / "P"
    (camp / "config").mkdir(parents=True)
    (camp / "asset_library").mkdir(parents=True)
    prof = {
        "summary": "S1",
        "positioning": "P1",
        "audience": "A1",
        "key_selling_points": ["k"],
        "creative_constraints": [],
        "pending_conflicts": [],
    }
    _persist_profile(camp, prof)

    text = load_product_context_for_agents(camp)
    assert "S1" in text
    assert "P1" in text
