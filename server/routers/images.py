import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from server.config import CAMPAIGNS_ROOT

router = APIRouter()

# Supported image MIME types
IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".bmp": "image/bmp",
}


@router.get("/api/images")
async def get_image(path: str):
    """
    Serve an image file from within CAMPAIGNS_ROOT.
    Accepts paths like:
      - campaigns/原语/daily/.../img.png  (relative, with campaigns/ prefix)
      - 原语/daily/.../img.png             (relative, without prefix)
      - campaigns\\原语\\...               (Windows backslashes)
    """
    # Normalize backslashes to forward slashes
    normalized = path.replace("\\", "/")

    # Strip leading "campaigns/" prefix if present
    if normalized.startswith("campaigns/"):
        normalized = normalized[len("campaigns/"):]

    # Resolve absolute path within CAMPAIGNS_ROOT
    candidate = (CAMPAIGNS_ROOT / normalized).resolve()

    # Security: ensure path is within CAMPAIGNS_ROOT
    try:
        candidate.relative_to(CAMPAIGNS_ROOT.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path outside allowed directory")

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    suffix = candidate.suffix.lower()
    media_type = IMAGE_TYPES.get(suffix)
    if not media_type:
        # Fallback to mimetypes detection
        media_type, _ = mimetypes.guess_type(str(candidate))
        if not media_type:
            media_type = "application/octet-stream"

    return FileResponse(str(candidate), media_type=media_type)
