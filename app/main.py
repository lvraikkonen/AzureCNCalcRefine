"""FastAPI application entry point.

Run with:
    uv run uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.explore import router as explore_router

app = FastAPI(
    title="Azure.cn Pricing Calculator",
    description="Azure China 定价计算器 API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(explore_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


# Frontend static files — must be after API routes
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
