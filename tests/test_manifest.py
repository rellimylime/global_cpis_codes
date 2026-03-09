from pathlib import Path

from cpis.common.manifest import load_manifest, save_manifest, tile_status_counts


def test_manifest_roundtrip(tmp_path: Path):
    p = tmp_path / "manifest.json"
    payload = {"version": 1, "tiles": {"a": {"status": "queued"}}}
    save_manifest(p, payload)
    loaded = load_manifest(p, {"version": 1, "tiles": {}})
    assert loaded["version"] == 1
    assert "updated_at" in loaded
    assert loaded["tiles"]["a"]["status"] == "queued"


def test_tile_status_counts():
    counts = tile_status_counts({"a": {"status": "queued"}, "b": {"status": "queued"}, "c": {"status": "failed"}})
    assert counts["queued"] == 2
    assert counts["failed"] == 1

