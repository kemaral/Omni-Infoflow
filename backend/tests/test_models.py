"""
Test Suite: Core Models & Infrastructure
==========================================
Validates Pydantic models, database dedup behaviour, config I/O,
event bus semantics, and plugin loading.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

# ── Models ─────────────────────────────────────────────────────────────────

from app.models.workflow import NodeEvent, PluginResult, RunContext, WorkflowItem


class TestWorkflowItem:
    def test_default_id_generated(self):
        item = WorkflowItem()
        assert len(item.id) == 32  # hex uuid4

    def test_fields_carry_through(self):
        item = WorkflowItem(
            source_type="rss",
            source_uri="https://example.com/feed",
            title="Test",
            raw_content="<p>Hello</p>",
        )
        assert item.source_type == "rss"
        assert item.raw_content == "<p>Hello</p>"
        assert item.cleaned_text is None  # not yet processed

    def test_artifacts_and_status_bags(self):
        item = WorkflowItem()
        item.artifacts["audio"] = "/tmp/test.mp3"
        item.status["parser"] = "done"
        assert item.artifacts["audio"] == "/tmp/test.mp3"


class TestPluginResult:
    def test_success_result(self):
        item = WorkflowItem(title="X")
        result = PluginResult(success=True, item=item, logs=["ok"])
        assert result.success
        assert result.error is None

    def test_failure_result(self):
        item = WorkflowItem(title="X")
        result = PluginResult(
            success=False, item=item, error="timeout"
        )
        assert not result.success
        assert result.error == "timeout"


class TestNodeEvent:
    def test_event_creation(self):
        evt = NodeEvent(
            run_id="r1",
            item_id="i1",
            step="parser",
            plugin_name="html_cleaner",
            status="success",
            message="cleaned 200 chars",
        )
        assert evt.status == "success"
        assert evt.duration_ms is None


class TestRunContext:
    def test_auto_fields(self):
        ctx = RunContext()
        assert len(ctx.run_id) == 32
        assert ctx.temp_dir == ""
        assert ctx.variables == {}


# ── Database ───────────────────────────────────────────────────────────────

from app.core.database import DedupDatabase


class TestDedupDatabase:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = Path(self._tmpdir) / "test.sqlite"
        self.db = DedupDatabase(self._db_path)
        self.db.init()

    def teardown_method(self):
        self.db.close()
        self._db_path.unlink(missing_ok=True)

    def test_not_duplicate_initially(self):
        assert not self.db.is_duplicate(source_uri="https://example.com/1")

    def test_mark_and_detect_by_uri(self):
        self.db.mark_processed(
            item_id="a1",
            source_uri="https://example.com/1",
        )
        assert self.db.is_duplicate(source_uri="https://example.com/1")

    def test_detect_by_content_hash(self):
        self.db.mark_processed(
            item_id="a2",
            content="Hello world",
        )
        assert self.db.is_duplicate(content="Hello world")
        assert not self.db.is_duplicate(content="Different")

    def test_detect_by_external_id(self):
        self.db.mark_processed(
            item_id="a3",
            external_id="doi:10.1234/test",
        )
        assert self.db.is_duplicate(external_id="doi:10.1234/test")

    def test_recent_items(self):
        self.db.mark_processed(item_id="b1", source_uri="u1")
        self.db.mark_processed(item_id="b2", source_uri="u2")
        items = self.db.recent_items(limit=10)
        assert len(items) == 2

    def test_count(self):
        assert self.db.count() == 0
        self.db.mark_processed(item_id="c1", source_uri="u1")
        assert self.db.count() == 1


# ── Config ─────────────────────────────────────────────────────────────────

from app.core.config import AppConfig, ConfigManager


class TestConfigManager:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._cfg_path = Path(self._tmpdir) / "test_config.json"
        self.mgr = ConfigManager(self._cfg_path)

    def teardown_method(self):
        self._cfg_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_load_creates_default(self):
        # path doesn't exist yet, so load() creates default
        cfg = await self.mgr.load()
        assert isinstance(cfg, AppConfig)
        assert cfg.workflow.max_concurrency == 3

    @pytest.mark.asyncio
    async def test_save_and_reload(self):
        cfg = AppConfig()
        cfg.workflow.max_concurrency = 10
        await self.mgr.save(cfg)
        reloaded = await self.mgr.load(force=True)
        assert reloaded.workflow.max_concurrency == 10

    @pytest.mark.asyncio
    async def test_patch_merges(self):
        # First load creates default config on disk
        await self.mgr.load()
        updated = await self.mgr.patch({"runtime": {"debug": True}})
        assert updated.runtime["debug"] is True


# ── EventBus ───────────────────────────────────────────────────────────────

from app.core.logger import EventBus


class TestEventBus:
    @pytest.mark.asyncio
    async def test_emit_and_recent(self):
        bus = EventBus()
        evt = NodeEvent(
            run_id="r1", item_id="i1", step="s", plugin_name="p", status="success"
        )
        await bus.emit(evt)
        assert bus.total == 1
        assert bus.recent(1)[0].run_id == "r1"

    @pytest.mark.asyncio
    async def test_ring_buffer_cap(self):
        bus = EventBus(max_events=5)
        for i in range(10):
            await bus.emit(
                NodeEvent(
                    run_id=str(i), item_id="i", step="s",
                    plugin_name="p", status="success",
                )
            )
        assert bus.total == 5
        assert bus.recent(10)[0].run_id == "5"  # oldest surviving


# ── Plugin Loading ─────────────────────────────────────────────────────────

from app.core.engine import PluginRegistry


class TestPluginRegistry:
    def test_load_mock_source_class(self):
        cls = PluginRegistry.load_class(
            "tests.plugins.mock_source.MockSourcePlugin"
        )
        assert cls.manifest.name == "mock_source"

    def test_load_invalid_path_raises(self):
        with pytest.raises(ImportError):
            PluginRegistry.load_class("nonexistent.module.Foo")

    def test_instantiate_sources(self):
        configs = [
            {
                "class": "tests.plugins.mock_source.MockSourcePlugin",
                "enabled": True,
                "config": {},
            }
        ]
        instances = PluginRegistry.instantiate_sources(configs)
        assert len(instances) == 1
        assert instances[0].manifest.category == "source"

    def test_disabled_plugin_skipped(self):
        configs = [
            {
                "class": "tests.plugins.mock_source.MockSourcePlugin",
                "enabled": False,
                "config": {},
            }
        ]
        instances = PluginRegistry.instantiate_sources(configs)
        assert len(instances) == 0
