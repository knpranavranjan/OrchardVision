"""Address search for the map.

Looks places up with OpenStreetMap's Nominatim service. The backend makes the
request, not the browser, so the service's rules are followed in one place: an
identifying User-Agent, at most one request a second, results cached, and
searching only when the operator submits (never as they type).

Needs internet. Coordinates typed as "lat, lon" are handled locally.
"""

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app import __version__

router = APIRouter(prefix="/api/geocode", tags=["geocode"])

NOMINATIM = "https://nominatim.openstreetmap.org"
USER_AGENT = f"OrchardVision-GroundStation/{__version__} (orchard survey planning)"
MIN_INTERVAL_S = 1.0
CACHE_SIZE = 200

_lock = threading.Lock()
_last_call = 0.0
_cache: OrderedDict[str, Any] = OrderedDict()

COORDINATES = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


def _fetch(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def _lookup(path: str, params: dict[str, Any]) -> Any:
    """One polite, cached request to the service."""
    global _last_call
    url = f"{NOMINATIM}/{path}?{urllib.parse.urlencode(params)}"
    with _lock:
        if url in _cache:
            _cache.move_to_end(url)
            return _cache[url]
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            data = _fetch(url)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise HTTPException(
                status_code=502,
                detail="Address search needs an internet connection and could not reach the "
                "map service. You can still type coordinates as: latitude, longitude",
            ) from e
        finally:
            _last_call = time.monotonic()
        _cache[url] = data
        if len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
        return data


def _place(row: dict[str, Any]) -> dict[str, Any]:
    address = row.get("address") or {}
    box = row.get("boundingbox")
    return {
        "name": row.get("name") or (row.get("display_name") or "").split(",")[0],
        "display_name": row.get("display_name", ""),
        "lat": float(row["lat"]),
        "lon": float(row["lon"]),
        "kind": (row.get("type") or row.get("addresstype") or "").replace("_", " "),
        "locality": address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("county")
        or "",
        "state": address.get("state", ""),
        "country": address.get("country", ""),
        "postcode": address.get("postcode", ""),
        # south, north, west, east
        "bounds": [float(v) for v in box] if box and len(box) == 4 else None,
    }


def parse_coordinates(text: str) -> tuple[float, float] | None:
    match = COORDINATES.match(text)
    if not match:
        return None
    lat, lon = float(match.group(1)), float(match.group(2))
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return lat, lon
    return None


@router.get("/search")
def search(q: str = Query(min_length=2, max_length=200)) -> list[dict[str, Any]]:
    """Places matching an address or name, best first. Coordinates are returned as typed."""
    typed = parse_coordinates(q)
    if typed:
        lat, lon = typed
        return [
            {
                "name": "Typed coordinates",
                "display_name": f"{lat:.6f}, {lon:.6f}",
                "lat": lat,
                "lon": lon,
                "kind": "coordinates",
                "locality": "",
                "state": "",
                "country": "",
                "postcode": "",
                "bounds": None,
            }
        ]
    rows = _lookup("search", {"q": q.strip(), "format": "jsonv2", "addressdetails": 1, "limit": 6})
    return [_place(r) for r in rows]


@router.get("/reverse")
def reverse(
    lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)
) -> dict[str, Any]:
    """The address at a point, for "where am I" and for a clicked place."""
    row = _lookup(
        "reverse",
        {"lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "format": "jsonv2", "addressdetails": 1},
    )
    if not isinstance(row, dict) or "lat" not in row:
        return {
            "name": "No address here",
            "display_name": f"{lat:.6f}, {lon:.6f}",
            "lat": lat,
            "lon": lon,
            "kind": "",
            "locality": "",
            "state": "",
            "country": "",
            "postcode": "",
            "bounds": None,
        }
    place = _place(row)
    place["lat"], place["lon"] = lat, lon  # keep the point that was asked about
    return place
