"""Select geographically diverse tiles for active-learning label round.

Picks N tiles from the available unlabeled training tiles by maximising
spatial spread (greedy farthest-point), biased toward high-difficulty tiles
with good CPI density.  Writes symlinks to a staging directory ready for
run_paper_inference.py.

Usage
-----
python tools/new_method/select_active_label_tiles.py \
    --tile-stats  runs/new_method/rse2023_2015_v1/splits/2015_ssa_val_v1/tile_stats.gpkg \
    --imagery-dir runs/new_method/rse2023_2015_v1/pilot_2015_ssa/raw \
    --out-root    runs/new_method/rse2023_2015_v1/active_label_v1 \
    --n-tiles 12 \
    --min-stable 15
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = str(ROOT / "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from cpis.common.file_utils import ensure_dir
from cpis.common.logging_utils import build_logger


# Tiles that already have manual labels — exclude from selection
ALREADY_LABELED = {
    "cpis_landsat_2015_tile_000015",
    "cpis_landsat_2015_tile_000022",
    "cpis_landsat_2015_tile_000023",
    "cpis_landsat_2015_tile_000024",
    "cpis_landsat_2015_tile_000026",
    "cpis_landsat_2015_tile_000033",
    "cpis_landsat_2015_tile_000035",
}


def farthest_point_select(
    candidates: gpd.GeoDataFrame,
    n: int,
    seed_idx: int = 0,
) -> list[int]:
    """Greedy farthest-point sampling on (lon, lat) centroids.

    Returns a list of integer positional indices into `candidates`.
    """
    pts = np.column_stack([candidates["centroid_lon"].values,
                           candidates["centroid_lat"].values])
    selected = [seed_idx]
    min_dist = np.full(len(pts), np.inf)

    for _ in range(n - 1):
        last = pts[selected[-1]]
        d = np.sqrt(((pts - last) ** 2).sum(axis=1))
        min_dist = np.minimum(min_dist, d)
        # Break ties toward higher difficulty score
        diff = candidates["difficulty_score"].values
        # Jitter by difficulty to prefer harder tiles at equal distance
        score = min_dist + diff * 0.01
        score[selected] = -np.inf
        selected.append(int(np.argmax(score)))

    return selected


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tile-stats", required=True)
    ap.add_argument("--imagery-dir", required=True)
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--n-tiles", type=int, default=12)
    ap.add_argument("--min-stable", type=int, default=15,
                    help="Minimum stable_count for a tile to be considered")
    ap.add_argument("--max-stable", type=int, default=300,
                    help="Max stable_count — avoids picking 500-pivot monster tiles")
    ap.add_argument("--val-split-file", default="",
                    help="val_tiles.txt to additionally exclude")
    args = ap.parse_args()

    out_root = ensure_dir(Path(args.out_root))
    log = build_logger(out_root / "select_active_label_tiles.log")

    ts = gpd.read_file(args.tile_stats)
    log(f"Loaded tile_stats: {len(ts)} tiles")

    imagery_dir = Path(args.imagery_dir)
    available = {p.stem for p in imagery_dir.glob("*.tif")}
    log(f"Available raw tiles: {len(available)}")

    extra_exclude: set[str] = set()
    if args.val_split_file:
        with open(args.val_split_file) as f:
            extra_exclude = {l.strip() for l in f if l.strip()}
        log(f"Additionally excluding {len(extra_exclude)} val-split tiles")

    exclude = ALREADY_LABELED | extra_exclude

    mask = (
        ts["tile"].isin(available)
        & ~ts["tile"].isin(exclude)
        & ~ts["selected_val"].astype(bool)
        & (ts["stable_count"] >= args.min_stable)
        & (ts["stable_count"] <= args.max_stable)
    )
    pool = ts[mask].reset_index(drop=True)
    log(f"Eligible pool after filters: {len(pool)} tiles "
        f"(min_stable={args.min_stable}, max_stable={args.max_stable})")

    if len(pool) < args.n_tiles:
        log(f"WARNING: only {len(pool)} eligible tiles — returning all")
        chosen_idx = list(range(len(pool)))
    else:
        # Seed from the tile with the highest difficulty score for diversity
        seed = int(pool["difficulty_score"].idxmax())
        chosen_idx = farthest_point_select(pool, args.n_tiles, seed_idx=seed)

    chosen = pool.iloc[chosen_idx].copy()
    log(f"Selected {len(chosen)} tiles:")
    for _, row in chosen.iterrows():
        log(f"  {row['tile']}  stable={row['stable_count']:3d}  "
            f"difficulty={row['difficulty_tier']:6s}  "
            f"lon={row['centroid_lon']:.2f}  lat={row['centroid_lat']:.2f}")

    # Write symlinks into staging dir
    stage_dir = ensure_dir(out_root / "input_tiles")
    for _, row in chosen.iterrows():
        src = imagery_dir / f"{row['tile']}.tif"
        dst = stage_dir / src.name
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        dst.symlink_to(src.resolve())

    log(f"Symlinked {len(chosen)} tiles → {stage_dir}")

    # Save selection manifest
    manifest = {
        "selected_tiles": chosen["tile"].tolist(),
        "tile_stats": chosen[
            ["tile", "stable_count", "difficulty_tier",
             "difficulty_score", "centroid_lon", "centroid_lat",
             "country_name"] if "country_name" in chosen.columns
            else ["tile", "stable_count", "difficulty_tier",
                  "difficulty_score", "centroid_lon", "centroid_lat"]
        ].to_dict(orient="records"),
        "staging_dir": str(stage_dir),
        "imagery_dir": str(imagery_dir),
        "min_stable": args.min_stable,
        "n_tiles": args.n_tiles,
    }
    manifest_path = out_root / "selection_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    log(f"Wrote manifest: {manifest_path}")

    print(f"\nNext step — submit inference:")
    print(f"  CPIS_INFER_IMAGERY={stage_dir} \\")
    print(f"  CPIS_INFER_OUT={out_root}/inference \\")
    print(f"  sbatch tools/new_method/run_inference_pod_gpu.slurm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
