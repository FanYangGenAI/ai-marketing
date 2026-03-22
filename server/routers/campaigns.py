import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from server.config import CAMPAIGNS_ROOT

router = APIRouter()


def _read_json(path: Path) -> Any:
    """Read and parse a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/api/products")
async def get_products():
    """Scan CAMPAIGNS_ROOT and return list of product folder names sorted."""
    if not CAMPAIGNS_ROOT.exists():
        return {"products": []}

    products = []
    for entry in sorted(CAMPAIGNS_ROOT.iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            products.append(entry.name)

    return {"products": products}


@router.get("/api/products/{product}/dates")
async def get_dates(product: str):
    """Return sorted dates for a product with pipeline status summaries."""
    daily_dir = CAMPAIGNS_ROOT / product / "daily"
    if not daily_dir.exists():
        raise HTTPException(status_code=404, detail=f"Product '{product}' not found")

    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    results = []

    for entry in sorted(daily_dir.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        if not date_pattern.match(entry.name):
            continue

        audit_passed = None
        stages_done = 0

        state_file = entry / ".pipeline_state.json"
        if state_file.exists():
            try:
                state = _read_json(state_file)
                # Count stages with done=true
                stage_keys = ["planner", "scriptwriter", "director", "creator", "audit"]
                for key in stage_keys:
                    if isinstance(state.get(key), dict) and state[key].get("done"):
                        stages_done += 1

                # audit_passed comes from audit.success
                audit_stage = state.get("audit", {})
                if isinstance(audit_stage, dict) and audit_stage.get("done"):
                    audit_passed = bool(audit_stage.get("success"))
            except Exception:
                pass

        results.append({
            "date": entry.name,
            "audit_passed": audit_passed,
            "stages_done": stages_done,
        })

    return results


@router.get("/api/products/{product}/{date}/state")
async def get_state(product: str, date: str):
    """Read .pipeline_state.json for a given product/date."""
    state_file = CAMPAIGNS_ROOT / product / "daily" / date / ".pipeline_state.json"
    if not state_file.exists():
        raise HTTPException(status_code=404, detail="Pipeline state not found")
    return _read_json(state_file)


@router.get("/api/products/{product}/{date}/package")
async def get_package(product: str, date: str):
    """Read creator/post_package.json for a given product/date."""
    package_file = CAMPAIGNS_ROOT / product / "daily" / date / "creator" / "post_package.json"
    if not package_file.exists():
        raise HTTPException(status_code=404, detail="Post package not found")

    data = _read_json(package_file)

    # Normalize backslashes in image paths to forward slashes
    if "images" in data and isinstance(data["images"], list):
        for img in data["images"]:
            if "path" in img:
                img["path"] = img["path"].replace("\\", "/")

    return data


@router.get("/api/products/{product}/{date}/audit")
async def get_audit(product: str, date: str):
    """Read audit/audit_result.json for a given product/date."""
    audit_file = CAMPAIGNS_ROOT / product / "daily" / date / "audit" / "audit_result.json"
    if not audit_file.exists():
        raise HTTPException(status_code=404, detail="Audit result not found")
    return _read_json(audit_file)


@router.get("/api/products/{product}/{date}/file")
async def get_file(product: str, date: str, path: str):
    """Read an arbitrary text file within the daily folder."""
    base_dir = (CAMPAIGNS_ROOT / product / "daily" / date).resolve()
    full_path = (base_dir / path).resolve()

    # Security: ensure path is within allowed directory
    try:
        full_path.relative_to(base_dir)
    except ValueError:
        raise HTTPException(status_code=403, detail="Path outside allowed directory")

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # Detect file type
    suffix = full_path.suffix.lower()
    if suffix == ".md":
        file_type = "markdown"
    elif suffix == ".json":
        file_type = "json"
    else:
        file_type = "text"

    content = full_path.read_text(encoding="utf-8")
    return {"content": content, "type": file_type, "path": path}


@router.get("/api/products/{product}/assets")
async def get_assets(product: str):
    """Read asset_library/index.json for a product."""
    index_file = CAMPAIGNS_ROOT / product / "asset_library" / "index.json"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Asset library not found")

    data = _read_json(index_file)

    # Normalize backslashes in asset file paths
    if "assets" in data and isinstance(data["assets"], list):
        for asset in data["assets"]:
            if "file" in asset:
                asset["file"] = asset["file"].replace("\\", "/")

    return data


@router.get("/api/products/{product}/memory/{platform}")
async def get_memory(product: str, platform: str):
    """Read memory/lessons_{platform}.json for a product."""
    memory_file = CAMPAIGNS_ROOT / product / "memory" / f"lessons_{platform}.json"
    if not memory_file.exists():
        raise HTTPException(status_code=404, detail=f"Memory for platform '{platform}' not found")
    return _read_json(memory_file)
