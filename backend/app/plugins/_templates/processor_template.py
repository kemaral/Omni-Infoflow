"""
Plugin Template: Processor (Parser / AI / Media / Dispatcher)
==============================================================
Copy this file into the relevant ``app/plugins/<category>/`` directory.
Fill in the ``manifest`` and implement ``run()``.
"""

from __future__ import annotations

from typing import Any

from app.models.workflow import PluginResult, RunContext, WorkflowItem
from app.plugins.base import BasePlugin, PluginManifest


class MyProcessorPlugin(BasePlugin):
    """TODO: replace with your plugin description."""

    manifest = PluginManifest(
        name="my_processor",
        category="parser",  # change to: parser | ai | media | dispatcher
        version="0.1.0",
        description="Short description of what this plugin does.",
        config_schema={
            "option_a": {
                "type": "string",
                "required": False,
                "default": "",
                "description": "An example option",
            },
        },
    )

    async def run(
        self, item: WorkflowItem, context: RunContext
    ) -> PluginResult:
        try:
            # 1. Read config and context
            option_a = self.config.get("option_a", "")

            # 2. Do your processing (transform item fields)
            # Example: item.cleaned_text = clean(item.raw_content)

            # 3. Return success
            return PluginResult(
                success=True,
                item=item,
                logs=[f"{self.manifest.name}: processed '{item.title}'"],
            )
        except Exception as exc:
            return PluginResult(
                success=False,
                item=item,
                error=str(exc),
            )
