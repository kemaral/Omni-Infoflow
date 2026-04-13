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
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.config import ConfigManager
from app.core.database import DedupDatabase
from app.core.engine import PluginRegistry
from app.core.logger import EventBus
from app.core.paths import DEFAULT_SOUL_PATH
from app.core.run_manager import RunManager
from app.core.scheduler import SchedulerService

router = APIRouter()


# -- helpers ----------------------------------------------------------------

def _cfg(request: Request) -> ConfigManager:
    return request.app.state.config_manager


def _db(request: Request) -> DedupDatabase:
    return request.app.state.dedup_db


def _runtime_state_db(request: Request) -> DedupDatabase:
    return request.app.state.runtime_state_db


def _bus(request: Request) -> EventBus:
    return request.app.state.event_bus


def _scheduler(request: Request) -> SchedulerService:
    return request.app.state.scheduler


def _run_manager(request: Request) -> RunManager:
    return request.app.state.run_manager


def _require_admin(
    x_omniflow_admin_token: str | None = Header(default=None),
) -> None:
    configured = os.environ.get("OMNIFLOW_ADMIN_TOKEN", "").strip()
    if not configured:
        return
    if x_omniflow_admin_token != configured:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token",
        )


# -- health -----------------------------------------------------------------

@router.get("/health")
async def health():
    return {"status": "ok", "service": "omni-infoflow"}


# -- config -----------------------------------------------------------------

@router.get("/config")
async def get_config(request: Request, _: None = Depends(_require_admin)):
    cfg = await _cfg(request).load()
    return cfg.model_dump(by_alias=True)


@router.patch("/config")
async def patch_config(
    request: Request,
    body: dict[str, Any],
    _: None = Depends(_require_admin),
):
    updated = await _cfg(request).patch(body)
    scheduler = _scheduler(request)
    if scheduler is not None:
        await scheduler.refresh(force_recompute=True)
    return updated.model_dump(by_alias=True)


# -- workflow ---------------------------------------------------------------

@router.post("/workflow/run")
async def trigger_run(request: Request, _: None = Depends(_require_admin)):
    """Kick off a pipeline run in the background and return immediately."""
    return await _run_manager(request).start_run("manual")


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

        const es = new EventSource('/api/logs/stream')
        es.onmessage = (e) => handleEvent(JSON.parse(e.data))
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
    scheduler = _scheduler(request).snapshot() if _scheduler(request) else None
    return {
        "processed_items_count": db.count(),
        "event_buffer_size": bus.total,
        "active_runs": _run_manager(request).active_runs_count(),
        "scheduler_enabled": scheduler.enabled if scheduler else False,
        "schedule_cron": scheduler.cron if scheduler else "",
        "timezone": scheduler.timezone if scheduler else "UTC",
        "next_run_at": scheduler.next_run_at if scheduler else None,
        "last_run_started_at": scheduler.last_run_started_at if scheduler else None,
        "last_run_finished_at": scheduler.last_run_finished_at if scheduler else None,
        "last_run_status": scheduler.last_run_status if scheduler else None,
        "last_run_reason": scheduler.last_run_reason if scheduler else None,
        "active_run_id": scheduler.active_run_id if scheduler else None,
        "admin_token_required": bool(os.environ.get("OMNIFLOW_ADMIN_TOKEN", "").strip()),
    }


# -- items ------------------------------------------------------------------

@router.get("/items")
async def get_items(request: Request, limit: int = 50):
    return _db(request).recent_items(limit)


@router.get("/runs")
async def get_runs(request: Request, limit: int = 20):
    return _runtime_state_db(request).recent_runs(limit)


# -- plugin discovery -------------------------------------------------------

@router.get("/plugins/discover")
async def discover_plugins(request: Request):
    """Return manifests for all plugins defined in config.

    The frontend uses this to render the plugin store with config schemas.
    """
    cfg = await _cfg(request).load()
    return PluginRegistry.discover_manifests(cfg.plugins)


@router.get("/prompt/soul")
async def get_soul_prompt(_: None = Depends(_require_admin)):
    if DEFAULT_SOUL_PATH.exists():
        content = DEFAULT_SOUL_PATH.read_text(encoding="utf-8")
    else:
        content = ""
    return {"content": content}


@router.patch("/prompt/soul")
async def patch_soul_prompt(
    body: dict[str, Any],
    _: None = Depends(_require_admin),
):
    content = str(body.get("content", ""))
    DEFAULT_SOUL_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_SOUL_PATH.write_text(content, encoding="utf-8")
    return {"content": content}

