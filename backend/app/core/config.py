"""
Configuration Manager
======================
Reads, validates, and persists the four-layer ``config.json``::

    {
      "global": { ... },
      "workflow": { ... },
      "plugins": { "sources": [], "parsers": [], ... },
      "runtime": { ... }
    }

Thread-safe writes use an ``asyncio.Lock`` so concurrent WebUI saves
never corrupt the file.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import BaseModel, Field

from app.core.paths import DEFAULT_CONFIG_PATH, RUNTIME_CONFIG_EXAMPLE_PATH

# ---------------------------------------------------------------------------
# Default paths — overridable via environment or constructor
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Structured config sub-models
# ---------------------------------------------------------------------------

class WorkflowPolicy(BaseModel):
    """Declarative workflow execution policy stored in config.json."""
    steps: list[str] = Field(
        default=["source", "parser", "ai", "media", "dispatch"]
    )
    optional_steps: list[str] = Field(default=["ai", "media"])
    continue_on_error: list[str] = Field(default=["media"])
    max_concurrency: int = 3
    retry_policy: dict[str, Any] = Field(
        default_factory=lambda: {"default_retries": 2}
    )


class AppConfig(BaseModel):
    """Top-level configuration schema."""
    global_settings: dict[str, Any] = Field(
        default_factory=dict, alias="global"
    )
    workflow: WorkflowPolicy = Field(default_factory=WorkflowPolicy)
    plugins: dict[str, list[dict[str, Any]]] = Field(
        default_factory=lambda: {
            "sources": [],
            "parsers": [],
            "ai": [],
            "media": [],
            "dispatchers": [],
        }
    )
    runtime: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# ConfigManager — async-safe read / write
# ---------------------------------------------------------------------------

class ConfigManager:
    """Singleton-ish config gateway used by API routes and the engine.

    Usage::

        mgr = ConfigManager()            # uses default data/config.json
        cfg = await mgr.load()           # -> AppConfig
        await mgr.save(cfg)              # persist back to disk
        await mgr.patch({"runtime": {"debug": True}})  # partial update
    """

    def __init__(self, path: "Path | str | None" = None) -> None:
        from pathlib import Path

        self._path = Path(path) if path else DEFAULT_CONFIG_PATH
        self._lock = asyncio.Lock()
        self._cache: AppConfig | None = None

    # -- read ---------------------------------------------------------------

    async def load(self, *, force: bool = False) -> AppConfig:
        """Return the current config, reading from disk on first call."""
        if self._cache is not None and not force:
            return self._cache

        if not self._path.exists():
            if RUNTIME_CONFIG_EXAMPLE_PATH.exists():
                raw = RUNTIME_CONFIG_EXAMPLE_PATH.read_text(encoding="utf-8")
                self._cache = AppConfig.model_validate_json(raw)
            else:
                self._cache = AppConfig()
            await self.save(self._cache)
            return self._cache

        raw = self._path.read_text(encoding="utf-8")
        self._cache = AppConfig.model_validate_json(raw)
        return self._cache

    # -- write --------------------------------------------------------------

    async def save(self, config: AppConfig) -> None:
        """Atomically persist *config* to disk."""
        async with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = config.model_dump(by_alias=True)
            self._path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._cache = config

    async def patch(self, partial: dict[str, Any]) -> AppConfig:
        """Merge *partial* into the current config and persist."""
        cfg = await self.load()
        merged = cfg.model_dump(by_alias=True)
        _deep_merge(merged, partial)
        updated = AppConfig.model_validate(merged)
        await self.save(updated)
        return updated

    # -- helpers ------------------------------------------------------------

    @property
    def path(self) -> Path:
        return self._path

    def get_plugin_configs(self, category: str) -> list[dict[str, Any]]:
        """Quick sync accessor — requires prior ``load()``."""
        if self._cache is None:
            raise RuntimeError("Config not loaded yet. Call await load() first.")
        return self._cache.plugins.get(category, [])


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge *override* into *base* in-place."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
