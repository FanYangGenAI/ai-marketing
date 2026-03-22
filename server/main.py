import os
import sys
from pathlib import Path

from fastapi import FastAPI
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

app = FastAPI(title="AI Marketing API", version="1.0.0")

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
