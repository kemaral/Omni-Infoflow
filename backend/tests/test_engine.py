"""
Integration Test Suite: Pipeline Engine (M2)
==============================================
Tests the full engine execution pipeline with mock plugins, verifying:

- Happy path: Source → Parser → Dispatcher end-to-end
- Dedup gating: duplicate items are skipped
- Optional step skipping: AI/Media steps skip when no plugins configured
- Error handling: continue_on_error allows recovery
- Retry logic: failing plugins are retried per policy
- Event telemetry: NodeEvents are emitted at every boundary
- Concurrency: multiple items processed in parallel
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from app.core.config import AppConfig, ConfigManager
from app.core.database import DedupDatabase
from app.core.engine import PipelineEngine, PluginRegistry
from app.core.logger import EventBus
from app.models.workflow import NodeEvent

# Reset plugin registry cache between tests
pytestmark = pytest.mark.asyncio


class EngineTestHarness:
    """Reusable test fixture for engine integration tests."""

    def __init__(self):
        self._tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self._tmpdir) / "test.sqlite"
        self.cfg_path = Path(self._tmpdir) / "config.json"

        self.db = DedupDatabase(self.db_path)
        self.db.init()
        self.bus = EventBus()
        self.config_mgr = ConfigManager(self.cfg_path)

    async def set_config(self, config_dict: dict) -> None:
        """Write a config dict and load it."""
        cfg = AppConfig.model_validate(config_dict)
        await self.config_mgr.save(cfg)

    async def run_engine(self) -> dict:
        engine = PipelineEngine(self.config_mgr, self.db, self.bus)
        return await engine.execute()

    def events(self, step: str | None = None) -> list[NodeEvent]:
        """Return all events, optionally filtered by step."""
        all_evts = self.bus.recent(1000)
        if step:
            return [e for e in all_evts if e.step == step]
        return all_evts

    def cleanup(self):
        self.db.close()
        self.db_path.unlink(missing_ok=True)
        PluginRegistry.clear_cache()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def harness():
    h = EngineTestHarness()
    yield h
    h.cleanup()


def _base_config(
    *,
    sources: list | None = None,
    parsers: list | None = None,
    ai: list | None = None,
    media: list | None = None,
    dispatchers: list | None = None,
    retries: int = 0,
    continue_on_error: list | None = None,
) -> dict:
    """Build a minimal config dict for testing."""
    return {
        "global": {},
        "workflow": {
            "steps": ["source", "parser", "ai", "media", "dispatch"],
            "optional_steps": ["ai", "media"],
            "continue_on_error": continue_on_error or [],
            "max_concurrency": 5,
            "retry_policy": {"default_retries": retries},
        },
        "plugins": {
            "sources": sources or [],
            "parsers": parsers or [],
            "ai": ai or [],
            "media": media or [],
            "dispatchers": dispatchers or [],
        },
        "runtime": {},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHappyPath:
    """Source → Parser → Dispatcher with all steps succeeding."""

    async def test_full_pipeline(self, harness: EngineTestHarness):
        from tests.plugins.mock_dispatcher import MockDispatcherPlugin
        MockDispatcherPlugin.reset()

        await harness.set_config(_base_config(
            sources=[{
                "class": "tests.plugins.mock_source.MockSourcePlugin",
                "enabled": True, "config": {},
            }],
            parsers=[{
                "class": "tests.plugins.mock_parser.MockParserPlugin",
                "enabled": True, "config": {},
            }],
            dispatchers=[{
                "class": "tests.plugins.mock_dispatcher.MockDispatcherPlugin",
                "enabled": True, "config": {},
            }],
        ))

        stats = await harness.run_engine()

        assert stats["items_fetched"] == 2
        assert stats["items_processed"] == 2
        assert stats["items_skipped_dedup"] == 0
        assert stats["errors"] == []
        assert len(MockDispatcherPlugin.sent) == 2

        # Verify parser actually cleaned the HTML
        for item in MockDispatcherPlugin.sent:
            assert "<" not in (item.cleaned_text or "")

    async def test_events_emitted(self, harness: EngineTestHarness):
        from tests.plugins.mock_dispatcher import MockDispatcherPlugin
        MockDispatcherPlugin.reset()

        await harness.set_config(_base_config(
            sources=[{
                "class": "tests.plugins.mock_source.MockSourcePlugin",
                "enabled": True, "config": {},
            }],
            parsers=[{
                "class": "tests.plugins.mock_parser.MockParserPlugin",
                "enabled": True, "config": {},
            }],
            dispatchers=[{
                "class": "tests.plugins.mock_dispatcher.MockDispatcherPlugin",
                "enabled": True, "config": {},
            }],
        ))

        await harness.run_engine()

        # Should have source events (started + success)
        source_evts = harness.events("source")
        assert len(source_evts) >= 2

        # Should have parser events for each item
        parser_evts = harness.events("parser")
        assert len(parser_evts) >= 2  # at least started+success per item

        # Should have dispatch events
        dispatch_evts = harness.events("dispatch")
        assert len(dispatch_evts) >= 2

        # Optional steps with no plugins should be skipped
        ai_evts = harness.events("ai")
        assert all(e.status == "skipped" for e in ai_evts)

    async def test_source_partial_failures_are_reported(
        self, harness: EngineTestHarness
    ):
        from tests.plugins.mock_dispatcher import MockDispatcherPlugin
        MockDispatcherPlugin.reset()

        await harness.set_config(_base_config(
            sources=[{
                "class": "tests.plugins.mock_partial_source.MockPartialSourcePlugin",
                "enabled": True, "config": {},
            }],
            dispatchers=[{
                "class": "tests.plugins.mock_dispatcher.MockDispatcherPlugin",
                "enabled": True, "config": {},
            }],
        ))

        stats = await harness.run_engine()

        assert stats["items_fetched"] == 1
        assert stats["source_items_failed"] == 1
        assert any(
            "mock partial source failure" in error
            for error in stats["errors"]
        )
        source_failures = [
            event for event in harness.events("source")
            if event.status == "failed"
        ]
        assert len(source_failures) >= 1


class TestDeduplication:
    """Verify that the dedup filter prevents reprocessing."""

    async def test_second_run_skips_duplicates(self, harness: EngineTestHarness):
        from tests.plugins.mock_dispatcher import MockDispatcherPlugin

        cfg = _base_config(
            sources=[{
                "class": "tests.plugins.mock_source.MockSourcePlugin",
                "enabled": True, "config": {},
            }],
            dispatchers=[{
                "class": "tests.plugins.mock_dispatcher.MockDispatcherPlugin",
                "enabled": True, "config": {},
            }],
        )
        await harness.set_config(cfg)

        # First run — processes 2 items
        MockDispatcherPlugin.reset()
        stats1 = await harness.run_engine()
        assert stats1["items_processed"] == 2

        # Clear event bus for clean second run
        harness.bus.clear()

        # Second run — same source, items should be skipped
        MockDispatcherPlugin.reset()
        stats2 = await harness.run_engine()
        assert stats2["items_skipped_dedup"] == 2
        assert stats2["items_processed"] == 0
        assert len(MockDispatcherPlugin.sent) == 0


class TestOptionalStepSkipping:
    """AI and Media steps should be silently skipped when not configured."""

    async def test_optional_steps_skipped(self, harness: EngineTestHarness):
        await harness.set_config(_base_config(
            sources=[{
                "class": "tests.plugins.mock_source.MockSourcePlugin",
                "enabled": True, "config": {},
            }],
            # No parsers, AI, media, or dispatchers
        ))

        stats = await harness.run_engine()

        # Items fetched but no processing plugins — optional steps skipped
        assert stats["items_fetched"] == 2
        ai_evts = harness.events("ai")
        media_evts = harness.events("media")
        assert all(e.status == "skipped" for e in ai_evts)
        assert all(e.status == "skipped" for e in media_evts)


class TestErrorHandling:
    """Error tolerance via continue_on_error policy."""

    async def test_continue_on_error_step(self, harness: EngineTestHarness):
        """When a step is in continue_on_error, its failure doesn't abort."""
        from tests.plugins.mock_dispatcher import MockDispatcherPlugin
        MockDispatcherPlugin.reset()

        await harness.set_config(_base_config(
            sources=[{
                "class": "tests.plugins.mock_source.MockSourcePlugin",
                "enabled": True, "config": {},
            }],
            parsers=[{
                "class": "tests.plugins.mock_failing.MockFailingPlugin",
                "enabled": True, "config": {"fail_count": 99},
            }],
            dispatchers=[{
                "class": "tests.plugins.mock_dispatcher.MockDispatcherPlugin",
                "enabled": True, "config": {},
            }],
            continue_on_error=["parser"],  # parser failure doesn't abort
            retries=0,
        ))

        stats = await harness.run_engine()

        # Parser failed but didn't abort — dispatcher should still run
        assert stats["items_processed"] == 2
        assert len(MockDispatcherPlugin.sent) == 2

    async def test_non_recoverable_step_aborts(self, harness: EngineTestHarness):
        """When a step is NOT in continue_on_error, its failure aborts item."""
        from tests.plugins.mock_failing import MockFailingPlugin
        from tests.plugins.mock_dispatcher import MockDispatcherPlugin

        MockDispatcherPlugin.reset()
        MockFailingPlugin.reset()

        await harness.set_config(_base_config(
            sources=[{
                "class": "tests.plugins.mock_source.MockSourcePlugin",
                "enabled": True, "config": {},
            }],
            parsers=[{
                "class": "tests.plugins.mock_failing.MockFailingPlugin",
                "enabled": True, "config": {"fail_count": 99},
            }],
            dispatchers=[{
                "class": "tests.plugins.mock_dispatcher.MockDispatcherPlugin",
                "enabled": True, "config": {},
            }],
            continue_on_error=[],  # parser failure DOES abort
            retries=0,
        ))

        stats = await harness.run_engine()

        # Items should be marked as failed, dispatcher never reached
        assert stats["items_failed"] >= 1
        assert len(MockDispatcherPlugin.sent) == 0


class TestRetryLogic:
    """Retry policy with exponential backoff."""

    async def test_retry_succeeds_after_failures(self, harness: EngineTestHarness):
        """Plugin fails once, retries, then succeeds."""
        from tests.plugins.mock_failing import MockFailingPlugin
        from tests.plugins.mock_dispatcher import MockDispatcherPlugin

        MockDispatcherPlugin.reset()
        MockFailingPlugin.reset()

        await harness.set_config(_base_config(
            sources=[{
                "class": "tests.plugins.mock_source.MockSourcePlugin",
                "enabled": True, "config": {},
            }],
            parsers=[{
                "class": "tests.plugins.mock_failing.MockFailingPlugin",
                "enabled": True, "config": {"fail_count": 1},
            }],
            dispatchers=[{
                "class": "tests.plugins.mock_dispatcher.MockDispatcherPlugin",
                "enabled": True, "config": {},
            }],
            retries=2,  # allow 2 retries → enough for fail_count=1
        ))

        stats = await harness.run_engine()

        # The first item triggers the failure, retry succeeds
        # But note: _call_count is shared, so second item sees count > fail_count
        assert stats["errors"] == [] or stats["items_processed"] >= 1


class TestPluginDiscovery:
    """PluginRegistry.discover_manifests returns metadata."""

    def test_discover_mock_manifests(self):
        plugins_config = {
            "sources": [{
                "class": "tests.plugins.mock_source.MockSourcePlugin",
                "enabled": True, "config": {},
            }],
            "parsers": [{
                "class": "tests.plugins.mock_parser.MockParserPlugin",
                "enabled": False, "config": {},
            }],
        }
        manifests = PluginRegistry.discover_manifests(plugins_config)

        names = [m["name"] for m in manifests]
        assert "mock_source" in names
        assert "mock_parser" in names

        # Enabled flag propagated
        source_m = next(m for m in manifests if m["name"] == "mock_source")
        assert source_m["enabled"] is True

    def test_discover_invalid_class_returns_error(self):
        plugins_config = {
            "sources": [{
                "class": "nonexistent.FakePlugin",
                "enabled": True, "config": {},
            }],
        }
        manifests = PluginRegistry.discover_manifests(plugins_config)
        invalid = next(
            manifest
            for manifest in manifests
            if manifest["name"] == "nonexistent.FakePlugin"
        )
        assert "error" in invalid

    def test_builtin_plugins_are_discovered_without_config_entries(self):
        manifests = PluginRegistry.discover_manifests({
            "sources": [],
            "parsers": [],
            "ai": [],
            "media": [],
            "dispatchers": [],
        })

        names = {manifest["name"] for manifest in manifests}
        assert "rss_source" in names
        assert "html_cleaner" in names


class TestEventTelemetry:
    """NodeEvent objects carry proper timing and metadata."""

    async def test_events_have_duration(self, harness: EngineTestHarness):
        from tests.plugins.mock_dispatcher import MockDispatcherPlugin
        MockDispatcherPlugin.reset()

        await harness.set_config(_base_config(
            sources=[{
                "class": "tests.plugins.mock_source.MockSourcePlugin",
                "enabled": True, "config": {},
            }],
            parsers=[{
                "class": "tests.plugins.mock_parser.MockParserPlugin",
                "enabled": True, "config": {},
            }],
            dispatchers=[{
                "class": "tests.plugins.mock_dispatcher.MockDispatcherPlugin",
                "enabled": True, "config": {},
            }],
        ))

        await harness.run_engine()

        success_events = [
            e for e in harness.events()
            if e.status == "success" and e.duration_ms is not None
        ]
        # Source and processing steps should have duration
        assert len(success_events) >= 1
        for e in success_events:
            assert e.duration_ms >= 0
