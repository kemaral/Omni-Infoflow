"""
Pipeline Engine (Orchestrator) — v2 (Milestone 2)
===================================================
Full-featured execution engine with:

  - **Plugin auto-discovery**: scans config *and* discovers manifests
  - **Retry policy**: configurable per-step retries with backoff
  - **Concurrency control**: ``asyncio.Semaphore`` caps parallel items
  - **Optional step skipping**: based on ``WorkflowPolicy.optional_steps``
  - **Error tolerance**: ``continue_on_error`` steps don't abort the run
  - **Timing telemetry**: ``duration_ms`` on every ``NodeEvent``
  - **Run lifecycle**: start → items → dedup → pipeline → mark complete

Flow::

    Source.fetch  →  dedup  →  Parser.run  →  (AI.run)  →  (Media.run)
        →  Dispatcher.run
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.config import ConfigManager, WorkflowPolicy
from app.core.database import DedupDatabase
from app.core.logger import EventBus
from app.models.workflow import NodeEvent, PluginResult, RunContext, WorkflowItem
from app.plugins.base import BasePlugin, BaseSourcePlugin, PluginManifest

log = logging.getLogger("omniflow.engine")


# ---------------------------------------------------------------------------
# Plugin Registry — discover & instantiate plugins from config
# ---------------------------------------------------------------------------

class PluginRegistry:
    """Resolves dotted Python paths to plugin instances.

    Each entry in ``config.plugins.<category>`` looks like::

        {
            "class": "app.plugins.sources.rss.RSSPlugin",
            "enabled": true,
            "config": { ... }
        }
    """

    # -- class cache so repeated instantiation doesn't re-import -----------
    _class_cache: dict[str, type] = {}

    @classmethod
    def load_class(cls, dotted_path: str) -> type:
        """Import a class from its fully-qualified dotted name (cached)."""
        if dotted_path in cls._class_cache:
            return cls._class_cache[dotted_path]

        module_path, _, class_name = dotted_path.rpartition(".")
        if not module_path:
            raise ImportError(f"Invalid plugin path: {dotted_path}")
        module = importlib.import_module(module_path)
        klass = getattr(module, class_name, None)
        if klass is None:
            raise ImportError(
                f"Class '{class_name}' not found in module '{module_path}'"
            )
        cls._class_cache[dotted_path] = klass
        return klass

    @classmethod
    def instantiate_sources(
        cls, configs: list[dict[str, Any]]
    ) -> list[BaseSourcePlugin]:
        """Create enabled source plugin instances."""
        instances: list[BaseSourcePlugin] = []
        for entry in configs:
            if not entry.get("enabled", False):
                continue
            try:
                klass = cls.load_class(entry["class"])
                instances.append(klass(entry.get("config", {})))
            except ImportError as exc:
                log.warning("Failed to load source plugin %s: %s",
                            entry.get("class"), exc)
        return instances

    @classmethod
    def instantiate_processors(
        cls, configs: list[dict[str, Any]]
    ) -> list[BasePlugin]:
        """Create enabled processing plugin instances."""
        instances: list[BasePlugin] = []
        for entry in configs:
            if not entry.get("enabled", False):
                continue
            try:
                klass = cls.load_class(entry["class"])
                instances.append(klass(entry.get("config", {})))
            except ImportError as exc:
                log.warning("Failed to load plugin %s: %s",
                            entry.get("class"), exc)
        return instances

    @classmethod
    def discover_manifests(
        cls, configs: dict[str, list[dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        """Return manifest metadata for every discoverable plugin.

        Used by the frontend to render the plugin store cards.
        """
        manifests: list[dict[str, Any]] = []
        for category, entries in configs.items():
            for entry in entries:
                try:
                    klass = cls.load_class(entry["class"])
                    manifest: PluginManifest = klass.manifest
                    manifests.append({
                        **manifest.model_dump(),
                        "class": entry["class"],
                        "enabled": entry.get("enabled", False),
                    })
                except Exception as exc:
                    manifests.append({
                        "name": entry.get("class", "unknown"),
                        "category": category.rstrip("s"),
                        "error": str(exc),
                        "enabled": False,
                    })
        return manifests

    @classmethod
    def clear_cache(cls) -> None:
        cls._class_cache.clear()


# ---------------------------------------------------------------------------
# PipelineEngine — main orchestrator (v2)
# ---------------------------------------------------------------------------

@dataclass
class ExecutionState:
    cfg: Any
    context: RunContext
    policy: WorkflowPolicy
    stats: dict[str, Any]
    step_categories: list[str]


class PipelineEngine:
    """Coordinates a single workflow run with retry, concurrency, and telemetry.

    Usage::

        engine = PipelineEngine(config_mgr, dedup_db, event_bus)
        summary = await engine.execute()
    """

    def __init__(
        self,
        config: ConfigManager,
        db: DedupDatabase,
        bus: EventBus,
    ) -> None:
        self.config = config
        self.db = db
        self.bus = bus

    async def execute(self) -> dict[str, Any]:
        """Run the full pipeline once and return a summary dict."""
        run_start = time.monotonic()
        state = await self._build_execution_state()
        all_items = await self._fetch_source_items(state)
        unique_items = await self._filter_unique_items(all_items, state)
        await self._process_items(unique_items, state)
        state.stats["duration_ms"] = int((time.monotonic() - run_start) * 1000)
        log.info("Run %s complete: %s", state.context.run_id, state.stats)
        return state.stats

    async def _build_execution_state(self) -> ExecutionState:
        cfg = await self.config.load()
        run_id = uuid.uuid4().hex
        context = RunContext(
            run_id=run_id,
            config_snapshot=cfg.model_dump(by_alias=True),
            started_at=datetime.now(timezone.utc),
            temp_dir=tempfile.mkdtemp(prefix=f"omniflow-{run_id[:8]}-"),
        )
        stats: dict[str, Any] = {
            "run_id": run_id,
            "items_fetched": 0,
            "items_processed": 0,
            "items_skipped_dedup": 0,
            "items_failed": 0,
            "errors": [],
            "duration_ms": 0,
        }
        return ExecutionState(
            cfg=cfg,
            context=context,
            policy=cfg.workflow,
            stats=stats,
            step_categories=[s for s in cfg.workflow.steps if s != "source"],
        )

    async def _fetch_source_items(self, state: ExecutionState) -> list[WorkflowItem]:
        sources = PluginRegistry.instantiate_sources(
            state.cfg.plugins.get("sources", [])
        )
        items: list[WorkflowItem] = []
        for src in sources:
            items.extend(await self._run_source_with_retry(src, state))
        state.stats["items_fetched"] = len(items)
        return items

    async def _filter_unique_items(
        self,
        all_items: list[WorkflowItem],
        state: ExecutionState,
    ) -> list[WorkflowItem]:
        unique_items: list[WorkflowItem] = []
        for item in all_items:
            if self.db.is_duplicate(
                source_uri=item.source_uri,
                content=item.raw_content or "",
                external_id=item.metadata.get("external_id"),
            ):
                state.stats["items_skipped_dedup"] += 1
                await self._emit(
                    state.context,
                    item.id,
                    "dedup",
                    "dedup",
                    "skipped",
                    message=f"Duplicate: {item.title or item.source_uri}",
                )
                continue
            unique_items.append(item)
        return unique_items

    async def _process_items(
        self,
        items: list[WorkflowItem],
        state: ExecutionState,
    ) -> None:
        semaphore = asyncio.Semaphore(max(1, state.policy.max_concurrency))

        async def process_item(item: WorkflowItem) -> bool:
            async with semaphore:
                return await self._process_single_item(item, state)

        results = await asyncio.gather(
            *(process_item(item) for item in items),
            return_exceptions=True,
        )

        for index, result in enumerate(results):
            if isinstance(result, Exception):
                state.stats["errors"].append(
                    f"item/{items[index].id}: unhandled {result}"
                )
                state.stats["items_failed"] += 1

    # -- item-level pipeline ------------------------------------------------

    async def _process_single_item(
        self,
        item: WorkflowItem,
        state: ExecutionState,
    ) -> bool:
        """Run one item through the full processing pipeline."""
        item_failed = False

        for step in state.step_categories:
            category_key = self._category_key(step)
            plugins = PluginRegistry.instantiate_processors(
                state.cfg.plugins.get(category_key, [])
            )

            if not plugins:
                if await self._handle_missing_plugins(item, step, state):
                    continue

            for plugin in plugins:
                success = await self._run_plugin_with_retry(
                    plugin, item, step, state
                )
                if success:
                    continue
                if step not in state.policy.continue_on_error:
                    item_failed = True
                    break

            if item_failed:
                break

        # Mark item complete in dedup db (even if partially failed)
        self.db.mark_processed(
            item_id=item.id,
            source_type=item.source_type,
            source_uri=item.source_uri,
            content=item.cleaned_text or item.raw_content or "",
            external_id=item.metadata.get("external_id"),
            title=item.title,
            status="failed" if item_failed else "completed",
        )

        if item_failed:
            state.stats["items_failed"] = state.stats.get("items_failed", 0) + 1
        else:
            state.stats["items_processed"] += 1

        return not item_failed

    # -- retry wrappers -----------------------------------------------------

    async def _handle_missing_plugins(
        self,
        item: WorkflowItem,
        step: str,
        state: ExecutionState,
    ) -> bool:
        if step in state.policy.optional_steps:
            await self._emit(
                state.context,
                item.id,
                "engine",
                step,
                "skipped",
                message="No plugins configured (optional step)",
            )
            return True

        await self._emit(
            state.context,
            item.id,
            "engine",
            step,
            "skipped",
            message="No plugins configured (mandatory step — check config)",
        )
        return True

    async def _run_source_with_retry(
        self,
        src: BaseSourcePlugin,
        state: ExecutionState,
    ) -> list[WorkflowItem]:
        """Fetch from a source with retry on failure."""
        max_retries = state.policy.retry_policy.get("default_retries", 2)
        items: list[WorkflowItem] = []

        for attempt in range(max_retries + 1):
            t0 = time.monotonic()
            await self._emit(
                state.context, "", src.manifest.name, "source", "started",
                message=f"attempt {attempt + 1}/{max_retries + 1}",
            )
            try:
                results = await src.fetch(state.context)
                duration = int((time.monotonic() - t0) * 1000)
                for r in results:
                    if r.success:
                        items.append(r.item)
                await self._emit(
                    state.context, "", src.manifest.name, "source", "success",
                    message=f"Fetched {len(results)} item(s)",
                    duration_ms=duration,
                )
                return items  # success — no more retries
            except Exception as exc:
                duration = int((time.monotonic() - t0) * 1000)
                if attempt < max_retries:
                    wait = 2 ** attempt  # exponential backoff
                    log.warning(
                        "Source %s failed (attempt %d), retrying in %ds: %s",
                        src.manifest.name, attempt + 1, wait, exc,
                    )
                    await self._emit(
                        state.context, "", src.manifest.name, "source", "failed",
                        message=f"Retry {attempt+1}: {exc}",
                        duration_ms=duration,
                    )
                    await asyncio.sleep(wait)
                else:
                    await self._emit(
                        state.context, "", src.manifest.name, "source", "failed",
                        message=f"All retries exhausted: {exc}",
                        duration_ms=duration,
                    )
        return items

    async def _run_plugin_with_retry(
        self,
        plugin: BasePlugin,
        item: WorkflowItem,
        step: str,
        state: ExecutionState,
    ) -> bool:
        """Execute a processing plugin with retry on failure."""
        max_retries = state.policy.retry_policy.get("default_retries", 2)

        for attempt in range(max_retries + 1):
            t0 = time.monotonic()
            await self._emit(
                state.context, item.id, plugin.manifest.name, step, "started",
                message=f"attempt {attempt + 1}/{max_retries + 1}"
                         if attempt > 0 else "",
            )
            try:
                result = await plugin.run(item, state.context)
                duration = int((time.monotonic() - t0) * 1000)

                if result.success:
                    # Merge mutations back into item (in-place via reference)
                    # The item object is shared, so plugin mutations persist
                    await self._emit(
                        state.context, item.id, plugin.manifest.name, step,
                        "success", message="",
                        duration_ms=duration,
                    )
                    return True
                else:
                    # Plugin returned failure but didn't throw
                    if attempt < max_retries:
                        log.warning(
                            "%s/%s returned failure (attempt %d), retrying: %s",
                            step, plugin.manifest.name, attempt + 1,
                            result.error,
                        )
                        await self._emit(
                            state.context, item.id, plugin.manifest.name, step,
                            "failed",
                            message=f"Retry {attempt+1}: {result.error}",
                            duration_ms=duration,
                        )
                        await asyncio.sleep(2 ** attempt)
                    else:
                        await self._emit(
                            state.context, item.id, plugin.manifest.name, step,
                            "failed",
                            message=f"All retries exhausted: {result.error}",
                            duration_ms=duration,
                        )
                        state.stats["errors"].append(
                            f"{step}/{plugin.manifest.name}: {result.error}"
                        )
                        return False

            except Exception as exc:
                duration = int((time.monotonic() - t0) * 1000)
                if attempt < max_retries:
                    log.warning(
                        "%s/%s threw exception (attempt %d), retrying: %s",
                        step, plugin.manifest.name, attempt + 1, exc,
                    )
                    await self._emit(
                        context, item.id, plugin.manifest.name, step,
                        "failed",
                        message=f"Retry {attempt+1}: {exc}",
                        duration_ms=duration,
                    )
                    await asyncio.sleep(2 ** attempt)
                else:
                    await self._emit(
                        context, item.id, plugin.manifest.name, step,
                        "failed",
                        message=f"All retries exhausted: {exc}",
                        duration_ms=duration,
                    )
                    state.stats["errors"].append(
                        f"{step}/{plugin.manifest.name}: {exc}"
                    )
                    return False

        return False  # should not reach here

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _category_key(step: str) -> str:
        """Map a workflow step name to the plugin config key."""
        mapping = {
            "parser": "parsers",
            "ai": "ai",
            "media": "media",
            "dispatch": "dispatchers",
        }
        return mapping.get(step, step)

    async def _emit(
        self,
        ctx: RunContext,
        item_id: str,
        plugin_name: str,
        step: str,
        status: str,
        *,
        message: str = "",
        duration_ms: int | None = None,
    ) -> None:
        event = NodeEvent(
            run_id=ctx.run_id,
            item_id=item_id,
            step=step,
            plugin_name=plugin_name,
            status=status,  # type: ignore[arg-type]
            message=message,
            duration_ms=duration_ms,
        )
        await self.bus.emit(event)
        log.debug(
            "[%s] %s/%s → %s  %s  (%s ms)",
            ctx.run_id[:8], step, plugin_name, status, message,
            duration_ms or "—",
        )
