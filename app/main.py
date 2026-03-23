"""FastAPI application entry point.

Run with:
    uv run uvicorn app.main:app --reload
"""
import logging
import mimetypes
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.explore import router as explore_router
from app.api.products import router as products_router

logger = logging.getLogger(__name__)

# Fix MIME types for JS/CSS modules - Windows registry may map .js as text/plain
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle events."""
    # Pre-load published service configs into in-memory cache if DB is available
    if os.environ.get("DATABASE_URL"):
        try:
            from app.database import get_session_factory
            from app.services.config_repo import load_all_published_to_cache
            from app.services.catalog_cache import load_catalog_to_cache

            factory = get_session_factory()
            async with factory() as session:
                n = await load_all_published_to_cache(session)
                logger.info("Loaded %d published service configs from DB", n)
                await load_catalog_to_cache(session)
                logger.info("Loaded product catalog from DB")
        except Exception as exc:
            logger.warning(
                "Could not load configs from DB at startup (will use JSON fallback): %s", exc
            )

    yield  # application runs here


app = FastAPI(
    title="Azure.cn Pricing Calculator",
    description="Azure China 定价计算器 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
app.include_router(explore_router)
app.include_router(products_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


# Admin frontend — must be before the public frontend mount
import pathlib

_ADMIN_DIR = pathlib.Path(__file__).resolve().parent.parent / "admin"
if _ADMIN_DIR.exists():
    app.mount("/admin", StaticFiles(directory=str(_ADMIN_DIR), html=True), name="admin")

# Public frontend static files — must be last (catches all unmatched routes)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
