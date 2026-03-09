"""Simple structured logger."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .time_utils import utc_now_iso


def build_logger(log_path: str | Path | None = None) -> Callable[[str], None]:
    target: Path | None = Path(log_path) if log_path else None
    if target is not None:
        target.parent.mkdir(parents=True, exist_ok=True)

    def _log(msg: str) -> None:
        line = f"[{utc_now_iso()}] {msg}"
        print(line, flush=True)
        if target is not None:
            with target.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    return _log

