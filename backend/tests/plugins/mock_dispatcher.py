"""
Mock Dispatcher Plugin (for testing)
=====================================
Records dispatched items in a list so assertions can inspect them.
"""

from __future__ import annotations

from app.models.workflow import PluginResult, RunContext, WorkflowItem
from app.plugins.base import BasePlugin, PluginManifest


class MockDispatcherPlugin(BasePlugin):
    """Collects dispatched items in ``cls.sent`` for test assertions."""

    manifest = PluginManifest(
        name="mock_dispatcher",
        category="dispatcher",
        version="0.1.0",
        description="Logs dispatches for testing",
        config_schema={},
        enabled_by_default=True,
    )

    # class-level accumulator — reset between tests
    sent: list[WorkflowItem] = []

    async def run(
        self, item: WorkflowItem, context: RunContext
    ) -> PluginResult:
        MockDispatcherPlugin.sent.append(item)
        return PluginResult(
            success=True,
            item=item,
            logs=[f"mock_dispatcher: dispatched '{item.title}'"],
        )

    @classmethod
    def reset(cls) -> None:
        cls.sent.clear()
