"""
Mock Source Plugin (for testing)
=================================
Returns a fixed list of fake WorkflowItems so the engine and tests can
exercise the full pipeline without network calls.
"""

from __future__ import annotations

from app.models.workflow import PluginResult, RunContext, WorkflowItem
from app.plugins.base import BaseSourcePlugin, PluginManifest


class MockSourcePlugin(BaseSourcePlugin):
    manifest = PluginManifest(
        name="mock_source",
        category="source",
        version="0.1.0",
        description="Returns fake items for testing",
        config_schema={},
        enabled_by_default=True,
    )

    async def fetch(self, context: RunContext) -> list[PluginResult]:
        items = [
            WorkflowItem(
                source_type="mock",
                source_uri="https://example.com/article-1",
                title="Mock Article One",
                raw_content="<p>Hello <b>world</b>. This is mock content.</p>",
                metadata={"external_id": "mock-guid-001"},
            ),
            WorkflowItem(
                source_type="mock",
                source_uri="https://example.com/article-2",
                title="Mock Article Two",
                raw_content="<div>Second piece of <em>content</em> for testing.</div>",
                metadata={"external_id": "mock-guid-002"},
            ),
        ]
        return [PluginResult(success=True, item=i) for i in items]
