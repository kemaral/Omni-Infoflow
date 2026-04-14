from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import ConfigManager
from app.core.database import DedupDatabase


@dataclass
class SchedulerSnapshot:
    enabled: bool
    cron: str
    timezone: str
    next_run_at: str | None
    last_run_started_at: str | None
    last_run_finished_at: str | None
    last_run_status: str | None
    last_run_reason: str | None
    active_run_id: str | None
    scheduler_error: str | None


class SchedulerService:
    def __init__(
        self,
        config_manager: ConfigManager,
        state_db: DedupDatabase,
        trigger_run: Callable[[str], Awaitable[dict]],
    ) -> None:
        self._config_manager = config_manager
        self._state_db = state_db
        self._trigger_run = trigger_run
        self._task: asyncio.Task | None = None
        self._wake_event = asyncio.Event()

    async def start(self) -> None:
        self._recover_interrupted_run()
        await self.refresh(force_recompute=True)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def _recover_interrupted_run(self) -> None:
        state = self._state_db.get_scheduler_state() or {}
        active_run_id = state.get("active_run_id")
        if not active_run_id:
            return

        finished_at = datetime.now(UTC).isoformat()
        self._state_db.upsert_scheduler_state(
            enabled=bool(state.get("enabled", False)),
            cron=state.get("cron", ""),
            timezone=state.get("timezone", "UTC"),
            next_run_at=state.get("next_run_at"),
            active_run_id="",
            last_run_started_at=state.get("last_run_started_at"),
            last_run_finished_at=finished_at,
            last_run_status="interrupted",
            last_run_reason="Previous run interrupted by service restart",
            scheduler_error=state.get("scheduler_error"),
        )
        self._state_db.record_run_history(
            run_id=str(active_run_id),
            trigger="recovery",
            status="interrupted",
            reason="Previous run interrupted by service restart",
            started_at=state.get("last_run_started_at"),
            finished_at=finished_at,
            duration_ms=None,
            items_fetched=0,
            items_processed=0,
            items_skipped_dedup=0,
            items_failed=1,
        )

    async def refresh(self, *, force_recompute: bool = False) -> SchedulerSnapshot:
        runtime = await self._load_runtime_settings(force_recompute)
        state = self._calculate_scheduler_state(runtime)
        self._state_db.upsert_scheduler_state(**state)
        self._wake_event.set()
        return self.snapshot()

    def snapshot(self) -> SchedulerSnapshot:
        state = self._state_db.get_scheduler_state()
        if not state:
            return SchedulerSnapshot(False, "", "UTC", None, None, None, None, None, None, None)
        return SchedulerSnapshot(
            enabled=bool(state.get("enabled")),
            cron=state.get("cron") or "",
            timezone=state.get("timezone") or "UTC",
            next_run_at=state.get("next_run_at"),
            last_run_started_at=state.get("last_run_started_at"),
            last_run_finished_at=state.get("last_run_finished_at"),
            last_run_status=state.get("last_run_status"),
            last_run_reason=state.get("last_run_reason"),
            active_run_id=state.get("active_run_id"),
            scheduler_error=state.get("scheduler_error"),
        )

    async def _load_runtime_settings(self, force_recompute: bool) -> dict[str, Any]:
        cfg = await self._config_manager.load(force=force_recompute)
        runtime = cfg.runtime or {}
        return {
            "enabled": bool(runtime.get("scheduler_enabled", False)),
            "cron": str(runtime.get("schedule_cron", "")).strip(),
            "timezone": str(runtime.get("timezone", "UTC")).strip() or "UTC",
        }

    def _calculate_scheduler_state(self, runtime: dict[str, Any]) -> dict[str, Any]:
        snapshot = self._state_db.get_scheduler_state() or {}
        enabled = bool(runtime["enabled"]) and bool(runtime["cron"])
        next_run_at: str | None = snapshot.get("next_run_at")
        scheduler_error = snapshot.get("scheduler_error")

        if enabled:
            try:
                next_run_at = compute_next_run_utc(
                    runtime["cron"],
                    timezone_name=runtime["timezone"],
                ).isoformat()
                scheduler_error = None
            except ValueError as exc:
                next_run_at = None
                scheduler_error = str(exc)
        else:
            next_run_at = None
            scheduler_error = None

        return {
            "enabled": enabled,
            "cron": runtime["cron"],
            "timezone": runtime["timezone"],
            "next_run_at": next_run_at,
            "active_run_id": snapshot.get("active_run_id"),
            "last_run_started_at": snapshot.get("last_run_started_at"),
            "last_run_finished_at": snapshot.get("last_run_finished_at"),
            "last_run_status": snapshot.get("last_run_status"),
            "last_run_reason": snapshot.get("last_run_reason"),
            "scheduler_error": scheduler_error,
        }

    async def _loop(self) -> None:
        while True:
            snapshot = self.snapshot()
            if not snapshot.enabled or not snapshot.next_run_at:
                await self._wake_event.wait()
                self._wake_event.clear()
                continue

            next_run = datetime.fromisoformat(snapshot.next_run_at)
            delay = max(0.0, (next_run - datetime.now(UTC)).total_seconds())
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=delay)
                self._wake_event.clear()
                continue
            except asyncio.TimeoutError:
                pass

            current = self.snapshot()
            if current.active_run_id:
                next_dt = (
                    compute_next_run_utc(
                        current.cron,
                        timezone_name=current.timezone,
                    )
                    if current.cron
                    else None
                )
                self._state_db.upsert_scheduler_state(
                    enabled=current.enabled,
                    cron=current.cron,
                    timezone=current.timezone,
                    next_run_at=next_dt.isoformat() if next_dt else None,
                )
                continue

            await self._trigger_run("scheduled")
            refreshed = await self.refresh(force_recompute=True)
            if not refreshed.enabled:
                self._wake_event.clear()


def compute_next_run_utc(
    cron_expr: str,
    now: datetime | None = None,
    timezone_name: str = "UTC",
) -> datetime:
    tz = _resolve_timezone(timezone_name)
    base_utc = (now or datetime.now(UTC)).astimezone(UTC)
    base_local = (
        base_utc.astimezone(tz).replace(second=0, microsecond=0)
        + timedelta(minutes=1)
    )
    minute_expr, hour_expr, dom_expr, month_expr, dow_expr = cron_expr.split()

    for offset in range(0, 366 * 24 * 60):
        candidate_local = base_local + timedelta(minutes=offset)
        if _matches(candidate_local.minute, minute_expr, 0, 59) and _matches(candidate_local.hour, hour_expr, 0, 23):
            if _matches(candidate_local.day, dom_expr, 1, 31) and _matches(candidate_local.month, month_expr, 1, 12):
                cron_dow = (candidate_local.weekday() + 1) % 7
                if _matches(cron_dow, dow_expr, 0, 6):
                    return candidate_local.astimezone(UTC)

    raise ValueError(f"Unable to compute next run for cron: {cron_expr}")



def _resolve_timezone(timezone_name: str):
    normalized = (timezone_name or "UTC").strip()
    if normalized.upper() == "UTC":
        return UTC
    if normalized in {"Asia/Shanghai", "Asia/Chongqing"}:
        return timezone(timedelta(hours=8), name=normalized)
    try:
        return ZoneInfo(normalized)
    except ZoneInfoNotFoundError:
        return UTC


def _matches(value: int, expr: str, min_value: int, max_value: int) -> bool:
    expr = expr.strip()
    if expr == "*":
        return True
    if expr.startswith("*/"):
        step = int(expr[2:])
        return (value - min_value) % step == 0

    parts = expr.split(",")
    for part in parts:
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            if int(start) <= value <= int(end):
                return True
        elif part and int(part) == value:
            return True
    return False
