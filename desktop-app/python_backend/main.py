import os
import sys
import logging

# Force the backend root to the front and remove the project root to avoid shadowing
backend_root = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(backend_root)) # Interview TA Bot folder
sys.path = [backend_root] + [p for p in sys.path if p != backend_root and p != project_root]

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import upload, interview, audio

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Interview Support Agent",
    description="Enterprise-grade real-time interview assistant powered by Azure OpenAI",
    version="1.0.0",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",     # Vite dev server
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5500",     # VS Code Live Server (legacy)
        "http://127.0.0.1:5500",
        "file://",                   # Electron production (file:// protocol)
    ],
    allow_origin_regex=r".*",        # catch-all for packaged Electron
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(upload.router)
app.include_router(interview.router)
app.include_router(audio.router)

from main_live import register_live_router
register_live_router(app)

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "app": "Interview Support Agent"}


if __name__ == "__main__":
    import uvicorn
    from config import get_settings

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
