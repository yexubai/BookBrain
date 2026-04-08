"""BookBrain FastAPI application entry point.

This module bootstraps the FastAPI application, configures middleware,
and manages application lifecycle events (database init, search index
healing on startup, graceful shutdown).
"""

import os
# Set HuggingFace mirror for China network environments.
# Must be set before any HuggingFace library imports to take effect.
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db.database import init_db, close_db, async_session
from api.routes import router
from search.vector_store import vector_store

# ─── Logging Setup ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bookbrain")


# ─── Application Lifespan ──────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown lifecycle events.

    Startup sequence:
      1. Load persisted user settings from disk (data/user_settings.json)
      2. Ensure required data directories exist (data/, covers/, index/)
      3. Initialize database tables and FTS5 virtual tables
      4. Launch background task to self-heal FAISS vector index mapping

    Shutdown:
      - Dispose of the database engine connection pool
    """
    # --- Startup ---
    settings.load_from_disk()

    # Honour debug flag that may have been toggled in persisted settings
    if settings.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Starting BookBrain v%s", settings.app_version)
    settings.ensure_directories()
    await init_db()
    logger.info("Database initialized")

    # Repair the FAISS id_map in the background so startup isn't blocked.
    # This reconciles the in-memory vector-to-chunk mapping with the DB.
    async def background_heal():
        try:
            async with async_session() as session:
                await vector_store.heal_index(session)
        except Exception as e:
            logger.error("Background search index healing failed: %s", e)

    asyncio.create_task(background_heal())

    yield  # Application is running

    # --- Shutdown ---
    logger.info("Shutting down BookBrain")
    await close_db()


# ─── FastAPI App Instance ──────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Ebook management system with OCR, classification, and semantic search",
    lifespan=lifespan,
)

# CORS middleware: allow all origins for local/NAS use.
# Note: allow_credentials=True is incompatible with allow_origins=["*"] per
# the CORS spec, so credentials are disabled here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all /api/* routes defined in api/routes.py
app.include_router(router)


# ─── Health Check ──────────────────────────────────────────────

@app.get("/")
async def root():
    """Root health-check endpoint. Returns app name, version, and status."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }


# ─── Development Entry Point ──────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,  # Auto-reload on code changes in debug mode
    )
