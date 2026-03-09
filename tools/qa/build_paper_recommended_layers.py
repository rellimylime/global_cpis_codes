import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from shapely.geometry import GeometryCollection
from shapely.ops import unary_union


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_layer(path: Path, run_name: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    if gdf.empty:
        raise ValueError(f"Layer is empty: {path}")
    if gdf.crs is None:
        raise ValueError(f"Layer missing CRS: {path}")
    gdf = gdf[gdf.geometry.notna() & (~gdf.geometry.is_empty)].copy()
    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].buffer(0)
    gdf = gdf[gdf.geometry.notna() & (~gdf.geometry.is_empty)].copy()
    gdf["run_name"] = run_name
    return gdf[["run_name", "geometry"]]


def union_geometry(gdf: gpd.GeoDataFrame):
    if gdf.empty:
        return GeometryCollection()
    return unary_union(gdf.geometry.to_list())


def explode_union(geom, crs) -> gpd.GeoDataFrame:
    union_gdf = gpd.GeoDataFrame({"geometry": [geom]}, crs=crs)
    union_gdf = union_gdf.explode(index_parts=False, ignore_index=True)
    union_gdf = union_gdf[union_gdf.geometry.notna() & (~union_gdf.geometry.is_empty)].copy()
    invalid = ~union_gdf.geometry.is_valid
    if invalid.any():
        union_gdf.loc[invalid, "geometry"] = union_gdf.loc[invalid, "geometry"].buffer(0)
    union_gdf = union_gdf[union_gdf.geometry.notna() & (~union_gdf.geometry.is_empty)].copy()
    return union_gdf


def to_shapefile(gdf: gpd.GeoDataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build comparison and recommended layers from paper-method shapefile runs."
    )
    parser.add_argument(
        "--baseline",
        default="runs/paper_method/tile0816_vector/merged_thr_0p85.shp",
        help="Baseline run shapefile (2048 fixed threshold 0.85).",
    )
    parser.add_argument(
        "--run-1536",
        default="runs/paper_method/tile0816_vector_chip1536/merged_thr_0p85.shp",
        help="Chip1536 fixed threshold 0.85 shapefile.",
    )
    parser.add_argument(
        "--run-1024",
        default="runs/paper_method/tile0816_vector_chip1024_fixed/merged_thr_0p85.shp",
        help="Chip1024 fixed threshold 0.85 shapefile.",
    )
    parser.add_argument(
        "--out-dir",
        default="runs/paper_method/recommended/tile0816_fixed_t085",
        help="Output directory for recommended layers.",
    )
    parser.add_argument(
        "--area-epsg",
        type=int,
        default=6933,
        help="Equal-area EPSG used for area_ha computation.",
    )
    parser.add_argument(
        "--min-area-ha",
        type=float,
        default=0.0,
        help="Drop components smaller than this area in hectares.",
    )
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    run_1536_path = Path(args.run_1536)
    run_1024_path = Path(args.run_1024)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{utc_now_iso()}] Loading input layers...")
    baseline = load_layer(baseline_path, "baseline2048")
    run1536 = load_layer(run_1536_path, "chip1536")
    run1024 = load_layer(run_1024_path, "chip1024")

    target_crs = baseline.crs
    run1536 = run1536.to_crs(target_crs)
    run1024 = run1024.to_crs(target_crs)

    run_layers = {
        "baseline2048": baseline,
        "chip1536": run1536,
        "chip1024": run1024,
    }
    run_unions = {name: union_geometry(gdf) for name, gdf in run_layers.items()}

    print(f"[{utc_now_iso()}] Building union components...")
    all_union = unary_union([g for g in run_unions.values() if not g.is_empty])
    components = explode_union(all_union, target_crs)
    if components.empty:
        raise SystemExit("No union components generated.")
    components["comp_id"] = range(1, len(components) + 1)

    support_counts = []
    support_names = []
    for geom in components.geometry:
        hits = []
        for run_name, run_geom in run_unions.items():
            if run_geom.is_empty:
                continue
            if geom.intersects(run_geom):
                hits.append(run_name)
        support_counts.append(len(hits))
        support_names.append(",".join(hits))
    components["supp_n"] = support_counts
    components["supp_set"] = support_names
    components["new_2048"] = [
        int(not geom.intersects(run_unions["baseline2048"])) for geom in components.geometry
    ]

    comp_area = components.to_crs(args.area_epsg).geometry.area / 10000.0
    components["area_ha"] = comp_area.round(4)
    if args.min_area_ha > 0:
        components = components[components["area_ha"] >= args.min_area_ha].copy()

    layer_union = components.copy()
    layer_consensus2 = components[components["supp_n"] >= 2].copy()
    layer_consensus3 = components[components["supp_n"] >= 3].copy()
    layer_new_vs_2048 = components[components["new_2048"] == 1].copy()
    layer_singleton = components[components["supp_n"] == 1].copy()

    print(f"[{utc_now_iso()}] Writing shapefiles...")
    out_union = out_dir / "fixed_t085_union_components.shp"
    out_consensus2 = out_dir / "fixed_t085_consensus_support2.shp"
    out_consensus3 = out_dir / "fixed_t085_consensus_support3.shp"
    out_new = out_dir / "fixed_t085_new_vs_2048.shp"
    out_singleton = out_dir / "fixed_t085_singleton_support1.shp"

    to_shapefile(layer_union, out_union)
    to_shapefile(layer_consensus2, out_consensus2)
    to_shapefile(layer_consensus3, out_consensus3)
    to_shapefile(layer_new_vs_2048, out_new)
    to_shapefile(layer_singleton, out_singleton)

    summary = {
        "generated_at": utc_now_iso(),
        "inputs": {
            "baseline": str(baseline_path.resolve()),
            "run_1536": str(run_1536_path.resolve()),
            "run_1024": str(run_1024_path.resolve()),
        },
        "output_dir": str(out_dir.resolve()),
        "input_raw_counts": {name: int(len(gdf)) for name, gdf in run_layers.items()},
        "component_counts": {
            "union_components": int(len(layer_union)),
            "consensus_support2": int(len(layer_consensus2)),
            "consensus_support3": int(len(layer_consensus3)),
            "new_vs_2048": int(len(layer_new_vs_2048)),
            "singleton_support1": int(len(layer_singleton)),
        },
        "area_ha": {
            "union_total": float(layer_union["area_ha"].sum()),
            "consensus_support2_total": float(layer_consensus2["area_ha"].sum()),
            "consensus_support3_total": float(layer_consensus3["area_ha"].sum()),
            "new_vs_2048_total": float(layer_new_vs_2048["area_ha"].sum()),
            "singleton_support1_total": float(layer_singleton["area_ha"].sum()),
        },
    }
    summary_path = out_dir / "summary_fixed_t085.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"[{utc_now_iso()}] Done.")
    print(f"  Summary: {summary_path}")
    print(f"  Union components: {out_union}")
    print(f"  Consensus (>=2): {out_consensus2}")
    print(f"  Consensus (=3): {out_consensus3}")
    print(f"  New vs baseline2048: {out_new}")
    print(f"  Singleton (support=1): {out_singleton}")


if __name__ == "__main__":
    main()
