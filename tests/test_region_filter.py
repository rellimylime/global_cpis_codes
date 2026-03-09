from __future__ import annotations

import json

from cpis.common.region_filter import RegionMask


def test_region_mask_contains_polygon(tmp_path):
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0]],
                    ],
                },
            }
        ],
    }
    p = tmp_path / "mask.geojson"
    p.write_text(json.dumps(payload), encoding="utf-8")

    m = RegionMask.from_geojson(p)
    assert m.polygon_count == 1
    assert m.contains(1.0, 1.0)
    assert not m.contains(3.0, 3.0)


def test_region_mask_respects_holes(tmp_path):
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0], [0.0, 0.0]],
                        [[1.0, 1.0], [3.0, 1.0], [3.0, 3.0], [1.0, 3.0], [1.0, 1.0]],
                    ],
                },
            }
        ],
    }
    p = tmp_path / "mask_hole.geojson"
    p.write_text(json.dumps(payload), encoding="utf-8")

    m = RegionMask.from_geojson(p)
    assert m.contains(0.5, 0.5)
    assert not m.contains(2.0, 2.0)
