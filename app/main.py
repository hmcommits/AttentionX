"""
AttentionX — FastAPI Application Entry Point
=============================================
Initializes the app, registers all API routers, and configures
middleware. Run with:
    uvicorn app.main:app --reload
"""

import logging
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Load .env before any service imports that read os.getenv()
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, upload, analyze, export

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("attentionx")


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown hooks)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Resource initialisation on startup, cleanup on shutdown."""
    logger.info("🚀  AttentionX API starting up...")
    # TODO: warm up Whisper model, verify Gemini key on startup
    yield
    logger.info("🛑  AttentionX API shutting down...")
    # TODO: flush any queued jobs, close thread pools


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AttentionX API",
    description=(
        "AI-powered content repurposing engine — automatically extracts "
        "60-second viral clips from long-form video using Narrative Intelligence."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS — allow Streamlit dev server (localhost:8501)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(health.router, tags=["Health"])
app.include_router(upload.router,  prefix="/api/v1", tags=["Upload"])
app.include_router(analyze.router, prefix="/api/v1", tags=["Analyze"])
app.include_router(export.router,  prefix="/api/v1", tags=["Export"])
