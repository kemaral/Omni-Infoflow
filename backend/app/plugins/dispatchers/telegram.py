"""
Telegram Dispatcher Plugin
============================
Sends processed content to a Telegram chat via Bot API.

Features:
  - Auto-splits long messages (Telegram 4096 char limit)
  - Supports audio file attachments (MP3 up to 50MB)
  - Formats output as Markdown with source link

Config::

    {
        "bot_token_env": "TELEGRAM_BOT_TOKEN",
        "chat_id_env": "TELEGRAM_CHAT_ID",
        "parse_mode": "Markdown"
    }
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import aiohttp

from app.models.workflow import PluginResult, RunContext, WorkflowItem
from app.plugins.base import BasePlugin, PluginManifest

_TG_API = "https://api.telegram.org/bot{token}"
_MAX_MSG_LEN = 4000  # leave margin from 4096 limit


class TelegramDispatcher(BasePlugin):
    manifest = PluginManifest(
        name="telegram_dispatcher",
        category="dispatcher",
        version="1.0.0",
        description="Pushes content to Telegram via Bot API",
        config_schema={
            "bot_token_env": {
                "type": "string",
                "default": "TELEGRAM_BOT_TOKEN",
                "description": "Env var holding the bot token",
            },
            "chat_id_env": {
                "type": "string",
                "default": "TELEGRAM_CHAT_ID",
                "description": "Env var holding the target chat ID",
            },
            "parse_mode": {
                "type": "string",
                "default": "Markdown",
                "description": "Markdown or HTML",
            },
        },
    )

    async def run(
        self, item: WorkflowItem, context: RunContext
    ) -> PluginResult:
        token = os.environ.get(
            self.config.get("bot_token_env", "TELEGRAM_BOT_TOKEN"), ""
        )
        chat_id = os.environ.get(
            self.config.get("chat_id_env", "TELEGRAM_CHAT_ID"), ""
        )

        if not token or not chat_id:
            return PluginResult(
                success=False, item=item,
                error="Telegram bot_token or chat_id not configured",
            )

        base_url = _TG_API.format(token=token)
        parse_mode = self.config.get("parse_mode", "Markdown")

        # Build message body
        body = self._format_message(item)
        logs: list[str] = []

        try:
            async with aiohttp.ClientSession() as session:
                # Send text message(s)
                chunks = self._split_message(body)
                for i, chunk in enumerate(chunks):
                    await self._send_text(
                        session, base_url, chat_id, chunk, parse_mode
                    )
                    logs.append(
                        f"telegram: sent part {i+1}/{len(chunks)} "
                        f"({len(chunk)} chars)"
                    )

                # Send audio attachment if available
                audio_path = item.artifacts.get("audio")
                if audio_path and Path(audio_path).exists():
                    await self._send_audio(
                        session, base_url, chat_id, audio_path, item.title
                    )
                    logs.append(f"telegram: sent audio {audio_path}")

            return PluginResult(success=True, item=item, logs=logs)

        except Exception as exc:
            return PluginResult(
                success=False, item=item,
                error=f"Telegram dispatch failed: {exc}",
            )

    # -- formatting ---------------------------------------------------------

    @staticmethod
    def _format_message(item: WorkflowItem) -> str:
        """Build a formatted Telegram message from the item."""
        parts: list[str] = []

        # Title
        title = item.title or "Untitled"
        parts.append(f"*{_escape_md(title)}*")

        # Summary or cleaned text
        content = item.summary or item.cleaned_text or item.raw_content or ""
        if content:
            parts.append(content[:3500])  # safety trim

        # Source link
        if item.source_uri:
            parts.append(f"\n🔗 [原文链接]({item.source_uri})")

        # Source metadata
        author = item.metadata.get("author", "")
        if author:
            parts.append(f"👤 {author}")

        return "\n\n".join(parts)

    @staticmethod
    def _split_message(text: str) -> list[str]:
        """Split text into chunks respecting Telegram's length limit."""
        if len(text) <= _MAX_MSG_LEN:
            return [text]

        chunks: list[str] = []
        while text:
            if len(text) <= _MAX_MSG_LEN:
                chunks.append(text)
                break
            # Try to split on newline
            split_pos = text.rfind("\n", 0, _MAX_MSG_LEN)
            if split_pos == -1:
                split_pos = _MAX_MSG_LEN
            chunks.append(text[:split_pos])
            text = text[split_pos:].lstrip()

        return chunks

    # -- Telegram API calls -------------------------------------------------

    @staticmethod
    async def _send_text(
        session: aiohttp.ClientSession,
        base_url: str,
        chat_id: str,
        text: str,
        parse_mode: str,
    ) -> None:
        url = f"{base_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        }
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
            if not data.get("ok"):
                raise RuntimeError(
                    f"Telegram sendMessage failed: {data.get('description')}"
                )

    @staticmethod
    async def _send_audio(
        session: aiohttp.ClientSession,
        base_url: str,
        chat_id: str,
        audio_path: str,
        title: str | None = None,
    ) -> None:
        url = f"{base_url}/sendAudio"
        data = aiohttp.FormData()
        data.add_field("chat_id", chat_id)
        if title:
            data.add_field("title", title)
        data.add_field(
            "audio",
            open(audio_path, "rb"),
            filename=Path(audio_path).name,
        )
        async with session.post(url, data=data) as resp:
            result = await resp.json()
            if not result.get("ok"):
                raise RuntimeError(
                    f"Telegram sendAudio failed: {result.get('description')}"
                )


def _escape_md(text: str) -> str:
    """Escape special Markdown characters for Telegram."""
    for char in ("_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"):
        text = text.replace(char, f"\\{char}")
    return text
