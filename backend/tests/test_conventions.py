import json
import math
import random

import pytest

from app.config import REPO_ROOT
from app.core.conventions import (
    LocalFrame,
    bearing_from_enu,
    ecef_to_geodetic,
    geodetic_to_ecef,
    heading_diff,
    to_iso_ms,
    utc_now,
    wrap_heading,
)
from app.core.geometry import (
    is_simple_polygon,
    point_in_polygon,
    polygon_area,
    scanline_segments,
    segment_inside_polygon,
)

VECTORS = json.loads((REPO_ROOT / "contracts" / "conventions_vectors.json").read_text())


def test_one_millidegree_east_at_equator():
    east, north, up = LocalFrame(0.0, 0.0).to_enu(0.0, 0.001)
    assert east == pytest.approx(111.3195, abs=0.001)
    assert north == pytest.approx(0.0, abs=1e-6)
    assert up == pytest.approx(0.0, abs=0.002)  # the tangent plane leaves the ellipsoid


def test_one_millidegree_north_at_equator():
    east, north, _ = LocalFrame(0.0, 0.0).to_enu(0.001, 0.0)
    assert north == pytest.approx(110.574, abs=0.001)
    assert east == pytest.approx(0.0, abs=1e-6)


def test_ecef_round_trip():
    rng = random.Random(7)
    for _ in range(200):
        lat, lon, alt = rng.uniform(-80, 80), rng.uniform(-180, 180), rng.uniform(-100, 5000)
        lat2, lon2, alt2 = ecef_to_geodetic(*geodetic_to_ecef(lat, lon, alt))
        assert lat2 == pytest.approx(lat, abs=1e-10)
        assert lon2 == pytest.approx(lon, abs=1e-10)
        assert alt2 == pytest.approx(alt, abs=1e-4)


def test_enu_round_trip_within_an_orchard():
    frame = LocalFrame(12.9716, 77.5946, 900.0)
    rng = random.Random(11)
    for _ in range(200):
        e, n, u = rng.uniform(-500, 500), rng.uniform(-500, 500), rng.uniform(0, 120)
        e2, n2, u2 = frame.to_enu(*frame.to_geodetic(e, n, u))
        assert math.dist((e, n, u), (e2, n2, u2)) < 1e-4  # a tenth of a millimetre


@pytest.mark.parametrize("case", VECTORS["enu"])
def test_shared_enu_vectors(case):
    frame = LocalFrame(*VECTORS["origin"])
    e, n, u = frame.to_enu(*case["geodetic"])
    assert math.dist((e, n, u), case["enu"]) < 1e-3


@pytest.mark.parametrize("case", VECTORS["heading_diff"])
def test_shared_heading_vectors(case):
    assert heading_diff(case["target"], case["current"]) == pytest.approx(case["diff"])


def test_heading_helpers():
    assert wrap_heading(-10) == 350
    assert wrap_heading(720) == 0
    assert heading_diff(10, 350) == 20
    assert heading_diff(350, 10) == -20
    assert heading_diff(180, 0) == 180
    assert bearing_from_enu(1, 0) == pytest.approx(90)
    assert bearing_from_enu(0, -1) == pytest.approx(180)
    assert bearing_from_enu(-1, 0) == pytest.approx(270)


def test_time_is_utc_milliseconds():
    stamp = to_iso_ms(utc_now())
    assert stamp.endswith("Z")
    assert len(stamp.split(".")[1]) == 4  # three digits and the Z


def test_polygon_geometry():
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert polygon_area(square) == 100
    assert polygon_area(square[::-1]) == 100  # winding does not matter
    assert point_in_polygon((5, 5), square) and not point_in_polygon((15, 5), square)
    assert is_simple_polygon(square)
    assert not is_simple_polygon([(0, 0), (10, 10), (10, 0), (0, 10)])  # a bow-tie
    assert scanline_segments(square, 5) == [(0, 10)]

    u_shape = [(0, 0), (30, 0), (30, 20), (20, 20), (20, 10), (10, 10), (10, 20), (0, 20)]
    assert scanline_segments(u_shape, 15) == [(0, 10), (20, 30)]  # two arms of the U
    assert segment_inside_polygon((5, 5), (25, 5), u_shape)
    assert not segment_inside_polygon((5, 15), (25, 15), u_shape)  # crosses the notch
