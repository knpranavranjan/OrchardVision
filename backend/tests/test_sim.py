import asyncio
import math

import pytest

from app.mission.compiler import compile_plan
from app.vehicle.link import EventKind, FailsafeAction, FlightMode, SafetyConfig
from tests.helpers import FRAME, make_sim, rect, run, survey_plan


def go(coro):
    return asyncio.run(coro)


def airborne(alt=20.0, **options):
    """A simulator armed, taken off and holding at alt."""
    sim, rec = make_sim(**options)
    assert go(sim.arm()).accepted
    assert go(sim.takeoff(alt)).accepted
    run(sim, lambda: sim.mode == FlightMode.HOLD, 60)
    return sim, rec


def test_commands_are_refused_when_they_make_no_sense():
    sim, _ = make_sim()
    assert not go(sim.takeoff(20)).accepted  # not armed
    assert not go(sim.start_mission()).accepted  # no mission
    assert not go(sim.rtl()).accepted  # on the ground
    assert not go(sim.goto(12.972, 77.595, 20)).accepted
    go(sim.arm())
    assert not go(sim.takeoff(500)).accepted  # above the height limit
    sim.inject(gps_ok=False)
    go(sim.disarm())
    assert "GPS" in go(sim.arm()).message


def test_takeoff_climbs_to_height_and_holds():
    sim, rec = airborne(20)
    assert sim.u == pytest.approx(20, abs=0.3)
    assert math.hypot(sim.e, sim.n) < 0.1
    assert rec.of(EventKind.ARMED) and sim.armed
    assert not go(sim.disarm()).accepted  # never in the air


def test_flies_a_survey_mission_end_to_end():
    plan = survey_plan()
    compiled = compile_plan(plan)
    sim, rec = make_sim()
    go(sim.apply_safety(plan.safety))
    go(sim.upload_fence([p.tuple() for p in plan.geofence], plan.safety.max_alt_m))
    assert go(sim.upload_mission(compiled.items)).accepted
    assert go(sim.read_mission()) == compiled.items

    go(sim.arm())
    assert go(sim.start_mission()).accepted
    track = []

    def done():
        track.append((sim.e, sim.n, sim.u))
        return not sim.armed

    seconds = run(sim, done, 1800)

    # Landed at home, disarmed, no failsafe
    assert math.hypot(sim.e, sim.n) < 1.0 and sim.u == 0
    assert sim.mode == FlightMode.STANDBY
    assert not rec.of(EventKind.FAILSAFE)
    assert rec.of(EventKind.MISSION)[-1].message == "Mission complete"

    # Every item was reached, in order
    reached = [e.data["seq"] for e in rec.of(EventKind.ITEM_REACHED)]
    assert reached == list(range(len(compiled.items)))

    # Photos: one every 5 m along each 60 m line
    captures = rec.of(EventKind.CAPTURE)
    assert abs(len(captures) - compiled.stats.photos) <= compiled.stats.lines
    for c in captures:
        e, n = FRAME.to_en(c.data["lat"], c.data["lon"])
        assert 9 <= e <= 111 and 9 <= n <= 71
        assert c.data["alt_rel_m"] == pytest.approx(25, abs=0.5)
        assert c.data["gimbal_pitch_deg"] == -90

    # It flew at survey height, never above the limit, never outside the fence
    assert max(u for _, _, u in track) < 31
    assert all(-20 <= e <= 130 and -20 <= n <= 90 for e, n, _ in track)

    # The planner's estimate is close to what happened
    assert seconds == pytest.approx(compiled.stats.time_s, rel=0.25)
    used = 100 - sim.battery_pct
    assert used == pytest.approx(compiled.stats.battery_pct, rel=0.3)


def test_pause_and_resume():
    plan = survey_plan()
    sim, _ = make_sim()
    go(sim.upload_mission(compile_plan(plan).items))
    go(sim.arm())
    go(sim.start_mission())
    run(sim, lambda: sim.seq is not None and sim.seq >= 5, 600)
    seq = sim.seq
    assert go(sim.pause()).accepted and sim.mode == FlightMode.HOLD
    run(sim, lambda: math.hypot(sim.ve, sim.vn) < 0.05, 30)
    here = (sim.e, sim.n)
    for _ in range(200):
        sim.step(0.05)
    assert math.dist(here, (sim.e, sim.n)) < 0.2  # holds position
    assert go(sim.resume()).accepted and sim.mode == FlightMode.AUTO and sim.seq == seq


def test_return_to_launch_climbs_then_comes_home_and_lands():
    sim, _ = airborne(10)
    go(sim.goto(*FRAME.to_latlon(60, 40), 10))
    run(sim, lambda: math.dist((sim.e, sim.n), (60, 40)) < 1, 120)
    assert go(sim.rtl()).accepted
    heights = []

    def landed():
        heights.append(sim.u)
        return not sim.armed

    run(sim, landed, 300)
    assert max(heights) == pytest.approx(30, abs=0.5)  # the default return height
    assert math.hypot(sim.e, sim.n) < 1.0


def test_manual_input_moves_the_vehicle_and_stops_when_it_stops():
    sim, _ = airborne(15)
    assert go(sim.set_velocity(3.0, 0.0, 0.0, 0.0)).accepted  # forward, facing north
    for _ in range(100):
        sim.step(0.05)
    assert sim.mode == FlightMode.MANUAL
    assert sim.n > 8 and abs(sim.e) < 0.5

    sim._manual_until = 0  # the input stream stops
    run(sim, lambda: math.hypot(sim.ve, sim.vn) < 0.05, 20)
    here = sim.n
    for _ in range(100):
        sim.step(0.05)
    assert sim.n == pytest.approx(here, abs=0.1)

    go(sim.set_velocity(0.0, 0.0, 0.0, 45.0))  # yaw right
    for _ in range(40):
        sim.step(0.05)
    assert sim.heading == pytest.approx(90, abs=3)


def test_manual_input_cannot_exceed_limits():
    sim, _ = airborne(15)
    go(sim.set_velocity(50.0, 0.0, 0.0, 0.0))
    for _ in range(200):
        sim.step(0.05)
    assert math.hypot(sim.ve, sim.vn) <= sim.safety.max_speed_mps + 0.01

    sim2, _ = make_sim()
    go(sim2.upload_mission(compile_plan(survey_plan()).items))
    go(sim2.arm())
    go(sim2.start_mission())
    run(sim2, lambda: sim2.u > 5, 60)
    assert not go(sim2.set_velocity(1, 0, 0, 0)).accepted  # mission must be paused first


def test_fence_breach_triggers_the_configured_action():
    sim, rec = airborne(15)
    go(sim.upload_fence([p.tuple() for p in rect(-30, -30, 30, 30)], 60))
    go(sim.goto(*FRAME.to_latlon(80, 0), 15))
    run(sim, lambda: sim.mode == FlightMode.RTL, 120)
    failsafe = rec.of(EventKind.FAILSAFE)[0]
    assert failsafe.data == {"failsafe": "fence", "action": "rtl"}
    assert sim.e < 34  # stopped just past the fence, not at the target
    run(sim, lambda: not sim.armed, 300)
    assert math.hypot(sim.e, sim.n) < 1.0


def test_critical_battery_and_gps_loss():
    sim, rec = airborne(15)
    sim.inject(battery_pct=29)
    sim.step(0.05)
    assert any("Battery low" in e.message for e in rec.of(EventKind.STATUS_TEXT))
    sim.inject(battery_pct=19)
    sim.step(0.05)
    assert sim.mode == FlightMode.RTL

    sim, rec = airborne(15)
    go(sim.apply_safety(SafetyConfig(on_gps_loss=FailsafeAction.LAND)))
    sim.inject(gps_ok=False)
    sim.step(0.05)
    assert sim.mode == FlightMode.LAND
    assert rec.of(EventKind.FAILSAFE)[0].data["failsafe"] == "gps"
    assert sim.state().gps_fix == "none"


def test_wind_costs_battery_and_drifts_slightly():
    calm, _ = airborne(15)
    windy, _ = airborne(15, wind_mps=8, wind_from_deg=270)
    for _ in range(1200):
        calm.step(0.05)
        windy.step(0.05)
    assert windy.battery_pct < calm.battery_pct
    assert 0 < windy.e < 30  # pushed east, but not blown away


def test_runs_in_real_time_and_emits_telemetry():
    async def scenario():
        sim, rec = make_sim(speedup=10)
        await sim.connect()
        await sim.arm()
        await sim.takeoff(10)
        await asyncio.sleep(1.2)
        await sim.disconnect()
        return sim, rec

    sim, rec = go(scenario())
    assert sim.u == pytest.approx(10, abs=0.5)  # about 12 simulated seconds
    assert len(rec.states) >= 8
    assert rec.states[-1].in_air and rec.states[-1].mode == FlightMode.HOLD
