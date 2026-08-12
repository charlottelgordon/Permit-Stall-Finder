"""Location -- a Google Maps pin at the permit's address, plus the city,
county, and ZIP it's filed under. Always rendered above the show/hide
toggle in streamlit_app.py (never hidden), for the same "immediately
understand where it is" reason the quick-glance card is always visible.

Pure presentation, same rule as every other module under app/: address,
lat/lon, and zip_code are read straight off the raw source row Agent 1
already preserved (see ingestion/permits.py's PERMIT_FIELDS, which
requests primary_address/lat/lon/zip_code specifically for this section --
none of the three is ever read by any Agent 1/2/3 analytical logic). City
and county are not per-row fields in the source dataset: gwh9-jnip is
scoped exclusively to City of Los Angeles Building and Safety permits, so
those two are fixed labels describing the dataset's jurisdiction, not
values looked up (or guessed) per permit.

The map is a Google Maps iframe embed via maps.google.com's public
"output=embed" endpoint -- the same no-API-key, no-billing-account embed
mechanism every free map-embed generator has used since Google introduced
it; not a Maps JavaScript API integration. A plain "Open in Google Maps"
link sits underneath in case a user's browser blocks third-party iframes.
"""

from __future__ import annotations

import streamlit as st

from i18n import t
from permit_stall_finder.orchestration.pipeline import PermitAnalysisResult


def _coordinates(result: PermitAnalysisResult) -> tuple[float, float] | None:
    snapshot = result.journey.latest_snapshot
    if snapshot is None:
        return None
    lat_raw, lon_raw = snapshot.raw.get("lat"), snapshot.raw.get("lon")
    if lat_raw in (None, "") or lon_raw in (None, ""):
        return None
    try:
        return float(lat_raw), float(lon_raw)
    except (TypeError, ValueError):
        # Source data occasionally carries an unparseable coordinate --
        # this is a presentation gap, not something to raise on, so the
        # rest of the page still renders.
        return None


def _zip_code(result: PermitAnalysisResult) -> str | None:
    snapshot = result.journey.latest_snapshot
    if snapshot is None:
        return None
    zip_code = snapshot.raw.get("zip_code")
    return str(zip_code) if zip_code not in (None, "") else None


def google_maps_embed_url(lat: float, lon: float, *, zoom: int = 16) -> str:
    return f"https://maps.google.com/maps?q={lat},{lon}&z={zoom}&output=embed"


def google_maps_link_url(lat: float, lon: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"


def render(result: PermitAnalysisResult) -> None:
    coords = _coordinates(result)
    zip_code = _zip_code(result)

    if coords is None:
        # No silent placeholder map centered on nowhere -- if the source
        # row has no coordinates, say so rather than showing something
        # that looks like a located pin at (0, 0).
        st.caption(t("map_unavailable"))
    else:
        lat, lon = coords
        st.iframe(google_maps_embed_url(lat, lon), height=280)
        st.caption(f"[{t('open_in_google_maps')}]({google_maps_link_url(lat, lon)})")

    location_bits = [t("city_label"), t("county_label")]
    if zip_code:
        location_bits.append(f"{t('zip_prefix')} {zip_code}")
    st.caption(" · ".join(location_bits))

