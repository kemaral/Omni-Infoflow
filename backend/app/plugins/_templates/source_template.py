"""
Plugin Template: Source
========================
Copy this file into ``app/plugins/sources/`` and rename it.
Fill in the ``manifest`` and implement ``fetch()``.
"""

from __future__ import annotations

from typing import Any

from app.models.workflow import PluginResult, RunContext, WorkflowItem
from app.plugins.base import BaseSourcePlugin, PluginManifest


class MySourcePlugin(BaseSourcePlugin):
    """TODO: replace with your plugin description."""

    manifest = PluginManifest(
        name="my_source",
        category="source",
        version="0.1.0",
        description="Short description of what this source fetches.",
        config_schema={
            "target_url": {
                "type": "string",
                "required": True,
                "description": "URL or identifier to fetch from",
            },
        },
    )

    async def fetch(self, context: RunContext) -> list[PluginResult]:
        # 1. Read your config
        target = self.config.get("target_url", "")

        # 2. Fetch external data (use aiohttp, feedparser, etc.)
        raw_data = f"Raw content from {target}"

        # 3. Wrap each piece of content as a WorkflowItem
        item = WorkflowItem(
            source_type=self.manifest.name,
            source_uri=target,
            title="Example Title",
            raw_content=raw_data,
        )

        # 4. Return a list of PluginResult
        return [PluginResult(success=True, item=item)]
