import json
import os
import re
import subprocess
import sys
from datetime import date as date_cls
from pathlib import Path
from typing import Any, Dict, List, Optional

import tempfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from server.config import CAMPAIGNS_ROOT

router = APIRouter()

# Max bytes per uploaded file (PRD or attachment)
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

ALLOWED_COLD_START_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}

# ── Pydantic 请求体模型 ────────────────────────────────────────────────────────

class CreateProductRequest(BaseModel):
    name: str
    user_brief: str = ""

class UpdateConfigRequest(BaseModel):
    user_brief: Optional[str] = None
    suppress_version_in_copy: Optional[bool] = None

class RunPipelineRequest(BaseModel):
    today_note: str = ""

class FeedbackRequest(BaseModel):
    action: str          # "accept" | "reject"
    reason: str = ""     # 拒绝时填写原因


class AssetNotePatchRequest(BaseModel):
    note: str = ""

# ── 运行状态追踪（内存，进程级别）─────────────────────────────────────────────
_running_processes: Dict[str, subprocess.Popen] = {}
_understanding_processes: Dict[str, subprocess.Popen] = {}

def _get_repo_root() -> Path:
    """获取项目根目录（server/ 的上级）。"""
    return Path(__file__).parent.parent.parent


def _read_json(path: Path) -> Any:
    """Read and parse a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _safe_filename(name: str) -> str:
    """ASCII-safe basename for stored files (no path segments)."""
    base = Path(name).name
    if not base:
        return "upload.dat"
    cleaned = re.sub(r"[^\w.\-]", "_", base)
    if not cleaned or cleaned in (".", ".."):
        return "upload.dat"
    return cleaned[:180]


def _unique_path(directory: Path, filename: str) -> Path:
    """Pick a non-existing path under directory."""
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    for i in range(1, 1000):
        alt = directory / f"{stem}_{i}{suffix}"
        if not alt.exists():
            return alt
    raise HTTPException(status_code=500, detail="Too many files with the same name")


def _relative_to_repo(repo_root: Path, absolute_file: Path) -> str:
    """Path string for product_config prd_path (posix, relative to repo root when possible)."""
    try:
        rel = absolute_file.resolve().relative_to(repo_root.resolve())
        return rel.as_posix()
    except ValueError:
        return str(absolute_file.resolve()).replace("\\", "/")


async def _save_upload_stream(dest: Path, upload: UploadFile) -> None:
    """Write upload to dest with size limit."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    chunk_size = 1024 * 1024
    with open(dest, "wb") as out:
        while True:
            chunk = await upload.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds limit of {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
                )
            out.write(chunk)


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

        # 读取用户反馈状态
        feedback = None
        feedback_path = entry / "feedback.json"
        if feedback_path.exists():
            try:
                fb = _read_json(feedback_path)
                feedback = fb.get("action")  # "accept" | "reject"
            except Exception:
                pass

        results.append({
            "date": entry.name,
            "audit_passed": audit_passed,
            "stages_done": stages_done,
            "feedback": feedback,
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
            if isinstance(img, dict):
                p = img.get("path")
                if isinstance(p, str):
                    img["path"] = p.replace("\\", "/")

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
    """Read asset_library/index.json for a product (empty index if not yet created)."""
    index_file = CAMPAIGNS_ROOT / product / "asset_library" / "index.json"
    if not index_file.exists():
        return {"version": "1.0", "assets": []}

    data = _read_json(index_file)

    # Normalize backslashes in asset file paths
    if "assets" in data and isinstance(data["assets"], list):
        for asset in data["assets"]:
            if isinstance(asset, dict):
                f = asset.get("file")
                if isinstance(f, str):
                    asset["file"] = f.replace("\\", "/")
            if "note" not in asset:
                asset["note"] = ""
            if "disabled" not in asset:
                asset["disabled"] = False

    return data


@router.get("/api/products/{product}/memory/{platform}")
async def get_memory(product: str, platform: str):
    """Read memory/lessons_{platform}.json for a product."""
    memory_file = CAMPAIGNS_ROOT / product / "memory" / f"lessons_{platform}.json"
    if not memory_file.exists():
        raise HTTPException(status_code=404, detail=f"Memory for platform '{platform}' not found")
    return _read_json(memory_file)


# ── 写操作路由 ─────────────────────────────────────────────────────────────────

@router.post("/api/products")
async def create_product(req: CreateProductRequest):
    """创建新产品项目，初始化目录结构和 product_config.json。"""
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="产品名称不能为空")

    product_dir = CAMPAIGNS_ROOT / name
    if product_dir.exists():
        raise HTTPException(status_code=409, detail=f"产品 '{name}' 已存在")

    # 创建目录结构（docs/materials：参考文档与附件）
    # Strategy artifacts live under daily/{date}/strategy/ at runtime; no product-level strategy/ folder
    for subdir in [
        "config",
        "docs",
        "docs/materials",
        "memory",
        "asset_library",
        "daily",
        "attachments",
        "attachments/raw",
    ]:
        (product_dir / subdir).mkdir(parents=True, exist_ok=True)

    # 写入 product_config.json
    config = {
        "platform": "xiaohongshu",
        "suppress_version_in_copy": True,
        "user_brief": req.user_brief,
    }
    config_path = product_dir / "config" / "product_config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"name": name, "status": "created"}


@router.post("/api/products/{product}/config")
async def update_config(product: str, req: UpdateConfigRequest):
    """更新产品配置（user_brief、suppress_version_in_copy 等）。"""
    config_path = CAMPAIGNS_ROOT / product / "config" / "product_config.json"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"产品 '{product}' 不存在")

    config = _read_json(config_path)
    if req.user_brief is not None:
        config["user_brief"] = req.user_brief
    if req.suppress_version_in_copy is not None:
        config["suppress_version_in_copy"] = req.suppress_version_in_copy

    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "updated", "config": config}


@router.get("/api/products/{product}/config")
async def get_config(product: str):
    """获取产品配置。"""
    config_path = CAMPAIGNS_ROOT / product / "config" / "product_config.json"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"产品 '{product}' 不存在")
    return _read_json(config_path)


@router.get("/api/products/{product}/documents")
async def list_product_documents(product: str):
    """List PRD path from config and files under docs/ and docs/materials/."""
    product_dir = CAMPAIGNS_ROOT / product
    if not product_dir.exists():
        raise HTTPException(status_code=404, detail=f"产品 '{product}' 不存在")

    config_path = product_dir / "config" / "product_config.json"
    prd_path = None
    if config_path.exists():
        try:
            prd_path = _read_json(config_path).get("prd_path")
        except Exception:
            pass

    docs_root = product_dir / "docs"
    materials_dir = docs_root / "materials"
    entries: List[Dict[str, Any]] = []

    def push_file(abs_path: Path, category: str) -> None:
        if not abs_path.is_file():
            return
        rel = abs_path.relative_to(product_dir)
        try:
            sz = abs_path.stat().st_size
        except OSError:
            sz = 0
        entries.append(
            {
                "name": abs_path.name,
                "path": rel.as_posix(),
                "size": sz,
                "category": category,
            }
        )

    if docs_root.exists():
        for p in sorted(docs_root.iterdir()):
            if p.is_file():
                push_file(p, "docs")
        if materials_dir.exists():
            for p in sorted(materials_dir.iterdir()):
                if p.is_file():
                    push_file(p, "materials")

    return {"prd_path": prd_path, "files": entries}


@router.post("/api/products/{product}/documents/prd")
async def upload_product_prd(product: str, file: UploadFile = File(...)):
    """Upload PRD file to campaigns/{product}/docs/, set product_config prd_path."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing file")

    product_dir = CAMPAIGNS_ROOT / product
    if not product_dir.exists():
        raise HTTPException(status_code=404, detail=f"产品 '{product}' 不存在")

    config_path = product_dir / "config" / "product_config.json"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Missing product_config.json")

    docs_dir = product_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    fname = _safe_filename(file.filename)
    dest = _unique_path(docs_dir, fname)
    await _save_upload_stream(dest, file)

    repo_root = _get_repo_root().resolve()
    prd_rel = _relative_to_repo(repo_root, dest)

    config = _read_json(config_path)
    config["prd_path"] = prd_rel
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"status": "ok", "prd_path": prd_rel}


@router.post("/api/products/{product}/documents/attachments")
async def upload_product_attachments(
    product: str,
    files: List[UploadFile] = File(...),
):
    """Upload reference files to campaigns/{product}/docs/materials/."""
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    product_dir = CAMPAIGNS_ROOT / product
    if not product_dir.exists():
        raise HTTPException(status_code=404, detail=f"产品 '{product}' 不存在")

    materials_dir = product_dir / "docs" / "materials"
    repo_root = _get_repo_root().resolve()
    saved: List[str] = []

    for up in files:
        if not up.filename:
            continue
        dest = _unique_path(materials_dir, _safe_filename(up.filename))
        await _save_upload_stream(dest, up)
        saved.append(_relative_to_repo(repo_root, dest))

    if not saved:
        raise HTTPException(status_code=400, detail="No valid files uploaded")

    return {"status": "ok", "paths": saved}


@router.get("/api/products/{product}/run/status")
async def get_run_status(product: str):
    """获取当前或最近一次 Pipeline 运行状态（供前端轮询）。"""
    proc = _running_processes.get(product)
    is_running = proc is not None and proc.poll() is None

    # 找最近一次 daily 目录的 pipeline state
    daily_dir = CAMPAIGNS_ROOT / product / "daily"
    latest_state = None
    latest_date = None
    if daily_dir.exists():
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        for entry in sorted(daily_dir.iterdir(), reverse=True):
            if entry.is_dir() and date_pattern.match(entry.name):
                state_file = entry / ".pipeline_state.json"
                if state_file.exists():
                    try:
                        latest_state = _read_json(state_file)
                        latest_date = entry.name
                    except Exception:
                        pass
                    break

    # 判断当前运行阶段
    current_stage = None
    if is_running and latest_state:
        for stage in ["strategist", "planner", "scriptwriter", "director", "creator", "audit"]:
            s = latest_state.get(stage, {})
            if isinstance(s, dict) and not s.get("done"):
                current_stage = stage
                break

    return {
        "running": is_running,
        "current_stage": current_stage,
        "latest_date": latest_date,
        "stages": latest_state or {},
    }


@router.post("/api/products/{product}/run")
async def run_pipeline(product: str, req: RunPipelineRequest):
    """异步触发 Pipeline 运行。"""
    product_dir = CAMPAIGNS_ROOT / product
    if not product_dir.exists():
        raise HTTPException(status_code=404, detail=f"产品 '{product}' 不存在")

    # 防重入：已在运行中则拒绝
    existing_proc = _running_processes.get(product)
    if existing_proc is not None and existing_proc.poll() is None:
        raise HTTPException(status_code=409, detail="Pipeline 正在运行中，请等待完成后再触发")

    repo_root = _get_repo_root()
    cmd = [sys.executable, "main.py", "--product", product]
    if req.today_note:
        cmd += ["--note", req.today_note]

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(repo_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _running_processes[product] = proc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动 Pipeline 失败：{e}")

    return {"status": "started", "pid": proc.pid}


# ── Cold-start ingestion (text + images, product profile) ───────────────────────


@router.get("/api/products/{product}/cold-start/status")
async def cold_start_status(product: str):
    """Understanding job state + quick manifest summary."""
    product_dir = CAMPAIGNS_ROOT / product
    if not product_dir.exists():
        raise HTTPException(status_code=404, detail=f"产品 '{product}' 不存在")

    state_path = product_dir / "attachments" / "understanding_state.json"
    state: Dict[str, Any] = {"status": "idle", "message": "", "updated_at": None}
    if state_path.exists():
        try:
            state = {**state, **_read_json(state_path)}
        except Exception:
            pass

    proc = _understanding_processes.get(product)
    running = proc is not None and proc.poll() is None
    if running:
        state = {**state, "status": "running", "message": state.get("message", "")}

    profile_exists = (product_dir / "config" / "product_profile.json").exists()
    return {
        **state,
        "process_running": running,
        "product_profile_exists": profile_exists,
    }


@router.post("/api/products/{product}/cold-start/images")
async def upload_cold_start_images(
    product: str,
    files: List[UploadFile] = File(...),
    tag: str = Form("product_ui"),
):
    """
    Upload images into attachments/raw + manifest + Asset Library.
    Allowed: png, jpg, jpeg, webp (no video/GIF).
    """
    product_dir = CAMPAIGNS_ROOT / product
    if not product_dir.exists():
        raise HTTPException(status_code=404, detail=f"产品 '{product}' 不存在")

    if tag not in ("brand", "product_ui", "marketing_ref"):
        tag = "product_ui"

    tmp_paths: List[Path] = []
    try:
        sys.path.insert(0, str(_get_repo_root()))
        from src.cold_start.ingest import ingest_image_files

        for up in files:
            if not up.filename:
                continue
            suf = Path(up.filename).suffix.lower()
            if suf not in ALLOWED_COLD_START_IMAGE_EXT:
                continue
            fd, name = tempfile.mkstemp(suffix=suf)
            os.close(fd)
            tmp_p = Path(name)
            await _save_upload_stream(tmp_p, up)
            tmp_paths.append(tmp_p)

        if not tmp_paths:
            raise HTTPException(
                status_code=400,
                detail="No valid image files (allowed: png, jpg, jpeg, webp)",
            )

        saved = ingest_image_files(product_dir, tmp_paths, default_tag=tag)
        return {"status": "ok", "items": saved, "tag": tag}
    finally:
        for p in tmp_paths:
            p.unlink(missing_ok=True)


@router.post("/api/products/{product}/cold-start/understand")
async def trigger_cold_start_understand(product: str):
    """Run understanding job in a subprocess (writes product_profile.json)."""
    product_dir = CAMPAIGNS_ROOT / product
    if not product_dir.exists():
        raise HTTPException(status_code=404, detail=f"产品 '{product}' 不存在")

    existing = _understanding_processes.get(product)
    if existing is not None and existing.poll() is None:
        raise HTTPException(status_code=409, detail="理解任务正在运行中")

    repo_root = _get_repo_root()
    cmd = [
        sys.executable,
        "-m",
        "src.cold_start.cli",
        "--campaign-root",
        str(product_dir.resolve()),
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(repo_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _understanding_processes[product] = proc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动理解任务失败：{e}")

    return {"status": "started", "pid": proc.pid}


@router.patch("/api/products/{product}/assets/{asset_id}")
async def patch_asset_note(product: str, asset_id: str, req: AssetNotePatchRequest):
    """Update user note on an asset (Asset Library + manifest if linked)."""
    product_dir = CAMPAIGNS_ROOT / product
    if not product_dir.exists():
        raise HTTPException(status_code=404, detail=f"产品 '{product}' 不存在")

    sys.path.insert(0, str(_get_repo_root()))
    from src.orchestrator.asset_library import AssetLibrary
    from src.cold_start.manifest import item_by_asset_id, load_manifest, save_manifest

    lib = AssetLibrary(str(product_dir / "asset_library"))
    updated = lib.update_note(asset_id, req.note)
    if not updated:
        raise HTTPException(status_code=404, detail="Asset not found")

    man = load_manifest(product_dir)
    it = item_by_asset_id(man, asset_id)
    if it:
        it.note = req.note
        save_manifest(product_dir, man)

    return {"status": "ok", "asset": {"id": updated.id, "note": updated.note}}


@router.delete("/api/products/{product}/assets/{asset_id}")
async def delete_asset(product: str, asset_id: str):
    """Soft-delete asset (disabled) and mark manifest item removed."""
    product_dir = CAMPAIGNS_ROOT / product
    if not product_dir.exists():
        raise HTTPException(status_code=404, detail=f"产品 '{product}' 不存在")

    sys.path.insert(0, str(_get_repo_root()))
    from src.orchestrator.asset_library import AssetLibrary
    from src.cold_start.manifest import item_by_asset_id, load_manifest, mark_item_removed, save_manifest

    lib = AssetLibrary(str(product_dir / "asset_library"))
    rec = lib.set_disabled(asset_id, True)
    if not rec:
        raise HTTPException(status_code=404, detail="Asset not found")

    man = load_manifest(product_dir)
    it = item_by_asset_id(man, asset_id)
    if it:
        mark_item_removed(man, it.id)
        save_manifest(product_dir, man)

    return {"status": "ok", "id": asset_id}


@router.get("/api/products/{product}/cold-start/profile")
async def get_product_profile(product: str):
    """Return product_profile.json for UI review."""
    path = CAMPAIGNS_ROOT / product / "config" / "product_profile.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="product_profile.json not found")
    return _read_json(path)


@router.post("/api/products/{product}/{date}/feedback")
async def submit_feedback(product: str, date: str, req: FeedbackRequest):
    """
    提交用户对每日素材包的接受/拒绝反馈。
    写入 feedback.json，同步更新 LessonMemory。
    """
    if req.action not in ("accept", "reject"):
        raise HTTPException(status_code=400, detail="action 必须为 'accept' 或 'reject'")
    if req.action == "reject" and not req.reason.strip():
        raise HTTPException(status_code=400, detail="拒绝时必须填写原因")

    daily_dir = CAMPAIGNS_ROOT / product / "daily" / date
    if not daily_dir.exists():
        raise HTTPException(status_code=404, detail=f"日期 '{date}' 数据不存在")

    feedback_path = daily_dir / "feedback.json"

    # 防止重复提交
    if feedback_path.exists():
        existing = _read_json(feedback_path)
        raise HTTPException(
            status_code=409,
            detail=f"已提交过反馈（{existing.get('action', '未知')}），不可重复提交"
        )

    feedback_data = {
        "action": req.action,
        "reason": req.reason,
        "date": date,
        "submitted_at": date_cls.today().isoformat(),
    }
    feedback_path.write_text(json.dumps(feedback_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 同步更新 LessonMemory
    try:
        # 动态导入避免循环依赖
        sys.path.insert(0, str(_get_repo_root()))
        from src.orchestrator.lesson_memory import LessonMemory

        # 读取产品平台配置
        cfg_path = CAMPAIGNS_ROOT / product / "config" / "product_config.json"
        platform = "xiaohongshu"
        if cfg_path.exists():
            cfg = _read_json(cfg_path)
            platform = cfg.get("platform", "xiaohongshu")

        lm = LessonMemory(CAMPAIGNS_ROOT / product, platform)

        if req.action == "accept":
            # 读取帖子标题作为正向信号
            pkg_path = daily_dir / "creator" / "post_package.json"
            title = ""
            theme = f"{date} 帖子"
            if pkg_path.exists():
                pkg = _read_json(pkg_path)
                title = pkg.get("title", "")
            lm.write_acceptance(title=title, theme=theme, note=f"用户接受于 {date}")
        else:
            lm.write_rejection(reason=req.reason)
    except Exception as e:
        # LessonMemory 更新失败不影响 feedback 写入
        import logging
        logging.getLogger(__name__).warning(f"LessonMemory 更新失败：{e}")

    return {"status": "submitted", "action": req.action}
