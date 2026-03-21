"""
Lark (Feishu) Webhook Dispatcher
================================
Pushes content to a Lark/Feishu group via Custom Bot Webhook.

Config::

    {
        "webhook_url_env": "LARK_WEBHOOK_URL"
    }
"""

from __future__ import annotations

import os
from typing import Any

import aiohttp

from app.models.workflow import PluginResult, RunContext, WorkflowItem
from app.plugins.base import BasePlugin, PluginManifest


class LarkDispatcher(BasePlugin):
    manifest = PluginManifest(
        name="lark_dispatcher",
        category="dispatcher",
        version="1.0.0",
        description="Pushes rich text to Lark/Feishu Webhook",
        config_schema={
            "webhook_url_env": {
                "type": "string",
                "default": "LARK_WEBHOOK_URL",
                "description": "Env var holding Lark bot webhook URL",
            },
        },
    )

    async def run(
        self, item: WorkflowItem, context: RunContext
    ) -> PluginResult:
        webhook_env = self.config.get("webhook_url_env", "LARK_WEBHOOK_URL")
        webhook_url = os.environ.get(webhook_env)

        if not webhook_url:
            return PluginResult(
                success=False, item=item,
                error="Lark webhook URL not configured in environment",
            )

        title = item.title or "Untitled Message"
        content = item.summary or item.cleaned_text or item.raw_content or "No content"

        # Build Lark interactive message card payload
        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": f"📰 {title[:50]}"},
                    "template": "blue"
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": content[:2000] + ("..." if len(content) > 2000 else "")
                    }
                ]
            }
        }

        if item.source_uri:
            payload["card"]["elements"].append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "🔗 Read Original"},
                    "type": "primary",
                    "url": item.source_uri
                }]
            })

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as resp:
                    resp.raise_for_status()
                    data = await resp.json()

                    if data.get("code") != 0:
                        raise RuntimeError(f"Lark API error: {data.get('msg')}")

            return PluginResult(
                success=True, item=item, logs=["lark: sent interactive card successfully"]
            )
        except Exception as exc:
            return PluginResult(
                success=False, item=item,
                error=f"Lark dispatch failed: {exc}"
            )
