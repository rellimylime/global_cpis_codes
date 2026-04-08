"""Generate file-level inventory for an archive bucket.

Outputs:
- JSON manifest with bucket summaries and per-file metadata
- CSV manifest for quick filtering in spreadsheets/QGIS tables
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def walk_files(root: Path) -> list[dict]:
    rows: list[dict] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        parts = rel.split("/")
        bucket = parts[0] if len(parts) > 1 else "<root_files>"
        st = p.stat()
        rows.append(
            {
                "bucket": bucket,
                "relative_path": rel,
                "size_bytes": int(st.st_size),
                "modified_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return rows


def summarize(rows: list[dict]) -> dict:
    bucket_files = defaultdict(int)
    bucket_bytes = defaultdict(int)
    ext_files = defaultdict(int)
    ext_bytes = defaultdict(int)
    total_bytes = 0

    for r in rows:
        b = str(r["bucket"])
        s = int(r["size_bytes"])
        total_bytes += s
        bucket_files[b] += 1
        bucket_bytes[b] += s

        ext = Path(str(r["relative_path"])).suffix.lower() or "<no_ext>"
        ext_files[ext] += 1
        ext_bytes[ext] += s

    bucket_summary = [
        {"bucket": b, "file_count": bucket_files[b], "size_bytes": bucket_bytes[b]}
        for b in sorted(bucket_files.keys())
    ]
    ext_summary = [
        {"extension": e, "file_count": ext_files[e], "size_bytes": ext_bytes[e]}
        for e in sorted(ext_files.keys())
    ]
    return {
        "file_count": len(rows),
        "size_bytes": int(total_bytes),
        "buckets": bucket_summary,
        "extensions": ext_summary,
    }


def write_csv(rows: list[dict], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["bucket", "relative_path", "size_bytes", "modified_utc"],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    p = argparse.ArgumentParser(description="Generate archive file inventory (JSON + CSV).")
    p.add_argument(
        "--archive-root",
        default="archive/2026-03-09_cleanup",
        help="Archive root directory",
    )
    p.add_argument(
        "--out-json",
        default="archive/2026-03-09_cleanup/ARCHIVE_MANIFEST.json",
        help="JSON output path",
    )
    p.add_argument(
        "--out-csv",
        default="archive/2026-03-09_cleanup/ARCHIVE_MANIFEST.csv",
        help="CSV output path",
    )
    args = p.parse_args()

    archive_root = Path(args.archive_root)
    out_json = Path(args.out_json)
    out_csv = Path(args.out_csv)

    if not archive_root.exists() or not archive_root.is_dir():
        raise SystemExit(f"Archive root does not exist: {archive_root}")

    rows = walk_files(archive_root)
    summary = summarize(rows)

    payload = {
        "generated_at": utc_now_iso(),
        "archive_root": str(archive_root.resolve()),
        "summary": summary,
        "files": rows,
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    write_csv(rows, out_csv)

    print(f"Wrote JSON: {out_json}")
    print(f"Wrote CSV: {out_csv}")
    print(
        f"Files={summary['file_count']} "
        f"SizeGB={summary['size_bytes'] / (1024 ** 3):.3f} "
        f"Buckets={len(summary['buckets'])}"
    )


if __name__ == "__main__":
    main()
