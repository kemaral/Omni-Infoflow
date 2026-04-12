"""
Markdown Export Dispatcher
==========================
Saves processed workflow items as Markdown files on the local filesystem.

Config::

    {
        "output_dir": "data/exports",
        "include_metadata": true
    }
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.core.paths import resolve_runtime_path
from app.models.workflow import PluginResult, RunContext, WorkflowItem
from app.plugins.base import BasePlugin, PluginManifest


class MarkdownExportPlugin(BasePlugin):
    manifest = PluginManifest(
        name="markdown_export",
        category="dispatcher",
        version="1.0.0",
        description="Exports items to local Markdown files",
        config_schema={
            "output_dir": {
                "type": "string",
                "default": "data/exports",
                "description": "Directory to save markdown files",
            },
            "include_metadata": {
                "type": "string",
                "default": "true",
                "description": "Whether to append JSON metadata block",
            },
        },
    )

    async def run(
        self, item: WorkflowItem, context: RunContext
    ) -> PluginResult:
        # Resolve output directory
        rel_dir = self.config.get("output_dir", "data/exports")
        out_path = resolve_runtime_path(rel_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # Generate filename
        safe_title = "".join(
            c for c in (item.title or item.id)
            if c.isalnum() or c in (' ', '-', '_')
        ).strip().replace(' ', '_')
        filename = f"{datetime.now().strftime('%Y%md_%H%M%S')}_{safe_title[:30]}.md"
        filepath = out_path / filename

        # Build content
        lines = [
            f"# {item.title or 'Untitled Workflow Item'}",
            f"\n**Source:** [{item.source_type}]({item.source_uri})",
        ]

        if item.metadata.get("author"):
            lines.append(f"**Author:** {item.metadata['author']}")

        lines.append("\n## Summary")
        if item.summary:
            lines.append(item.summary)
        else:
            lines.append("*No AI summary available.*")

        lines.append("\n## Content")
        if item.cleaned_text:
            lines.append(item.cleaned_text[:2000] + ("..." if len(item.cleaned_text) > 2000 else ""))
        else:
            lines.append("*No cleaned content.*")

        # Optional metadata block
        include_meta = str(self.config.get("include_metadata", "true")).lower() == "true"
        if include_meta and item.metadata:
            lines.append("\n## Metadata")
            lines.append("```json")
            lines.append(json.dumps(item.metadata, indent=2, ensure_ascii=False))
            lines.append("```")

        # Write file
        try:
            filepath.write_text("\n".join(lines), encoding="utf-8")
            item.artifacts["markdown_file"] = str(filepath)
            return PluginResult(
                success=True,
                item=item,
                logs=[f"markdown_export: saved to {filepath}"],
            )
        except Exception as exc:
            return PluginResult(
                success=False,
                item=item,
                error=f"Failed to write markdown file: {exc}",
            )
