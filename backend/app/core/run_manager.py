from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request, status

from app.core.config import ConfigManager
from app.core.database import DedupDatabase
from app.core.engine import PipelineEngine
from app.core.logger import EventBus
from app.core.scheduler import SchedulerService


class RunManager:
    def __init__(
        self,
        config_manager: ConfigManager,
        dedup_db: DedupDatabase,
        state_db: DedupDatabase,
        event_bus: EventBus,
        scheduler: SchedulerService | None = None,
    ) -> None:
        self._config_manager = config_manager
        self._dedup_db = dedup_db
        self._state_db = state_db
        self._event_bus = event_bus
        self._scheduler = scheduler
        self._active_runs: dict[str, asyncio.Task] = {}

    def bind_scheduler(self, scheduler: SchedulerService) -> None:
        self._scheduler = scheduler

    def active_runs_count(self) -> int:
        return len(self._active_runs)

    async def start_run(self, trigger: str) -> dict[str, Any]:
        scheduler_state = self._state_db.get_scheduler_state() or {}
        active_run_id = scheduler_state.get("active_run_id")
        if active_run_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A workflow run is already in progress",
            )

        engine = PipelineEngine(
            config=self._config_manager,
            db=self._dedup_db,
            bus=self._event_bus,
        )

        task_id = str(datetime.now(UTC).timestamp()).replace(".", "")
        task = asyncio.create_task(self._run_task(task_id, trigger, engine, scheduler_state))
        self._active_runs[task_id] = task
        task.add_done_callback(lambda _done: self._active_runs.pop(task_id, None))
        return {"message": "Pipeline run started", "task_id": task_id, "trigger": trigger}

    async def _run_task(
        self,
        task_id: str,
        trigger: str,
        engine: PipelineEngine,
        scheduler_state: dict[str, Any],
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC).isoformat()
        self._state_db.upsert_scheduler_state(
            enabled=scheduler_state.get("enabled", False),
            cron=scheduler_state.get("cron", ""),
            timezone=scheduler_state.get("timezone", "UTC"),
            next_run_at=scheduler_state.get("next_run_at"),
            active_run_id=task_id,
            last_run_started_at=started_at,
            last_run_finished_at=scheduler_state.get("last_run_finished_at"),
            last_run_status="running",
            last_run_reason=trigger,
            scheduler_error=scheduler_state.get("scheduler_error"),
        )

        try:
            result = await engine.execute()
            await self._record_success(task_id, trigger, started_at, result)
            result["trigger"] = trigger
            return result
        except Exception as exc:
            await self._record_failure(task_id, trigger, started_at, str(exc))
            raise

    async def _record_success(
        self,
        task_id: str,
        trigger: str,
        started_at: str,
        result: dict[str, Any],
    ) -> None:
        finished_at = datetime.now(UTC).isoformat()
        refreshed = await self._refresh_scheduler()
        self._state_db.upsert_scheduler_state(
            enabled=refreshed.get("enabled", False),
            cron=refreshed.get("cron", ""),
            timezone=refreshed.get("timezone", "UTC"),
            next_run_at=refreshed.get("next_run_at"),
            active_run_id="",
            last_run_started_at=started_at,
            last_run_finished_at=finished_at,
            last_run_status="success",
            last_run_reason="",
            scheduler_error=refreshed.get("scheduler_error"),
        )
        self._state_db.record_run_history(
            run_id=result.get("run_id", task_id),
            trigger=trigger,
            status="success",
            reason="",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=result.get("duration_ms"),
            items_fetched=result.get("items_fetched", 0),
            items_processed=result.get("items_processed", 0),
            items_skipped_dedup=result.get("items_skipped_dedup", 0),
            items_failed=result.get("items_failed", 0),
        )

    async def _record_failure(
        self,
        task_id: str,
        trigger: str,
        started_at: str,
        reason: str,
    ) -> None:
        finished_at = datetime.now(UTC).isoformat()
        refreshed = await self._refresh_scheduler()
        self._state_db.upsert_scheduler_state(
            enabled=refreshed.get("enabled", False),
            cron=refreshed.get("cron", ""),
            timezone=refreshed.get("timezone", "UTC"),
            next_run_at=refreshed.get("next_run_at"),
            active_run_id="",
            last_run_started_at=started_at,
            last_run_finished_at=finished_at,
            last_run_status="failed",
            last_run_reason=reason,
            scheduler_error=refreshed.get("scheduler_error"),
        )
        self._state_db.record_run_history(
            run_id=task_id,
            trigger=trigger,
            status="failed",
            reason=reason,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=None,
            items_fetched=0,
            items_processed=0,
            items_skipped_dedup=0,
            items_failed=1,
        )

    async def _refresh_scheduler(self) -> dict[str, Any]:
        if self._scheduler is None:
            return self._state_db.get_scheduler_state() or {}
        await self._scheduler.refresh(force_recompute=True)
        snapshot = self._scheduler.snapshot()
        return {
            "enabled": snapshot.enabled,
            "cron": snapshot.cron,
            "timezone": snapshot.timezone,
            "next_run_at": snapshot.next_run_at,
            "scheduler_error": snapshot.scheduler_error,
        }


async def get_run_manager(request: Request) -> RunManager:
    return request.app.state.run_manager
