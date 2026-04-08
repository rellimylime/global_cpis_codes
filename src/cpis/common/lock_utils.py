"""Lightweight file-lock with stale lock recovery."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .file_utils import load_json, save_json
from .time_utils import utc_now_iso


@contextmanager
def manifest_lock(lock_path: str | Path, stale_seconds: int = 7200, force: bool = False) -> Iterator[None]:
    p = Path(lock_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    now_ts = int(__import__("time").time())

    if p.exists():
        data = load_json(p, {})
        lock_ts = int(data.get("timestamp", 0))
        age = max(0, now_ts - lock_ts)
        if not force and age <= int(stale_seconds):
            owner = data.get("pid", "unknown")
            raise RuntimeError(
                f"Lock already held: {p} (pid={owner}, age_seconds={age}). "
                "Use --force-lock or wait for stale timeout."
            )

    payload = {"pid": os.getpid(), "timestamp": now_ts, "acquired_at": utc_now_iso()}
    save_json(p, payload)
    try:
        yield
    finally:
        if p.exists():
            p.unlink()

