"""
Bilibili Hot List Source Plugin
===============================
Fetches the top N trending videos from Bilibili's public API.

Config::

    {
        "limit": 10
    }
"""

from __future__ import annotations

import uuid
from typing import Any

import aiohttp

from app.models.workflow import PluginResult, RunContext, WorkflowItem
from app.plugins.base import BaseSourcePlugin, PluginManifest

_API_URL = "https://api.bilibili.com/x/web-interface/popular?ps={limit}&pn=1"


class BilibiliHotPlugin(BaseSourcePlugin):
    manifest = PluginManifest(
        name="bilibili_hot",
        category="source",
        version="1.0.0",
        description="Fetches Bilibili trending videos",
        config_schema={
            "limit": {
                "type": "int",
                "default": 10,
                "description": "Number of top videos to fetch (max 50)",
            },
        },
    )

    async def fetch(self, context: RunContext) -> list[PluginResult]:
        limit = min(self.config.get("limit", 10), 50)
        url = _API_URL.format(limit=limit)
        results: list[PluginResult] = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    data = await resp.json()

            if data.get("code") != 0:
                raise RuntimeError(f"Bilibili API error: {data.get('message')}")

            items = data.get("data", {}).get("list", [])
            for item in items[:limit]:
                bvid = item.get("bvid", "")
                title = item.get("title", "Untitled")
                desc = item.get("desc", "")
                owner = item.get("owner", {}).get("name", "Unknown")
                link = f"https://www.bilibili.com/video/{bvid}"

                wf_item = WorkflowItem(
                    id=uuid.uuid4().hex,
                    source_type="bilibili",
                    source_uri=link,
                    title=title,
                    raw_content=f"{title}\n\n{desc}\n\nUP主: {owner}",
                    metadata={
                        "external_id": bvid,
                        "author": owner,
                        "view_count": item.get("stat", {}).get("view", 0),
                        "like_count": item.get("stat", {}).get("like", 0),
                        "pubdate": item.get("pubdate", 0),
                    },
                )
                results.append(PluginResult(success=True, item=wf_item))

        except Exception as exc:
            results.append(
                PluginResult(
                    success=False,
                    item=WorkflowItem(
                        source_type="bilibili",
                        source_uri="api.bilibili.com",
                        title="[API Fetch Error]",
                    ),
                    error=f"Failed to fetch Bilibili hot list: {exc}",
                )
            )

        return results
