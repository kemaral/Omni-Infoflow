"""
Mock source plugin that returns both success and failure results.
"""

from __future__ import annotations

from app.models.workflow import PluginResult, RunContext, WorkflowItem
from app.plugins.base import BaseSourcePlugin, PluginManifest


class MockPartialSourcePlugin(BaseSourcePlugin):
    manifest = PluginManifest(
        name="mock_partial_source",
        category="source",
        version="0.1.0",
        description="Returns one successful item and one failed source result",
        config_schema={},
    )

    async def fetch(self, context: RunContext) -> list[PluginResult]:
        success_item = WorkflowItem(
            source_type="mock",
            source_uri="https://example.com/partial-success",
            title="Partial Success",
            raw_content="<p>content</p>",
            metadata={"external_id": "partial-success"},
        )
        failed_item = WorkflowItem(
            source_type="mock",
            source_uri="https://example.com/partial-failure",
            title="Partial Failure",
        )
        return [
            PluginResult(success=True, item=success_item),
            PluginResult(
                success=False,
                item=failed_item,
                error="mock partial source failure",
            ),
        ]
