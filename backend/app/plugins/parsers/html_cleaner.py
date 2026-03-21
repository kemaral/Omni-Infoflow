"""
HTML Cleaner Plugin
=====================
Strips HTML tags, ads, navigation, and boilerplate from raw content
to produce clean readable text.

Uses a layered strategy:
  1. Try ``readability`` (lxml-based) for article extraction
  2. Fall back to regex-based tag stripping

Config::

    {
        "min_text_length": 50
    }
"""

from __future__ import annotations

import html
import re
from typing import Any

from app.models.workflow import PluginResult, RunContext, WorkflowItem
from app.plugins.base import BasePlugin, PluginManifest


class HTMLCleanerPlugin(BasePlugin):
    manifest = PluginManifest(
        name="html_cleaner",
        category="parser",
        version="1.0.0",
        description="Strips HTML tags and extracts readable text",
        config_schema={
            "min_text_length": {
                "type": "int",
                "default": 50,
                "description": "Minimum chars for valid extraction",
            },
        },
    )

    async def run(
        self, item: WorkflowItem, context: RunContext
    ) -> PluginResult:
        raw = item.raw_content or ""
        if not raw.strip():
            return PluginResult(
                success=True,
                item=item,
                logs=["html_cleaner: empty content, skipping"],
            )

        try:
            cleaned = self._extract_text(raw)
            min_len = self.config.get("min_text_length", 50)

            if len(cleaned) < min_len:
                item.cleaned_text = cleaned
                return PluginResult(
                    success=True,
                    item=item,
                    logs=[f"html_cleaner: short text ({len(cleaned)} chars)"],
                )

            item.cleaned_text = cleaned
            return PluginResult(
                success=True,
                item=item,
                logs=[f"html_cleaner: extracted {len(cleaned)} chars"],
            )
        except Exception as exc:
            return PluginResult(
                success=False,
                item=item,
                error=f"HTML cleaning failed: {exc}",
            )

    def _extract_text(self, raw_html: str) -> str:
        """Multi-layer text extraction."""
        # Try readability first (if installed)
        try:
            from readability import Document
            doc = Document(raw_html)
            summary_html = doc.summary()
            return self._strip_tags(summary_html)
        except ImportError:
            pass
        except Exception:
            pass  # readability can fail on malformed HTML

        # Fallback: regex-based extraction
        return self._strip_tags(raw_html)

    @staticmethod
    def _strip_tags(text: str) -> str:
        """Remove HTML tags, decode entities, normalise whitespace."""
        # Remove script and style blocks entirely
        text = re.sub(
            r"<(script|style)[^>]*>.*?</\1>",
            "", text, flags=re.DOTALL | re.IGNORECASE,
        )
        # Remove all HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Decode HTML entities
        text = html.unescape(text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text
