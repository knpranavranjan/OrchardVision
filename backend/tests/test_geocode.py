"""Address search, with the map service replaced so the tests need no internet."""

import urllib.error

import pytest

from app.api import geocode

BENGALURU = {
    "name": "Cubbon Park",
    "display_name": "Cubbon Park, Bengaluru, Karnataka, 560001, India",
    "lat": "12.9763",
    "lon": "77.5929",
    "type": "park",
    "boundingbox": ["12.9690", "12.9830", "77.5880", "77.5990"],
    "address": {
        "city": "Bengaluru",
        "state": "Karnataka",
        "country": "India",
        "postcode": "560001",
    },
}


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    geocode._cache.clear()
    monkeypatch.setattr(geocode, "MIN_INTERVAL_S", 0.0)


def test_search_returns_places_and_caches(offline_client, monkeypatch):
    calls = []

    def fake(url):
        calls.append(url)
        return [BENGALURU]

    monkeypatch.setattr(geocode, "_fetch", fake)
    first = offline_client.get("/api/geocode/search", params={"q": "Cubbon Park"}).json()
    assert first == [
        {
            "name": "Cubbon Park",
            "display_name": "Cubbon Park, Bengaluru, Karnataka, 560001, India",
            "lat": 12.9763,
            "lon": 77.5929,
            "kind": "park",
            "locality": "Bengaluru",
            "state": "Karnataka",
            "country": "India",
            "postcode": "560001",
            "bounds": [12.969, 12.983, 77.588, 77.599],
        }
    ]
    assert "q=Cubbon+Park" in calls[0] and "nominatim.openstreetmap.org/search" in calls[0]
    offline_client.get("/api/geocode/search", params={"q": "Cubbon Park"})
    assert len(calls) == 1  # the second identical search came from the cache


def test_typed_coordinates_need_no_service(offline_client, monkeypatch):
    def boom(url):
        raise AssertionError("coordinates must not be sent to the map service")

    monkeypatch.setattr(geocode, "_fetch", boom)
    for text in ("12.9716, 77.5946", "12.9716 77.5946", " -33.86,151.21 "):
        result = offline_client.get("/api/geocode/search", params={"q": text}).json()
        assert len(result) == 1 and result[0]["kind"] == "coordinates"
    assert result[0]["lat"] == -33.86 and result[0]["lon"] == 151.21
    assert geocode.parse_coordinates("95, 10") is None  # not a latitude
    assert geocode.parse_coordinates("MG Road 12") is None


def test_reverse_keeps_the_point_asked_about(offline_client, monkeypatch):
    monkeypatch.setattr(geocode, "_fetch", lambda url: BENGALURU)
    place = offline_client.get("/api/geocode/reverse", params={"lat": 12.97, "lon": 77.59}).json()
    assert (place["lat"], place["lon"]) == (12.97, 77.59)
    assert place["locality"] == "Bengaluru" and place["country"] == "India"

    geocode._cache.clear()
    monkeypatch.setattr(geocode, "_fetch", lambda url: {"error": "Unable to geocode"})
    empty = offline_client.get("/api/geocode/reverse", params={"lat": 0.0, "lon": 0.0}).json()
    assert empty["name"] == "No address here"


def test_no_internet_is_explained(offline_client, monkeypatch):
    def offline(url):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(geocode, "_fetch", offline)
    r = offline_client.get("/api/geocode/search", params={"q": "anywhere"})
    assert r.status_code == 502 and "internet" in r.json()["detail"]
    assert offline_client.get("/api/geocode/search", params={"q": "x"}).status_code == 422
