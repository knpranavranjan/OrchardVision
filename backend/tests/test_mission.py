import json
import math

import pytest

from app.core.geometry import point_in_polygon, polygon_area
from app.mission.compiler import compile_plan
from app.mission.export import to_kml, to_qgc_plan, to_waypoints
from app.mission.schema import DEFAULT_CAMERAS, EndAction, MissionPlan, MissionType, WaypointSpec
from app.mission.validate import CropContext, Status, validate_plan
from app.vehicle.link import MissionItemKind as K
from tests.helpers import FRAME, HOME, ONE_INCH, rect, survey_plan


def check(validation, id_):
    return next(c for c in validation.checks if c.id == id_)


def test_camera_geometry_matches_the_worked_example():
    # One-inch camera at 25 m: 0.69 cm per pixel, 37.5 m by 25 m on the ground.
    assert ONE_INCH.gsd_cm(25) == pytest.approx(0.685, abs=0.005)
    assert ONE_INCH.footprint_m(25) == pytest.approx((37.5, 25.0))


def test_survey_lines_cover_the_block():
    compiled = compile_plan(survey_plan())
    s = compiled.stats
    # 70% side overlap of 37.5 m wants 11.25 m; nine lines fit the 100 m width at 11.11 m.
    assert s.lines == 9
    assert s.line_spacing_m == pytest.approx(11.11, abs=0.01)
    assert s.trigger_distance_m == pytest.approx(5.0)
    assert s.area_ha == pytest.approx(0.6, abs=0.001)

    block = [(10, 10), (110, 10), (110, 70), (10, 70)]
    easts = []
    for a, b in compiled.lines:
        (ae, an), (be, bn) = FRAME.to_en(*a), FRAME.to_en(*b)
        assert ae == pytest.approx(be, abs=0.01)  # heading 0: lines run north-south
        assert abs(an - bn) == pytest.approx(60, abs=0.01)
        assert point_in_polygon((ae, (an + bn) / 2), block)
        easts.append(ae)
    # Edge lines sit half a spacing inside, so the block's edges are covered.
    assert min(easts) == pytest.approx(10 + 11.11 / 2, abs=0.01)
    assert max(easts) == pytest.approx(110 - 11.11 / 2, abs=0.01)


def test_lines_alternate_and_start_near_home():
    compiled = compile_plan(survey_plan())
    first = FRAME.to_en(*compiled.lines[0][0])
    corners = [(10, 10), (110, 10), (110, 70), (10, 70)]
    assert math.dist(first, (0, 0)) <= min(math.dist(c, (0, 0)) for c in corners) + 12
    directions = [FRAME.to_en(*b)[1] - FRAME.to_en(*a)[1] > 0 for a, b in compiled.lines]
    assert all(directions[i] != directions[i + 1] for i in range(len(directions) - 1))


def test_angle_turns_the_lines():
    compiled = compile_plan(survey_plan(angle_deg=90))
    for a, b in compiled.lines:
        assert FRAME.to_en(*a)[1] == pytest.approx(FRAME.to_en(*b)[1], abs=0.01)  # east-west
    assert compiled.stats.lines == 6  # 60 m across at 11.25 m wanted


def test_concave_area_gives_separate_segments():
    # A U shape: the notch must not be flown through.
    plan = survey_plan()
    pts = [(0, 0), (90, 0), (90, 60), (60, 60), (60, 20), (30, 20), (30, 60), (0, 60)]
    plan.survey.polygon = [
        type(HOME)(lat=lat, lon=lon) for lat, lon in (FRAME.to_latlon(e, n) for e, n in pts)
    ]
    plan.survey.angle_deg = 0
    plan.geofence = []
    plan.safety.fence_enabled = False
    compiled = compile_plan(plan)
    for a, b in compiled.lines:
        (ae, an), (_, bn) = FRAME.to_en(*a), FRAME.to_en(*b)
        if 30 < ae < 60:
            assert max(an, bn) <= 20.01
    assert compiled.stats.area_ha == pytest.approx(polygon_area(pts) / 1e4, abs=0.001)


def test_items_are_what_the_autopilot_needs():
    compiled = compile_plan(survey_plan())
    kinds = [i.kind for i in compiled.items]
    assert kinds[:3] == [K.TAKEOFF, K.SET_SPEED, K.GIMBAL_PITCH]
    assert kinds[-1] == K.RTL
    assert [i.seq for i in compiled.items] == list(range(len(compiled.items)))
    # Each line is: go to start, camera on, go to end, camera off.
    body = kinds[3:-1]
    assert body == [K.WAYPOINT, K.CAMERA_TRIGGER_DISTANCE] * (len(body) // 2)
    triggers = [i.value for i in compiled.items if i.kind == K.CAMERA_TRIGGER_DISTANCE]
    assert triggers == [5.0, 0.0] * 9
    assert compile_plan(survey_plan()).items == compiled.items  # deterministic


def test_land_ending_goes_home_first():
    plan = survey_plan()
    plan.end_action = EndAction.LAND
    items = compile_plan(plan).items
    assert items[-1].kind == K.LAND
    assert (items[-2].lat, items[-2].lon) == pytest.approx((HOME.lat, HOME.lon), abs=1e-6)


def test_estimate_is_plausible():
    s = compile_plan(survey_plan()).stats
    # 9 lines of 60 m plus cross-overs and transit: several hundred metres at 3 m/s.
    assert 700 < s.distance_m < 900
    assert 5 * 60 < s.time_s < 8 * 60
    assert s.photos == 9 * 13  # 60 m lines, a photo every 5 m, both ends included
    assert s.battery_pct == pytest.approx(s.time_s / (18 * 60) * 100, abs=0.1)
    assert s.flights_needed == 1


def test_validation_passes_a_good_plan():
    plan = survey_plan()
    v = validate_plan(plan, compile_plan(plan), CropContext(crop="papaya", min_gsd_cm=2.0))
    assert v.ok, [c for c in v.checks if c.status == Status.FAIL]
    assert check(v, "gsd").status == Status.PASS
    assert check(v, "fence").status == Status.PASS


def test_validation_blocks_bad_plans():
    plan = survey_plan()
    plan.geofence = rect(-20, -20, 60, 90)  # cuts the block in half
    assert check(validate_plan(plan, compile_plan(plan)), "fence").status == Status.FAIL

    plan = survey_plan()
    plan.geofence = []
    v = validate_plan(plan, compile_plan(plan))
    assert check(v, "fence").status == Status.FAIL and not v.ok

    plan = survey_plan(altitude_m=80)
    assert check(validate_plan(plan, compile_plan(plan)), "altitude").status == Status.FAIL

    plan = survey_plan(speed_mps=12)
    assert check(validate_plan(plan, compile_plan(plan)), "speed").status == Status.FAIL

    # The low-resolution camera at 50 m is too coarse for a 2 cm requirement.
    plan = survey_plan(altitude_m=50)
    plan.camera = DEFAULT_CAMERAS[0]
    v = validate_plan(plan, compile_plan(plan), CropContext(crop="papaya", min_gsd_cm=2.0))
    assert check(v, "gsd").status == Status.FAIL

    plan = survey_plan()
    v = validate_plan(
        plan,
        compile_plan(plan),
        CropContext(crop="papaya", models_ready=False, models_detail="tree model missing"),
    )
    assert check(v, "models").status == Status.FAIL


def test_fence_close_to_route_is_a_warning():
    plan = survey_plan()
    plan.geofence = rect(-5, -5, 112, 72)
    assert check(validate_plan(plan, compile_plan(plan)), "fence").status == Status.WARN


def test_large_area_is_split_into_flights():
    plan = survey_plan()
    plan.survey.polygon = rect(10, 10, 410, 310)  # 12 hectares
    plan.geofence = rect(-20, -20, 430, 330)
    compiled = compile_plan(plan)
    assert compiled.stats.battery_pct > 75
    assert compiled.stats.flights_needed == len(compiled.segments) > 1
    covered = []
    for seg in compiled.segments:
        assert seg.estimate.battery_pct <= 75  # each flight keeps the 25% reserve
        assert seg.items[0].kind == K.TAKEOFF and seg.items[-1].kind == K.RTL
        covered += list(range(seg.first_line, seg.last_line + 1))
    assert covered == list(range(compiled.stats.lines))  # every line flown exactly once
    v = validate_plan(plan, compiled)
    assert check(v, "battery").status == Status.WARN and "flights" in check(v, "battery").detail


def test_waypoint_mission():
    plan = MissionPlan(
        type=MissionType.WAYPOINTS,
        home=HOME,
        takeoff_alt_m=15,
        waypoints=[
            WaypointSpec(lat=lat, lon=lon, alt_m=15, hold_s=h)
            for (lat, lon), h in zip(
                (FRAME.to_latlon(e, n) for e, n in [(20, 0), (20, 30), (0, 30)]),
                [0, 5, 0],
                strict=True,
            )
        ],
        geofence=rect(-20, -20, 50, 60),
    )
    compiled = compile_plan(plan)
    assert [i.kind for i in compiled.items].count(K.WAYPOINT) == 3
    assert compiled.items[4].value == 5  # the hold
    assert validate_plan(plan, compiled).ok
    assert compiled.stats.distance_m == pytest.approx(20 + 30 + 20 + 30, abs=1)

    plan.waypoints = []
    assert not validate_plan(plan, compile_plan(plan)).ok


def test_exports():
    plan = survey_plan()
    compiled = compile_plan(plan)
    qgc = json.loads(to_qgc_plan(plan, compiled.items))
    assert qgc["fileType"] == "Plan" and len(qgc["mission"]["items"]) == len(compiled.items)
    assert qgc["mission"]["items"][0]["command"] == 22
    assert len(qgc["geoFence"]["polygons"][0]["polygon"]) == 4

    wpl = to_waypoints(plan, compiled.items).splitlines()
    assert wpl[0] == "QGC WPL 110" and len(wpl) == len(compiled.items) + 2
    assert wpl[2].split("\t")[3] == "22" and wpl[-1].split("\t")[3] == "20"

    kml = to_kml("Block A", plan, compiled.route)
    assert "<LineString>" in kml and "Survey area" in kml and "Geofence" in kml
