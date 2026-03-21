"""
Edge TTS Media Plugin
=====================
Synthesizes speech from summary text using the free edge-tts library.

Config::

    {
        "voice": "zh-CN-XiaoxiaoNeural",
        "rate": "+0%",
        "volume": "+0%"
    }
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.paths import MEDIA_DIR
from app.models.workflow import PluginResult, RunContext, WorkflowItem
from app.plugins.base import BasePlugin, PluginManifest


class EdgeTTSPlugin(BasePlugin):
    manifest = PluginManifest(
        name="edge_tts",
        category="media",
        version="1.0.0",
        description="Text-to-Speech using edge-tts",
        config_schema={
            "voice": {
                "type": "string",
                "default": "zh-CN-XiaoxiaoNeural",
                "description": "Voice identifier",
            },
            "rate": {
                "type": "string",
                "default": "+0%",
                "description": "Speaking rate (e.g., +20%, -10%)",
            },
        },
    )

    async def run(self, item: WorkflowItem, context: RunContext) -> PluginResult:
        # Require Edge TTS to be installed
        try:
            import edge_tts
        except ImportError:
            return PluginResult(
                success=False, item=item,
                error="edge-tts not installed. Run `pip install edge-tts`",
            )

        text = item.summary or item.cleaned_text or ""
        if not text.strip():
            return PluginResult(
                success=True, item=item,
                logs=["edge_tts: no text to synthesize, skipping"],
            )

        voice = self.config.get("voice", "zh-CN-XiaoxiaoNeural")
        rate = self.config.get("rate", "+0%")

        # Ensure media directory exists
        out_dir = MEDIA_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        filename = f"tts_{item.id}_{uuid.uuid4().hex[:6]}.mp3"
        filepath = out_dir / filename

        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            await communicate.save(str(filepath))

            item.artifacts["audio"] = str(filepath)
            return PluginResult(
                success=True, item=item,
                logs=[f"edge_tts: saved audio to {filepath}"],
            )
        except Exception as exc:
            return PluginResult(
                success=False, item=item,
                error=f"Edge TTS synthesis failed: {exc}",
            )
