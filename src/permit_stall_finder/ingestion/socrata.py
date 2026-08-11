"""Minimal Socrata (SODA2) client. Stdlib only — no requests, no app token
required at this query volume. Every query requests the system columns
(:id, :created_at, :updated_at) so callers can carry real source provenance."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone

USER_AGENT = "permit-stall-finder/0.1"

SYSTEM_COLUMNS = [":id", ":created_at", ":updated_at"]


def normalize_permit(permit_number: str) -> str:
    """The one normalization rule this project uses anywhere: strip every
    non-alphanumeric character and uppercase. Confirmed sufficient for
    joining gwh9-jnip.permit_nbr (dash-separated) against 9w5z-rg2h.permit
    (mixed dash/space-separated) — see research/DATASET_VALIDATION.md §9a."""
    return re.sub(r"[^A-Z0-9]", "", permit_number.upper())


def query(dataset_id: str, params: dict[str, str], base_url: str) -> list[dict]:
    url = f"{base_url}/{dataset_id}.json?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def select_with_system_columns(select_fields: list[str]) -> str:
    return ",".join(SYSTEM_COLUMNS + select_fields)


def parse_date(value: str | None) -> date | None:
    """Socrata calendar_date fields, e.g. "2020-11-16T00:00:00.000"."""
    if not value:
        return None
    return date.fromisoformat(value[:10])


def parse_datetime(value: str | None) -> datetime | None:
    """Socrata system timestamps, e.g. "2026-08-10T15:10:43.831Z" (always
    UTC — the "Z" suffix). Returns a timezone-aware UTC datetime; never a
    naive one, so it can't later be silently misinterpreted as local time
    by a storage layer that doesn't track tzinfo (see storage/db.py)."""
    if not value:
        return None
    v = value[:-1] if value.endswith("Z") else value
    return datetime.fromisoformat(v).replace(tzinfo=timezone.utc)
