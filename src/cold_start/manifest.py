"""Attachment manifest: tracks user-uploaded images linked to Asset Library."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.cold_start.paths import ensure_attachment_dirs, manifest_path


@dataclass
class ManifestItem:
    id: str
    path: str  # relative to campaign root, posix
    kind: str  # "image"
    user_tags: list[str] = field(default_factory=list)
    note: str = ""
    asset_library_id: str = ""
    removed: bool = False
    created_at: str = ""


@dataclass
class AttachmentManifest:
    version: str = "1.0"
    items: list[ManifestItem] = field(default_factory=list)


def load_manifest(campaign_root: Path) -> AttachmentManifest:
    p = manifest_path(campaign_root)
    if not p.exists():
        return AttachmentManifest()
    data = json.loads(p.read_text(encoding="utf-8"))
    items = []
    for it in data.get("items", []):
        items.append(
            ManifestItem(
                id=it.get("id", ""),
                path=it.get("path", "").replace("\\", "/"),
                kind=it.get("kind", "image"),
                user_tags=list(it.get("user_tags") or []),
                note=it.get("note", "") or "",
                asset_library_id=it.get("asset_library_id", "") or "",
                removed=bool(it.get("removed", False)),
                created_at=it.get("created_at", "") or "",
            )
        )
    return AttachmentManifest(version=data.get("version", "1.0"), items=items)


def save_manifest(campaign_root: Path, manifest: AttachmentManifest) -> None:
    ensure_attachment_dirs(campaign_root)
    p = manifest_path(campaign_root)
    payload = {"version": manifest.version, "items": [asdict(i) for i in manifest.items]}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def new_item_id() -> str:
    return f"att_{uuid.uuid4().hex[:12]}"


def update_item_note(manifest: AttachmentManifest, item_id: str, note: str) -> ManifestItem | None:
    for it in manifest.items:
        if it.id == item_id and not it.removed:
            it.note = note
            return it
    return None


def mark_item_removed(manifest: AttachmentManifest, item_id: str) -> ManifestItem | None:
    for it in manifest.items:
        if it.id == item_id:
            it.removed = True
            return it
    return None


def active_items(manifest: AttachmentManifest) -> list[ManifestItem]:
    return [i for i in manifest.items if not i.removed]


def item_by_asset_id(manifest: AttachmentManifest, asset_library_id: str) -> ManifestItem | None:
    for it in manifest.items:
        if it.asset_library_id == asset_library_id and not it.removed:
            return it
    return None
