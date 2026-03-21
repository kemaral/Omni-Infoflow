"""
LLM Client Plugin (AI Processor)
==================================
Sends cleaned text to an OpenAI-compatible API (OpenAI / DeepSeek / local)
with a system prompt loaded from ``data/prompts/soul.md``.

Features:
  - Token-safe chunking for long texts
  - Configurable model, temperature, max_tokens
  - Reads ``soul.md`` as the system-level persona

Config::

    {
        "api_base": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "model": "gpt-4o-mini",
        "max_tokens": 4096,
        "temperature": 0.7,
        "chunk_size": 12000,
        "soul_path": "data/prompts/soul.md"
    }
"""

from __future__ import annotations

import os
from typing import Any

from openai import AsyncOpenAI

from app.core.paths import DEFAULT_SOUL_PATH, resolve_runtime_path
from app.models.workflow import PluginResult, RunContext, WorkflowItem
from app.plugins.base import BasePlugin, PluginManifest


class LLMClientPlugin(BasePlugin):
    manifest = PluginManifest(
        name="llm_client",
        category="ai",
        version="1.0.0",
        description="Summarises text via OpenAI-compatible LLM API",
        config_schema={
            "api_base": {
                "type": "string",
                "default": "https://api.openai.com/v1",
                "description": "LLM API base URL",
            },
            "api_key_env": {
                "type": "string",
                "default": "OPENAI_API_KEY",
                "description": "Environment variable holding the API key",
            },
            "model": {
                "type": "string",
                "default": "gpt-4o-mini",
                "description": "Model identifier",
            },
            "max_tokens": {
                "type": "int",
                "default": 4096,
                "description": "Max output tokens",
            },
            "temperature": {
                "type": "float",
                "default": 0.7,
                "description": "Sampling temperature",
            },
            "chunk_size": {
                "type": "int",
                "default": 12000,
                "description": "Max input chars per chunk (token-safe margin)",
            },
            "soul_path": {
                "type": "string",
                "default": "data/prompts/soul.md",
                "description": "Path to system prompt file",
            },
        },
    )

    async def run(
        self, item: WorkflowItem, context: RunContext
    ) -> PluginResult:
        text = item.cleaned_text or item.raw_content or ""
        if not text.strip():
            return PluginResult(
                success=True, item=item,
                logs=["llm_client: no text to summarise"],
            )

        try:
            system_prompt = self._load_soul(context)
            client = self._build_client()

            chunks = self._chunk_text(text)
            summaries: list[str] = []

            for i, chunk in enumerate(chunks):
                user_msg = (
                    f"以下是第 {i+1}/{len(chunks)} 段内容，请按要求处理：\n\n"
                    f"标题：{item.title or '未知'}\n"
                    f"来源：{item.source_uri}\n\n"
                    f"{chunk}"
                )

                resp = await client.chat.completions.create(
                    model=self.config.get("model", "gpt-4o-mini"),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    max_tokens=self.config.get("max_tokens", 4096),
                    temperature=self.config.get("temperature", 0.7),
                )

                content = resp.choices[0].message.content or ""
                summaries.append(content)

            item.summary = "\n\n---\n\n".join(summaries)
            return PluginResult(
                success=True,
                item=item,
                logs=[f"llm_client: summarised {len(chunks)} chunk(s)"],
                metrics={
                    "chunks": len(chunks),
                    "input_chars": len(text),
                    "output_chars": len(item.summary),
                },
            )
        except Exception as exc:
            return PluginResult(
                success=False,
                item=item,
                error=f"LLM processing failed: {exc}",
            )

    # -- helpers ------------------------------------------------------------

    def _build_client(self) -> AsyncOpenAI:
        api_key_env = self.config.get("api_key_env", "OPENAI_API_KEY")
        api_key = os.environ.get(api_key_env, "")
        api_base = self.config.get("api_base", "https://api.openai.com/v1")
        return AsyncOpenAI(api_key=api_key, base_url=api_base)

    def _load_soul(self, context: RunContext) -> str:
        """Load the system prompt from soul.md."""
        soul_path = self.config.get("soul_path", "data/prompts/soul.md")
        full_path = resolve_runtime_path(soul_path)

        if full_path.exists():
            return full_path.read_text(encoding="utf-8")
        if DEFAULT_SOUL_PATH.exists():
            return DEFAULT_SOUL_PATH.read_text(encoding="utf-8")
        return "You are a helpful AI assistant that summarises content."

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into chunks safe for the model's context window."""
        chunk_size = self.config.get("chunk_size", 12000)
        if len(text) <= chunk_size:
            return [text]

        # Split on sentence boundaries where possible
        chunks: list[str] = []
        current = ""
        sentences = text.replace("\n", " ").split("。")

        for sentence in sentences:
            if len(current) + len(sentence) + 1 > chunk_size:
                if current:
                    chunks.append(current.strip())
                current = sentence + "。"
            else:
                current += sentence + "。"

        if current.strip():
            chunks.append(current.strip())

        return chunks or [text]
