"""
Test Suite: MVP Plugins (M3)
==============================
Tests plugin classes can be loaded, instantiated, and invoked
with mock data. Network-dependent tests are isolated behind
lightweight stubs.
"""

from __future__ import annotations

import pytest

from app.models.workflow import PluginResult, RunContext, WorkflowItem


# ---------------------------------------------------------------------------
# HTML Cleaner
# ---------------------------------------------------------------------------

class TestHTMLCleaner:
    @pytest.mark.asyncio
    async def test_strips_html_tags(self):
        from app.plugins.parsers.html_cleaner import HTMLCleanerPlugin

        plugin = HTMLCleanerPlugin({})
        item = WorkflowItem(
            raw_content="<p>Hello <b>world</b>! This is a <a href='#'>test</a>.</p>"
        )
        ctx = RunContext()
        result = await plugin.run(item, ctx)

        assert result.success
        assert "<" not in result.item.cleaned_text
        assert "Hello" in result.item.cleaned_text
        assert "world" in result.item.cleaned_text

    @pytest.mark.asyncio
    async def test_removes_script_tags(self):
        from app.plugins.parsers.html_cleaner import HTMLCleanerPlugin

        plugin = HTMLCleanerPlugin({})
        item = WorkflowItem(
            raw_content="<p>Good</p><script>alert('xss')</script><p>Content</p>"
        )
        ctx = RunContext()
        result = await plugin.run(item, ctx)

        assert result.success
        assert "alert" not in result.item.cleaned_text
        assert "Good" in result.item.cleaned_text

    @pytest.mark.asyncio
    async def test_handles_empty_content(self):
        from app.plugins.parsers.html_cleaner import HTMLCleanerPlugin

        plugin = HTMLCleanerPlugin({})
        item = WorkflowItem(raw_content="")
        ctx = RunContext()
        result = await plugin.run(item, ctx)
        assert result.success

    @pytest.mark.asyncio
    async def test_decodes_html_entities(self):
        from app.plugins.parsers.html_cleaner import HTMLCleanerPlugin

        plugin = HTMLCleanerPlugin({})
        item = WorkflowItem(raw_content="<p>Tom &amp; Jerry &lt;3</p>")
        ctx = RunContext()
        result = await plugin.run(item, ctx)

        assert result.success
        assert "Tom & Jerry <3" in result.item.cleaned_text


# ---------------------------------------------------------------------------
# LLM Client — tests without network (manifest & chunking only)
# ---------------------------------------------------------------------------

class TestLLMClient:
    def test_manifest_valid(self):
        from app.plugins.ai.llm_client import LLMClientPlugin
        assert LLMClientPlugin.manifest.name == "llm_client"
        assert LLMClientPlugin.manifest.category == "ai"

    def test_chunk_short_text(self):
        from app.plugins.ai.llm_client import LLMClientPlugin
        plugin = LLMClientPlugin({"chunk_size": 100})
        chunks = plugin._chunk_text("Hello world")
        assert len(chunks) == 1

    def test_chunk_long_text(self):
        from app.plugins.ai.llm_client import LLMClientPlugin
        plugin = LLMClientPlugin({"chunk_size": 50})
        text = "这是一个长句子。" * 20  # ~160 chars
        chunks = plugin._chunk_text(text)
        assert len(chunks) > 1
        # All content preserved
        rejoined = "".join(chunks)
        assert "这是一个长句子" in rejoined

    def test_soul_fallback(self):
        from app.plugins.ai.llm_client import LLMClientPlugin
        plugin = LLMClientPlugin({"soul_path": "nonexistent/soul.md"})
        ctx = RunContext()
        prompt = plugin._load_soul(ctx)
        assert "helpful" in prompt.lower() or "assistant" in prompt.lower()


# ---------------------------------------------------------------------------
# Telegram Dispatcher — message formatting only (no network)
# ---------------------------------------------------------------------------

class TestTelegramDispatcher:
    def test_format_message(self):
        from app.plugins.dispatchers.telegram import TelegramDispatcher

        item = WorkflowItem(
            title="Test Article",
            source_uri="https://example.com/article",
            summary="This is a summary.",
            metadata={"author": "Alice"},
        )
        msg = TelegramDispatcher._format_message(item)

        assert "Test" in msg
        assert "summary" in msg
        assert "example.com" in msg
        assert "Alice" in msg

    def test_split_short_message(self):
        from app.plugins.dispatchers.telegram import TelegramDispatcher
        chunks = TelegramDispatcher._split_message("Short message")
        assert len(chunks) == 1

    def test_split_long_message(self):
        from app.plugins.dispatchers.telegram import TelegramDispatcher
        long_msg = "A" * 5000
        chunks = TelegramDispatcher._split_message(long_msg)
        assert len(chunks) >= 2
        # All content preserved
        total_len = sum(len(c) for c in chunks)
        assert total_len == 5000

    @pytest.mark.asyncio
    async def test_missing_token_returns_error(self):
        from app.plugins.dispatchers.telegram import TelegramDispatcher
        import os

        # Ensure env vars are not set
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)

        plugin = TelegramDispatcher({})
        item = WorkflowItem(title="Test")
        ctx = RunContext()
        result = await plugin.run(item, ctx)

        assert not result.success
        assert "not configured" in result.error


# ---------------------------------------------------------------------------
# RSS Plugin — manifest check (network tests would need mocking)
# ---------------------------------------------------------------------------

class TestRSSPlugin:
    def test_manifest_valid(self):
        from app.plugins.sources.rss import RSSPlugin
        assert RSSPlugin.manifest.name == "rss_source"
        assert RSSPlugin.manifest.category == "source"
        assert "feed_urls" in RSSPlugin.manifest.config_schema

    def test_can_instantiate(self):
        from app.plugins.sources.rss import RSSPlugin
        plugin = RSSPlugin({"feed_urls": ["https://example.com/feed"]})
        assert plugin.config["feed_urls"] == ["https://example.com/feed"]
