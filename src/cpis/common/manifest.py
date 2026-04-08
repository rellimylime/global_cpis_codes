"""Manifest helpers for resumable jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .file_utils import load_json, save_json
from .time_utils import utc_now_iso


def load_manifest(path: str | Path, default_payload: dict[str, Any]) -> dict[str, Any]:
    payload = load_json(path, default_payload)
    payload.setdefault("updated_at", None)
    return payload


def save_manifest(path: str | Path, payload: dict[str, Any]) -> None:
    payload["updated_at"] = utc_now_iso()
    save_json(path, payload)


def tile_status_counts(tiles: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in tiles.values():
        status = str(row.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return counts

