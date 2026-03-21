"""
Mock Parser Plugin (for testing)
=================================
Strips angle brackets to simulate HTML cleaning.
"""

from __future__ import annotations

import re

from app.models.workflow import PluginResult, RunContext, WorkflowItem
from app.plugins.base import BasePlugin, PluginManifest


class MockParserPlugin(BasePlugin):
    manifest = PluginManifest(
        name="mock_parser",
        category="parser",
        version="0.1.0",
        description="Strips HTML tags for testing",
        config_schema={},
        enabled_by_default=True,
    )

    async def run(
        self, item: WorkflowItem, context: RunContext
    ) -> PluginResult:
        raw = item.raw_content or ""
        item.cleaned_text = re.sub(r"<[^>]+>", "", raw).strip()
        return PluginResult(
            success=True,
            item=item,
            logs=[f"mock_parser: cleaned {len(item.cleaned_text)} chars"],
        )
