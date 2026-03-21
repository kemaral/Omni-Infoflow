"""
Runtime path helpers.

The project uses a single runtime data root for mutable state such as:

- config.json
- db.sqlite
- prompts/
- exports/
- media/

By default this resolves to ``<project-root>/data`` in local development and
``/app/data`` in Docker because the backend code lives under ``/app/backend``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_DATA_DIR = PROJECT_ROOT / "backend" / "data"
DATA_DIR = Path(
    os.environ.get("OMNIFLOW_DATA_DIR", str(PROJECT_ROOT / "data"))
).expanduser()
PROMPTS_DIR = DATA_DIR / "prompts"
EXPORTS_DIR = DATA_DIR / "exports"
MEDIA_DIR = DATA_DIR / "media"

DEFAULT_CONFIG_PATH = DATA_DIR / "config.json"
DEFAULT_DB_PATH = DATA_DIR / "db.sqlite"
DEFAULT_SOUL_PATH = PROMPTS_DIR / "soul.md"
RUNTIME_CONFIG_EXAMPLE_PATH = DATA_DIR / "config.example.json"
PACKAGE_CONFIG_EXAMPLE_PATH = PACKAGE_DATA_DIR / "config.example.json"
PACKAGE_SOUL_PATH = PACKAGE_DATA_DIR / "prompts" / "soul.md"


def ensure_runtime_layout() -> None:
    """Create the runtime data layout and seed bundled defaults."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    _copy_if_missing(PACKAGE_CONFIG_EXAMPLE_PATH, RUNTIME_CONFIG_EXAMPLE_PATH)
    _copy_if_missing(PACKAGE_SOUL_PATH, DEFAULT_SOUL_PATH)


def resolve_runtime_path(path_str: str) -> Path:
    """Resolve configured paths against the runtime data root."""
    path = Path(path_str).expanduser()
    if path.is_absolute():
        return path

    parts = path.parts
    if parts and parts[0] == "data":
        return DATA_DIR.joinpath(*parts[1:])
    return PROJECT_ROOT / path


def _copy_if_missing(source: Path, target: Path) -> None:
    if source.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
