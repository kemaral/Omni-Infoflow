from __future__ import annotations

from datetime import UTC, datetime

from app.core.scheduler import compute_next_run_utc


def test_compute_next_run_every_six_hours() -> None:
    now = datetime(2026, 4, 13, 10, 5, tzinfo=UTC)
    next_run = compute_next_run_utc("0 */6 * * *", now)
    assert next_run.hour == 12
    assert next_run.minute == 0


def test_compute_next_run_daily_fixed_time() -> None:
    now = datetime(2026, 4, 13, 23, 40, tzinfo=UTC)
    next_run = compute_next_run_utc("15 8 * * *", now)
    assert next_run.day == 14
    assert next_run.hour == 8
    assert next_run.minute == 15


def test_compute_next_run_asia_shanghai() -> None:
    now = datetime(2026, 4, 13, 23, 40, tzinfo=UTC)
    next_run = compute_next_run_utc("0 8 * * *", now, timezone_name="Asia/Shanghai")
    assert next_run.hour == 0
    assert next_run.minute == 0
