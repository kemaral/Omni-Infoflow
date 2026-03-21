"""
Omni-InfoFlow Plugin Contract Layer
=====================================
All plugins — regardless of category — share two invariants:

1. A ``PluginManifest`` class-attribute describing *what* the plugin is.
2. A single async entry-point whose signature is dictated by the base class.

Processing plugins (parser / ai / media / dispatcher):
    ``async run(item, context) -> PluginResult``

Source plugins (they *produce* items rather than transform one):
    ``async fetch(context) -> list[PluginResult]``
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.workflow import PluginResult, RunContext, WorkflowItem


# ---------------------------------------------------------------------------
# PluginManifest — self-describing metadata for every plugin
# ---------------------------------------------------------------------------

class PluginManifest(BaseModel):
    """Declarative metadata baked into every plugin class.

    ``config_schema`` follows a simplified JSON-Schema-like dict so the
    frontend can auto-render a settings form without knowing the plugin's
    internals.

    Example::

        PluginManifest(
            name="rss_source",
            category="source",
            version="1.0.0",
            description="Standard RSS / Atom feed reader",
            config_schema={
                "feed_urls": {"type": "list", "required": True,
                              "description": "List of RSS feed URLs"},
                "fetch_interval_min": {"type": "int", "default": 30,
                                       "description": "Polling interval"},
            },
        )
    """

    name: str
    category: Literal["source", "parser", "ai", "media", "dispatcher"]
    version: str = "0.1.0"
    description: str = ""
    config_schema: dict[str, Any] = Field(default_factory=dict)
    enabled_by_default: bool = False


# ---------------------------------------------------------------------------
# BasePlugin — unified contract for parser / ai / media / dispatcher
# ---------------------------------------------------------------------------

class BasePlugin(ABC):
    """Every processing plugin inherits from this.

    Sub-classes MUST:
        1. Set ``manifest`` as a class attribute.
        2. Implement ``async run(item, context) -> PluginResult``.

    The engine treats all processing plugins identically: it calls ``run``,
    inspects the ``PluginResult``, and decides whether to continue, skip, or
    abort based on the workflow policy.
    """

    manifest: PluginManifest

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @abstractmethod
    async def run(
        self,
        item: WorkflowItem,
        context: RunContext,
    ) -> PluginResult:
        """Transform *item* in-place (or produce a derivative) and return a
        ``PluginResult`` wrapping the updated item."""
        ...


# ---------------------------------------------------------------------------
# BaseSourcePlugin — contract for data ingestion
# ---------------------------------------------------------------------------

class BaseSourcePlugin(ABC):
    """Sources are different: they *produce* WorkflowItems from external data.

    Sub-classes MUST:
        1. Set ``manifest`` as a class attribute.
        2. Implement ``async fetch(context) -> list[PluginResult]``.

    Each ``PluginResult.item`` in the returned list represents one piece of
    raw content (article, paper, page, …) ready for downstream parsing.
    """

    manifest: PluginManifest

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @abstractmethod
    async def fetch(
        self,
        context: RunContext,
    ) -> list[PluginResult]:
        """Fetch external data and return a list of ``PluginResult`` objects,
        each wrapping a newly-created ``WorkflowItem``."""
        ...
