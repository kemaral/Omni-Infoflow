"""
API Routes (v2 — Milestone 2)
===============================
RESTful + SSE endpoints consumed by the WebUI and external tooling.

Endpoints:
    GET   /api/health             – liveness check
    GET   /api/config             – current config
    PATCH /api/config             – partial config update
    POST  /api/workflow/run       – trigger a pipeline run
    GET   /api/logs               – recent NodeEvent log stream
    GET   /api/logs/stream        – SSE real-time event stream
    GET   /api/status             – engine / db summary stats
    GET   /api/items              – recently processed items from dedup db
    GET   /api/plugins/discover   – manifests for all known plugins
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.config import ConfigManager
from app.core.database import DedupDatabase
from app.core.engine import PipelineEngine, PluginRegistry
from app.core.logger import EventBus

router = APIRouter()


# -- helpers ----------------------------------------------------------------

def _cfg(request: Request) -> ConfigManager:
    return request.app.state.config_manager


def _db(request: Request) -> DedupDatabase:
    return request.app.state.dedup_db


def _bus(request: Request) -> EventBus:
    return request.app.state.event_bus


# -- health -----------------------------------------------------------------

@router.get("/health")
async def health():
    return {"status": "ok", "service": "omni-infoflow"}


# -- config -----------------------------------------------------------------

@router.get("/config")
async def get_config(request: Request):
    cfg = await _cfg(request).load()
    return cfg.model_dump(by_alias=True)


@router.patch("/config")
async def patch_config(request: Request, body: dict[str, Any]):
    updated = await _cfg(request).patch(body)
    return updated.model_dump(by_alias=True)


# -- workflow ---------------------------------------------------------------

# Track active runs for status reporting
_active_runs: dict[str, asyncio.Task] = {}


@router.post("/workflow/run")
async def trigger_run(request: Request):
    """Kick off a pipeline run in the background and return immediately."""
    engine = PipelineEngine(
        config=_cfg(request),
        db=_db(request),
        bus=_bus(request),
    )

    async def _do_run() -> dict[str, Any]:
        result = await engine.execute()
        _active_runs.pop(result.get("run_id", ""), None)
        return result

    task = asyncio.create_task(_do_run())
    # We don't have run_id yet, but we'll track by task id
    task_id = id(task)
    _active_runs[str(task_id)] = task

    return {"message": "Pipeline run started", "task_id": str(task_id)}


# -- logs / events ----------------------------------------------------------

@router.get("/logs")
async def get_logs(request: Request, limit: int = 50):
    events = _bus(request).recent(limit)
    return [e.model_dump(mode="json") for e in events]


@router.get("/logs/stream")
async def stream_logs(request: Request):
    """Server-Sent Events (SSE) stream of pipeline events.

    The frontend connects to this endpoint and receives real-time
    NodeEvent objects as they're emitted by the engine.

    Usage (JavaScript)::

        const es = new EventSource('/api/logs/stream');
        es.onmessage = (e) => console.log(JSON.parse(e.data));
    """
    bus = _bus(request)

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        bus._subscribers.append(queue)
        try:
            yield "data: {\"type\": \"connected\"}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    payload = json.dumps(event.model_dump(mode="json"))
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive to prevent proxy timeout
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in bus._subscribers:
                bus._subscribers.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# -- status -----------------------------------------------------------------

@router.get("/status")
async def get_status(request: Request):
    db = _db(request)
    bus = _bus(request)
    return {
        "processed_items_count": db.count(),
        "event_buffer_size": bus.total,
        "active_runs": len(_active_runs),
    }


# -- items ------------------------------------------------------------------

@router.get("/items")
async def get_items(request: Request, limit: int = 50):
    return _db(request).recent_items(limit)


# -- plugin discovery -------------------------------------------------------

@router.get("/plugins/discover")
async def discover_plugins(request: Request):
    """Return manifests for all plugins defined in config.

    The frontend uses this to render the plugin store with config schemas.
    """
    cfg = await _cfg(request).load()
    return PluginRegistry.discover_manifests(cfg.plugins)
