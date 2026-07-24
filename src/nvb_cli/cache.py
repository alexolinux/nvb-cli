"""Disk cache for probe results (avoids testing 100+ models on every call)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir

from nvb_cli.config import APP_NAME

DEFAULT_TTL_SECONDS = 6 * 60 * 60  # 6 hours: free catalog changes infrequently


def cache_dir() -> Path:
    d = Path(user_cache_dir(APP_NAME))
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_file() -> Path:
    return cache_dir() / "free_models.json"


def load(ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict[str, Any] | None:
    """Returns the cache if it exists and is within TTL, otherwise None."""
    path = cache_file()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    age = time.time() - data.get("checked_at", 0)
    if age > ttl_seconds:
        return None
    return data


def save(results: dict[str, str], base_url: str) -> dict[str, Any]:
    """Saves {model_id: status} in cache along with check timestamp."""
    data = {
        "checked_at": time.time(),
        "base_url": base_url,
        "results": results,
    }
    cache_file().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def clear() -> None:
    path = cache_file()
    if path.exists():
        path.unlink()
