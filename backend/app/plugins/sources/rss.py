"""
RSS Source Plugin
==================
Fetches and parses RSS / Atom feeds using ``feedparser``.

Config::

    {
        "feed_urls": ["https://example.com/feed.xml"],
        "fetch_timeout": 30
    }
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

import aiohttp
import feedparser

from app.models.workflow import PluginResult, RunContext, WorkflowItem
from app.plugins.base import BaseSourcePlugin, PluginManifest


class RSSPlugin(BaseSourcePlugin):
    manifest = PluginManifest(
        name="rss_source",
        category="source",
        version="1.0.0",
        description="Standard RSS / Atom feed reader",
        config_schema={
            "feed_urls": {
                "type": "list",
                "required": True,
                "description": "List of RSS/Atom feed URLs to poll",
            },
            "fetch_timeout": {
                "type": "int",
                "default": 30,
                "description": "HTTP timeout in seconds",
            },
        },
    )

    async def fetch(self, context: RunContext) -> list[PluginResult]:
        feed_urls: list[str] = self.config.get("feed_urls", [])
        timeout = aiohttp.ClientTimeout(
            total=self.config.get("fetch_timeout", 30)
        )
        results: list[PluginResult] = []

        async with aiohttp.ClientSession(timeout=timeout) as session:
            for url in feed_urls:
                try:
                    items = await self._fetch_feed(session, url)
                    results.extend(items)
                except Exception as exc:
                    results.append(PluginResult(
                        success=False,
                        item=WorkflowItem(
                            source_type="rss",
                            source_uri=url,
                            title=f"[Feed Error] {url}",
                        ),
                        error=str(exc),
                    ))

        return results

    async def _fetch_feed(
        self, session: aiohttp.ClientSession, url: str
    ) -> list[PluginResult]:
        """Download and parse a single RSS/Atom feed."""
        async with session.get(url) as resp:
            resp.raise_for_status()
            body = await resp.text()

        feed = feedparser.parse(body)
        items: list[PluginResult] = []

        for entry in feed.entries:
            title = entry.get("title", "Untitled")
            link = entry.get("link", url)
            # Use entry content, summary, or description — whatever exists
            content = ""
            if hasattr(entry, "content") and entry.content:
                content = entry.content[0].get("value", "")
            elif hasattr(entry, "summary"):
                content = entry.summary or ""
            elif hasattr(entry, "description"):
                content = entry.description or ""

            # Build external_id from guid or link hash
            guid = entry.get("id") or entry.get("guid") or link
            external_id = hashlib.sha256(guid.encode()).hexdigest()[:16]

            item = WorkflowItem(
                id=uuid.uuid4().hex,
                source_type="rss",
                source_uri=link,
                title=title,
                raw_content=content,
                metadata={
                    "external_id": external_id,
                    "feed_url": url,
                    "published": entry.get("published", ""),
                    "author": entry.get("author", ""),
                },
            )
            items.append(PluginResult(success=True, item=item))

        return items
