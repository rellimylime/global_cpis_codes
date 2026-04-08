from cpis.common.geo_utils import circle_overlap_ratio, make_grid


def test_circle_overlap_ratio_identity():
    ratio = circle_overlap_ratio(0.0, 0.0, 10.0, 0.0, 0.0, 10.0)
    assert abs(ratio - 1.0) < 1e-6


def test_circle_overlap_ratio_disjoint():
    ratio = circle_overlap_ratio(0.0, 0.0, 5.0, 100.0, 100.0, 5.0)
    assert ratio == 0.0


def test_make_grid_generates_tiles():
    bounds = (-1.0, -1.0, 1.0, 1.0)
    tiles = make_grid(bounds, tile_km=100.0)
    assert len(tiles) > 0

