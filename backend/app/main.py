"""
FastAPI Application Entry Point
================================
Bootstraps the application, initialises shared services (config, database,
event bus), and mounts the API router.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import ConfigManager
from app.core.database import DedupDatabase
from app.core.logger import EventBus

# ---------------------------------------------------------------------------
# Shared service singletons (attached to app.state)
# ---------------------------------------------------------------------------

config_manager = ConfigManager()
dedup_db = DedupDatabase()
event_bus = EventBus()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-24s  %(levelname)-5s  %(message)s",
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks."""
    # -- startup --
    await config_manager.load()
    dedup_db.init()
    logging.getLogger("omniflow").info(
        "Omni-InfoFlow backend ready  (config=%s, db=%s)",
        config_manager.path,
        dedup_db._path,
    )
    yield
    # -- shutdown --
    dedup_db.close()


app = FastAPI(
    title="Omni-InfoFlow",
    description="Plugin-driven information processing engine",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach shared services so route handlers can access them via request.app
app.state.config_manager = config_manager
app.state.dedup_db = dedup_db
app.state.event_bus = event_bus

app.include_router(router, prefix="/api")
