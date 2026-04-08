"""Stage a small batch of exported GeoTIFFs into an isolated pilot cache."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cpis.common.file_utils import ensure_dir, save_json  # noqa: E402
from cpis.common.logging_utils import build_logger  # noqa: E402


def _stage_raw(src: Path, dst: Path, *, mode: str) -> str:
    ensure_dir(dst.parent)
    if dst.exists():
        return "exists"

    if mode == "copy":
        shutil.copy2(src, dst)
        return "copied"
    if mode == "symlink":
        dst.symlink_to(src.resolve())
        return "symlinked"
    if mode == "hardlink":
        try:
            dst.hardlink_to(src)
            return "hardlinked"
        except OSError:
            shutil.copy2(src, dst)
            return "copied_fallback"
    raise RuntimeError(f"Unsupported copy mode: {mode}")


def _scale_to_u8(src: Path, dst: Path, *, scale_min: float, scale_max: float) -> None:
    ensure_dir(dst.parent)
    if dst.exists():
        return

    cmd = [
        "gdal_translate",
        "-b",
        "1",
        "-b",
        "2",
        "-b",
        "3",
        "-b",
        "4",
        "-ot",
        "Byte",
        "-scale",
        str(scale_min),
        str(scale_max),
        "0",
        "255",
        str(src),
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gdal_translate failed for {src.name}: {result.stderr.strip()}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input-dir", required=True, help="Directory containing downloaded raw GeoTIFF exports")
    ap.add_argument("--out-root", required=True, help="Pilot batch output root")
    ap.add_argument("--pattern", default="*.tif", help="Glob pattern for input files")
    ap.add_argument(
        "--copy-mode",
        choices=["hardlink", "copy", "symlink"],
        default="hardlink",
        help="How to stage raw files into the pilot cache",
    )
    ap.add_argument("--scale-min", type=float, default=0.0, help="Input lower bound for uint8 scaling")
    ap.add_argument("--scale-max", type=float, default=12520.0, help="Input upper bound for uint8 scaling")
    ap.add_argument("--log-file", default="", help="Optional log file")
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"Input dir not found: {input_dir}")

    out_root = Path(args.out_root)
    raw_dir = ensure_dir(out_root / "raw")
    u8_dir = ensure_dir(out_root / "u8")
    log = build_logger(args.log_file if args.log_file else (out_root / "stage_paper_batch.log"))

    src_paths = sorted(
        p
        for p in input_dir.glob(args.pattern)
        if p.is_file() and p.suffix.lower() == ".tif" and not p.name.endswith("_rgbnir_u8.tif")
    )
    if not src_paths:
        raise RuntimeError(f"No raw GeoTIFFs found in {input_dir} matching pattern={args.pattern}")

    staged_rows: list[dict[str, object]] = []
    batch_list_lines: list[str] = []
    for idx, src_path in enumerate(src_paths, 1):
        raw_dst = raw_dir / src_path.name
        action = _stage_raw(src_path, raw_dst, mode=str(args.copy_mode))
        u8_name = f"{src_path.stem}_rgbnir_u8.tif"
        u8_dst = u8_dir / u8_name
        _scale_to_u8(raw_dst, u8_dst, scale_min=float(args.scale_min), scale_max=float(args.scale_max))
        batch_list_lines.append(str(u8_dst.resolve()))
        row = {
            "index": idx,
            "src": str(src_path.resolve()),
            "raw": str(raw_dst.resolve()),
            "u8": str(u8_dst.resolve()),
            "stage_action": action,
        }
        staged_rows.append(row)
        log(f"[{idx}/{len(src_paths)}] {src_path.name} -> raw={action} u8={u8_dst.name}")

    batch_list_path = out_root / "_batch_list.txt"
    batch_list_path.write_text("\n".join(batch_list_lines) + ("\n" if batch_list_lines else ""), encoding="utf-8")

    payload = {
        "input_dir": str(input_dir.resolve()),
        "out_root": str(out_root.resolve()),
        "raw_dir": str(raw_dir.resolve()),
        "u8_dir": str(u8_dir.resolve()),
        "batch_list": str(batch_list_path.resolve()),
        "copy_mode": str(args.copy_mode),
        "scale_min": float(args.scale_min),
        "scale_max": float(args.scale_max),
        "files": staged_rows,
        "counts": {
            "raw_files": int(len(staged_rows)),
            "u8_files": int(len(staged_rows)),
        },
    }
    save_json(out_root / "stage_summary.json", payload)
    log(f"Wrote stage summary: {out_root / 'stage_summary.json'}")
    log(f"Wrote batch list: {batch_list_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
