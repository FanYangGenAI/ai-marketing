"""Run LLM understanding over PRD + uploaded images; write product_profile + product_knowledge."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from src.cold_start.manifest import active_items, load_manifest
from src.cold_start.paths import (
    product_knowledge_path,
    product_profile_path,
    understanding_state_path,
)
from src.llm.gemini_client import GeminiClient


_PROFILE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "2-4 sentences product summary"},
        "positioning": {"type": "string"},
        "audience": {"type": "string"},
        "key_selling_points": {"type": "array", "items": {"type": "string"}},
        "creative_constraints": {"type": "array", "items": {"type": "string"}},
        "terminology": {"type": "array", "items": {"type": "string"}},
        "image_insights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "description": {"type": "string"},
                    "suggested_use": {"type": "string"},
                },
            },
        },
        "pending_conflicts": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "positioning", "audience"],
}


def _write_state(campaign_root: Path, status: str, message: str = "") -> None:
    understanding_state_path(campaign_root).parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = understanding_state_path(campaign_root)
    prev = {}
    if path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    payload = {
        "status": status,
        "message": message,
        "updated_at": now,
    }
    if status == "running":
        payload["started_at"] = now
    elif status in ("done", "error", "skipped"):
        payload["started_at"] = prev.get("started_at", now)
        payload["finished_at"] = now
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _repo_root_from_campaign(campaign_root: Path) -> Path:
    """campaigns/{product} -> repo root (parent of campaigns/)."""
    return campaign_root.resolve().parent.parent


def _read_prd_text(campaign_root: Path) -> str:
    cfg = campaign_root / "config" / "product_config.json"
    if not cfg.exists():
        return ""
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    rel = data.get("prd_path") or ""
    if not rel:
        return ""
    rel_p = Path(rel)
    if rel_p.is_absolute():
        prd = rel_p
    else:
        repo_root = _repo_root_from_campaign(campaign_root)
        prd = (repo_root / rel).resolve()
        if not prd.is_file():
            alt = (campaign_root / rel).resolve()
            prd = alt if alt.is_file() else prd
    if not prd.exists() or not prd.is_file():
        return ""
    try:
        return prd.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_user_brief(campaign_root: Path) -> str:
    cfg = campaign_root / "config" / "product_config.json"
    if not cfg.exists():
        return ""
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    return (data.get("user_brief") or "").strip()


def _collect_image_paths(campaign_root: Path, limit: int = 12) -> list[Path]:
    manifest = load_manifest(campaign_root)
    paths: list[Path] = []
    for item in active_items(manifest):
        if item.kind != "image":
            continue
        p = (campaign_root / item.path).resolve()
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            paths.append(p)
        if len(paths) >= limit:
            break
    return paths


async def run_cold_start_understanding(campaign_root: Path) -> None:
    """
    Generate product_profile.json and product_knowledge.json under campaign_root.
    Safe to call without API key (writes stub + skipped state).
    """
    campaign_root = campaign_root.resolve()
    _write_state(campaign_root, "running", "")

    prd_text = _read_prd_text(campaign_root)
    brief = _read_user_brief(campaign_root)
    images = _collect_image_paths(campaign_root)

    if not os.environ.get("GEMINI_API_KEY"):
        stub = {
            "version": "1.0",
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "summary": "Understanding skipped: GEMINI_API_KEY not set.",
            "positioning": "",
            "audience": "",
            "key_selling_points": [],
            "creative_constraints": [],
            "terminology": [],
            "image_insights": [],
            "pending_conflicts": [],
            "sources": {"prd": bool(prd_text), "image_count": len(images)},
        }
        _persist_profile(campaign_root, stub)
        _persist_knowledge(campaign_root, stub)
        _write_state(campaign_root, "skipped", "GEMINI_API_KEY not set")
        return

    # Truncate very long PRD for token limits
    prd_excerpt = prd_text[:24000] if prd_text else "(no PRD file configured)"
    text_block = (
        f"## user_brief\n{brief or '(none)'}\n\n## PRD excerpt\n{prd_excerpt}\n\n"
        f"You are given {len(images)} product images in order. "
        "Analyze them together with the text. Output JSON per schema."
    )

    try:
        client = GeminiClient()
        if images:
            result = await client.chat_structured_with_images(
                text=text_block,
                image_paths=images,
                response_schema=_PROFILE_SCHEMA,
                system=(
                    "You extract structured marketing-oriented product knowledge from PRD and images. "
                    "Do not invent features not supported by text or images; list uncertainties under pending_conflicts."
                ),
                max_tokens=8192,
                temperature=0.2,
            )
        else:
            from src.llm.base import LLMMessage

            messages = [LLMMessage(role="user", content=text_block)]
            raw = await client.chat_structured(
                messages=messages,
                response_schema=_PROFILE_SCHEMA,
                system=(
                    "You extract structured marketing-oriented product knowledge from PRD text only. "
                    "Do not invent; use pending_conflicts for gaps."
                ),
                max_tokens=8192,
                temperature=0.2,
            )
            result = raw

        if not isinstance(result, dict):
            result = {}

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        profile = {
            "version": "1.0",
            "updated_at": now,
            "summary": result.get("summary") or "",
            "positioning": result.get("positioning") or "",
            "audience": result.get("audience") or "",
            "key_selling_points": result.get("key_selling_points") or [],
            "creative_constraints": result.get("creative_constraints") or [],
            "terminology": result.get("terminology") or [],
            "image_insights": result.get("image_insights") or [],
            "pending_conflicts": result.get("pending_conflicts") or [],
            "sources": {"prd": bool(prd_text), "image_count": len(images)},
        }
        _persist_profile(campaign_root, profile)
        _persist_knowledge(campaign_root, profile)
        _write_state(campaign_root, "done", "")
    except Exception as e:
        _write_state(campaign_root, "error", str(e))
        raise


def _persist_profile(campaign_root: Path, profile: dict) -> None:
    path = product_profile_path(campaign_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def _persist_knowledge(campaign_root: Path, profile: dict) -> None:
    path = product_knowledge_path(campaign_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    facts: list[str] = []
    for x in profile.get("key_selling_points") or []:
        facts.append(f"selling_point: {x}")
    for x in profile.get("creative_constraints") or []:
        facts.append(f"constraint: {x}")
    for x in profile.get("terminology") or []:
        facts.append(f"term: {x}")
    payload = {
        "version": "1.0",
        "namespace": "product_knowledge",
        "updated_at": profile.get("updated_at", ""),
        "facts": facts[:200],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
