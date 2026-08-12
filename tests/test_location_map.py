"""Tests for app/sections/location_map.py's pure helpers -- no Streamlit
involved. Uses lightweight SimpleNamespace stand-ins for the one path each
helper actually reads (result.journey.latest_snapshot.raw), rather than
running the full pipeline, since none of these functions touch anything
else on PermitAnalysisResult."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from sections import location_map  # noqa: E402


def _fake_result(raw: dict | None):
    snapshot = SimpleNamespace(raw=raw) if raw is not None else None
    journey = SimpleNamespace(latest_snapshot=snapshot)
    return SimpleNamespace(journey=journey)


def test_coordinates_reads_lat_lon_from_raw():
    result = _fake_result({"lat": "34.08759", "lon": "-118.33499"})
    assert location_map._coordinates(result) == (34.08759, -118.33499)


def test_coordinates_none_when_no_snapshot():
    assert location_map._coordinates(_fake_result(None)) is None


def test_coordinates_none_when_lat_or_lon_missing():
    assert location_map._coordinates(_fake_result({"lat": "34.0"})) is None
    assert location_map._coordinates(_fake_result({"lon": "-118.0"})) is None
    assert location_map._coordinates(_fake_result({"lat": "", "lon": ""})) is None


def test_coordinates_none_when_unparseable_without_raising():
    result = _fake_result({"lat": "not-a-number", "lon": "-118.33499"})
    assert location_map._coordinates(result) is None


def test_zip_code_reads_from_raw():
    result = _fake_result({"zip_code": "90038"})
    assert location_map._zip_code(result) == "90038"


def test_zip_code_none_when_missing_or_no_snapshot():
    assert location_map._zip_code(_fake_result({})) is None
    assert location_map._zip_code(_fake_result(None)) is None


def test_google_maps_embed_url_format():
    url = location_map.google_maps_embed_url(34.08759, -118.33499, zoom=16)
    assert url == "https://maps.google.com/maps?q=34.08759,-118.33499&z=16&output=embed"


def test_google_maps_link_url_format():
    url = location_map.google_maps_link_url(34.08759, -118.33499)
    assert url == "https://www.google.com/maps/search/?api=1&query=34.08759,-118.33499"

