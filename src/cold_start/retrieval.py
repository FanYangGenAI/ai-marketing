"""Assemble product context from cold-start artifacts for Strategist / Director."""

from __future__ import annotations

import json
from pathlib import Path

from src.cold_start.manifest import active_items, load_manifest
from src.cold_start.paths import product_profile_path
from src.orchestrator.asset_library import AssetLibrary


def load_product_context_for_agents(campaign_root: Path) -> str:
    """
    Human-readable block to append to agent context (Strategist, optional others).

    Includes product_profile.json summary and active user-upload assets (notes + ids).
    """
    parts: list[str] = []

    prof = product_profile_path(campaign_root)
    if prof.exists():
        try:
            data = json.loads(prof.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        summary = (data.get("summary") or "").strip()
        positioning = (data.get("positioning") or "").strip()
        audience = (data.get("audience") or "").strip()
        ksp = data.get("key_selling_points") or []
        constraints = data.get("creative_constraints") or []
        conflicts = data.get("pending_conflicts") or []

        if summary or positioning:
            block = ["## 产品档案（冷启动理解）"]
            if summary:
                block.append(f"摘要：{summary}")
            if positioning:
                block.append(f"定位：{positioning}")
            if audience:
                block.append(f"受众：{audience}")
            if ksp:
                block.append("核心卖点：\n" + "\n".join(f"- {x}" for x in ksp[:12]))
            if constraints:
                block.append("创作约束：\n" + "\n".join(f"- {x}" for x in constraints[:12]))
            if conflicts:
                block.append("待确认冲突：\n" + "\n".join(f"- {x}" for x in conflicts[:8]))
            parts.append("\n".join(block))

    lib = AssetLibrary(str(campaign_root / "asset_library"))
    uploads = [a for a in lib.list_active_assets("image") if a.source == "user_upload"]
    if uploads:
        lines = ["## 用户上传素材（可复用，优先 reuse）"]
        for a in uploads[:30]:
            note = (a.note or "").strip()
            prompt = (a.prompt or "").strip()
            tag_str = ",".join(a.tags) if a.tags else ""
            hint = note or prompt[:120]
            lines.append(
                f"- [{a.id}] tags=[{tag_str}] {hint}"
            )
        parts.append("\n".join(lines))

    manifest = load_manifest(campaign_root)
    extra = [i for i in active_items(manifest) if i.note and i.asset_library_id]
    if extra:
        lines = ["## 附件备注（manifest）"]
        for i in extra[:20]:
            lines.append(f"- {i.asset_library_id}: {i.note}")
        parts.append("\n".join(lines))

    if not parts:
        return ""
    return "\n\n".join(parts)
