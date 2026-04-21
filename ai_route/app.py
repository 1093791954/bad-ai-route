"""FastAPI application setup and route mounting."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from .anthropic_proxy import router as anthropic_router
from .openai_proxy import router as openai_router
from .admin_api import router as admin_router
from .prober import start_prober, stop_prober
from .upstream import close_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_prober()
    try:
        yield
    finally:
        await stop_prober()
        await close_client()


app = FastAPI(
    title="AI-Route",
    description="Multi-model fallback proxy for OpenAI/Anthropic APIs",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(anthropic_router)
app.include_router(openai_router)
app.include_router(admin_router)


# Static files for web UI
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(static_dir), html=True), name="ui")


@app.get("/")
async def root():
    """Redirect root to web UI."""
    return RedirectResponse(url="/ui/")


@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "ai-route"}
