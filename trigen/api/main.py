"""Trigen Backend API Main Entry.

FastAPI application initialization, middleware registration, router mounting,
and lifecycle management. Port: 7100.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trigen.api.config import config
from trigen.api.models.database import Database
from trigen.api.routers import assets, chat, health, models, scene, tools
from trigen.api.services.agent_service import AgentService
from trigen.api.services.session_service import SessionService

logging.basicConfig(
    level=logging.DEBUG if config.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("trigen.api")  # API module logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: initialize the database and Agent on startup,
    and release resources on shutdown.
    """
    os.makedirs(config.exports_dir, exist_ok=True)  # Create exports directory

    db = Database(config.db_url)
    await db.init()
    SessionService.get().bind_db(db)
    logger.info("Database initialized: %s", config.db_url)  # Database initialization done log

    # Pre-initialize Agent (triggers workspace creation)
    _ = AgentService.get().orchestrator
    logger.info("Trigen Agent ready | LLM configured: %s | port: %d", AgentService.get().llm_configured, config.port)

    # Run dynamic model discovery in the background (non-blocking)
    import asyncio
    from trigen.llm.model_discovery import discover_all
    from trigen.llm.router import router as model_router

    async def _bg_discovery():
        try:
            counts = await discover_all(model_router)
            total = sum(counts.values())
            if total > 0:
                logger.info("Startup model discovery: %d new models (%s)", total, counts)
        except Exception as exc:
            logger.warning("Startup model discovery failed: %s", str(exc)[:100])

    asyncio.create_task(_bg_discovery())

    yield

    await db.close()
    logger.info("Trigen API shutdown")  # API shutdown log


def create_app() -> FastAPI:
    """Build the FastAPI application instance."""
    app = FastAPI(
        title="Trigen API",
        description="AI-Native 3D Creation Agent Platform — Backend API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS / Cross-origin resource sharing middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    api_prefix = "/api"
    app.include_router(health.router, prefix=api_prefix)
    app.include_router(chat.router, prefix=api_prefix)
    app.include_router(scene.router, prefix=api_prefix)
    app.include_router(assets.router, prefix=api_prefix)
    app.include_router(tools.router, prefix=api_prefix)
    app.include_router(models.router, prefix=api_prefix)

    # Root route
    @app.get("/")
    async def root():
        return {
            "name": "Trigen API",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/api/health",
        }

    return app


app = create_app()  # Global FastAPI application instance


if __name__ == "__main__":
    uvicorn.run(
        "trigen.api.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        log_level="debug" if config.debug else "info",
    )
