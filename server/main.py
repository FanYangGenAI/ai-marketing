import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

# Full date+time on all log lines (uvicorn installs its own handlers after import)
_LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_DATE = "%Y-%m-%d %H:%M:%S"


def _ts_formatter() -> logging.Formatter:
    return logging.Formatter(_LOG_FMT, datefmt=_LOG_DATE)


def _configure_logging() -> None:
    """Early import-time setup (before uvicorn adds handlers)."""
    formatter = _ts_formatter()
    root = logging.getLogger()
    if not root.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(formatter)
        root.addHandler(h)
        root.setLevel(logging.INFO)
    else:
        for h in root.handlers:
            h.setFormatter(formatter)


def _apply_timestamps_to_all_handlers() -> None:
    """
    Uvicorn attaches StreamHandlers to uvicorn / uvicorn.error / uvicorn.access
    after the app module loads. Re-apply formatters at startup so every line has asctime.
    """
    formatter = _ts_formatter()
    seen: set[int] = set()

    def touch(logger: logging.Logger) -> None:
        for h in logger.handlers:
            hid = id(h)
            if hid in seen:
                continue
            seen.add(hid)
            if isinstance(h, logging.Handler):
                h.setFormatter(formatter)

    touch(logging.root)
    for name in list(logging.Logger.manager.loggerDict.keys()):
        touch(logging.getLogger(name))


_configure_logging()
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Support running as both:
#   - `uvicorn main:app` (from server/ directory)
#   - `uvicorn server.main:app` (from project root)
try:
    from server.routers import campaigns, images
except ModuleNotFoundError:
    # Running from within server/ directory
    _server_dir = Path(__file__).parent
    if str(_server_dir) not in sys.path:
        sys.path.insert(0, str(_server_dir.parent))
    from server.routers import campaigns, images


@asynccontextmanager
async def lifespan(app: FastAPI):
    _apply_timestamps_to_all_handlers()
    yield


app = FastAPI(title="AI Marketing API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(campaigns.router)
app.include_router(images.router)

# In production mode, serve frontend/dist/ as static files
frontend_dist = os.environ.get("FRONTEND_DIST")
if frontend_dist:
    dist_path = Path(frontend_dist)
    if dist_path.exists():
        assets_dir = dist_path / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/")
        async def root():
            return FileResponse(str(dist_path / "index.html"))

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            # Don't intercept API routes
            if full_path.startswith("api/"):
                from fastapi import HTTPException
                raise HTTPException(status_code=404)
            index_file = dist_path / "index.html"
            static_file = dist_path / full_path
            if static_file.exists() and static_file.is_file():
                return FileResponse(str(static_file))
            return FileResponse(str(index_file))
else:
    @app.get("/")
    async def root():
        return RedirectResponse(url="http://localhost:5173")
