"""
Mock Failing Plugin (for testing error handling & retry)
==========================================================
Fails a configurable number of times before succeeding.
"""

from __future__ import annotations

from app.models.workflow import PluginResult, RunContext, WorkflowItem
from app.plugins.base import BasePlugin, PluginManifest


class MockFailingPlugin(BasePlugin):
    """Fails ``fail_count`` times, then succeeds.

    Config::

        {"fail_count": 2}   → fails twice, succeeds on 3rd attempt
        {"fail_count": 99}  → always fails (for total failure tests)
    """

    manifest = PluginManifest(
        name="mock_failing",
        category="parser",
        version="0.1.0",
        description="Fails N times then succeeds (testing only)",
        config_schema={"fail_count": {"type": "int", "default": 1}},
    )

    _call_count: int = 0

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        MockFailingPlugin._call_count = 0

    async def run(
        self, item: WorkflowItem, context: RunContext
    ) -> PluginResult:
        MockFailingPlugin._call_count += 1
        fail_count = self.config.get("fail_count", 1)

        if MockFailingPlugin._call_count <= fail_count:
            return PluginResult(
                success=False,
                item=item,
                error=f"Intentional failure #{MockFailingPlugin._call_count}",
            )

        item.cleaned_text = f"Recovered after {fail_count} failure(s)"
        return PluginResult(success=True, item=item)

    @classmethod
    def reset(cls) -> None:
        cls._call_count = 0
