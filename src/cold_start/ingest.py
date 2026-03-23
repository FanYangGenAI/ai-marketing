"""Save uploaded images to attachments + manifest + Asset Library."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from src.cold_start.manifest import (
    AttachmentManifest,
    ManifestItem,
    load_manifest,
    new_item_id,
    save_manifest,
)
from src.cold_start.paths import attachments_raw_dir, ensure_attachment_dirs
from src.orchestrator.asset_library import AssetLibrary

ALLOWED_IMAGE_SUFFIX = {".png", ".jpg", ".jpeg", ".webp"}
VALID_USER_TAGS = frozenset({"brand", "product_ui", "marketing_ref"})


def _safe_segment(name: str) -> str:
    base = Path(name).name
    if not base:
        return "image.dat"
    cleaned = re.sub(r"[^\w.\-]", "_", base)
    return cleaned[:120] if cleaned else "image.dat"


def _image_size_label(path: Path) -> str:
    try:
        with Image.open(path) as im:
            w, h = im.size
            return f"{w}x{h}"
    except Exception:
        return ""


def ingest_image_files(
    campaign_root: Path,
    file_paths: list[Path],
    default_tag: str = "product_ui",
) -> list[dict]:
    """
    Copy each file into attachments/raw/, append manifest, register AssetLibrary.

    Returns list of {item_id, asset_id, path} for API response.
    """
    campaign_root = campaign_root.resolve()
    if default_tag not in VALID_USER_TAGS:
        default_tag = "product_ui"

    ensure_attachment_dirs(campaign_root)
    raw_dir = attachments_raw_dir(campaign_root)
    manifest = load_manifest(campaign_root)
    lib = AssetLibrary(str(campaign_root / "asset_library"))

    out: list[dict] = []
    for src in file_paths:
        src = src.resolve()
        if not src.is_file():
            continue
        suf = src.suffix.lower()
        if suf not in ALLOWED_IMAGE_SUFFIX:
            continue

        item_id = new_item_id()
        dest_name = f"{item_id}_{_safe_segment(src.name)}"
        dest = raw_dir / dest_name
        dest.write_bytes(src.read_bytes())

        rel = dest.relative_to(campaign_root).as_posix()
        tags = [default_tag]
        record = lib.add(
            str(dest),
            source="user_upload",
            prompt=f"user_upload:{dest_name}",
            tags=tags,
            size=_image_size_label(dest),
        )

        item = ManifestItem(
            id=item_id,
            path=rel,
            kind="image",
            user_tags=tags,
            note="",
            asset_library_id=record.id,
            removed=False,
            created_at=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        )
        manifest.items.append(item)
        out.append({"item_id": item_id, "asset_id": record.id, "path": rel})

    save_manifest(campaign_root, manifest)
    return out
