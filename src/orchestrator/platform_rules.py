"""
Load platform JSON from src/config/platforms/{platform}.json.

Used by API and orchestration code for a single source of truth.
"""

from __future__ import annotations

import json
from pathlib import Path

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config" / "platforms"


def platform_config_path(platform: str) -> Path:
    return _CONFIG_DIR / f"{platform}.json"


def load_platform_config(platform: str) -> dict:
    p = platform_config_path(platform)
    if not p.exists():
        raise FileNotFoundError(
            f"platform config not found: {p} (supported: {[x.stem for x in _CONFIG_DIR.glob('*.json')]})"
        )
    return json.loads(p.read_text(encoding="utf-8"))


def derive_hard_rules_from_specs(cfg: dict) -> dict:
    """Backward-compatible when hard_rules block is absent."""
    specs = cfg.get("specs", cfg)
    body = specs.get("body_chars", {})
    return {
        "title": {"required": True, "max_chars": int(specs.get("title_max_chars", 20))},
        "body": {"required": True, "max_chars": int(body.get("max", 1000))},
    }


def get_hard_rules_dict(cfg: dict) -> dict:
    hr = cfg.get("hard_rules")
    if isinstance(hr, dict) and hr:
        return hr
    return derive_hard_rules_from_specs(cfg)
