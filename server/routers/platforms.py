"""Read-only platform rules for frontend and tooling."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.orchestrator.platform_rules import get_hard_rules_dict, load_platform_config

router = APIRouter()


@router.get("/api/platforms/{platform}/rules")
async def get_platform_rules(platform: str):
    """Return hard_rules + guidelines + specs for read-only UI."""
    try:
        cfg = load_platform_config(platform)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {platform}")

    guidelines = dict(cfg.get("guidelines", {}))
    guidelines["specs"] = cfg.get("specs", {})
    guidelines["style_guide"] = cfg.get("style_guide", {})
    guidelines["publish_time"] = cfg.get("publish_time", {})

    return {
        "platform": cfg.get("platform", platform),
        "display_name": cfg.get("display_name", platform),
        "content_type": cfg.get("content_type", ""),
        "rules_version": cfg.get("rules_version", "1.0"),
        "updated_at": cfg.get("updated_at", ""),
        "hard_rules": get_hard_rules_dict(cfg),
        "guidelines": guidelines,
    }
