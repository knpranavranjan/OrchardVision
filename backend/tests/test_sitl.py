"""The MAVLink link against the real ArduPilot flight code running in software.

Needs the container:  docker compose --profile sitl up -d sitl
Run with:             uv run pytest -m sitl -s

These are slow (the autopilot flies in real time) and are skipped when the
container is not reachable.
"""

import asyncio
import math
import socket

import pytest

from app.core.conventions import LocalFrame
from app.mission.compiler import compile_plan
from app.mission.schema import LatLon, MissionPlan, SurveySpec
from app.vehicle.link import EventKind, FlightMode, VehicleEvent, VehicleKind, VehicleState
from app.vehicle.mavlink import MavlinkLink

pytestmark = pytest.mark.sitl
URL = "tcp:127.0.0.1:5760"


def sitl_reachable() -> bool:
    try:
        socket.create_connection(("127.0.0.1", 5760), timeout=1).close()
        return True
    except OSError:
        return False


class Watch:
    def __init__(self) -> None:
        self.state: VehicleState | None = None
        self.events: list[VehicleEvent] = []
        self.track: list[tuple[float, float, float]] = []

    def on_state(self, s: VehicleState) -> None:
        self.state = s
        if s.in_air:  # before the simulated GPS locks, the autopilot reports 0, 0
            self.track.append((s.lat, s.lon, s.alt_rel_m))

    async def until(self, condition, timeout: float, what: str) -> None:
        for _ in range(int(timeout * 10)):
            if self.state is not None and condition(self.state):
                return
            await asyncio.sleep(0.1)
        raise AssertionError(f"timed out waiting for {what}; last state: {self.state}")


def small_survey(home: LatLon) -> MissionPlan:
    frame = LocalFrame(home.lat, home.lon)

    def box(e0, n0, e1, n1):
        return [
            LatLon(lat=lat, lon=lon)
            for lat, lon in (
                frame.to_latlon(e, n) for e, n in [(e0, n0), (e1, n0), (e1, n1), (e0, n1)]
            )
        ]

    return MissionPlan(
        home=home,
        takeoff_alt_m=15,
        survey=SurveySpec(polygon=box(10, 10, 40, 50), altitude_m=15, speed_mps=5),
        geofence=box(-40, -40, 90, 100),
    )


def test_full_flight_on_the_real_autopilot():
    if not sitl_reachable():
        pytest.skip("SITL container is not running")

    async def scenario() -> None:
        link = MavlinkLink(URL, kind=VehicleKind.SITL)
        watch = Watch()
        link.subscribe(watch.on_state, watch.events.append)
        await link.connect()
        try:
            # The autopilot needs a little while to get its simulated GPS and estimator ready.
            await watch.until(
                lambda s: s.gps_fix.usable and s.ekf_ok and s.home_lat is not None,
                90,
                "GPS, estimator and home",
            )
            home = LatLon(lat=watch.state.home_lat, lon=watch.state.home_lon)
            plan = small_survey(home)
            compiled = compile_plan(plan)

            # Settings, fence, mission; then read the mission back and compare.
            assert (await link.apply_safety(plan.safety)).accepted
            fence = await link.upload_fence(
                [p.tuple() for p in plan.geofence], plan.safety.max_alt_m
            )
            assert fence.accepted, fence.message
            upload = await link.upload_mission(compiled.items)
            assert upload.accepted, upload.message
            back = await link.read_mission()
            assert len(back) == len(compiled.items)
            for sent, got in zip(compiled.items, back, strict=True):
                assert sent.matches(got), (sent, got)

            # Fly it.
            for _ in range(20):  # pre-arm checks can take a few more seconds to clear
                armed = await link.arm()
                if armed.accepted:
                    break
                await asyncio.sleep(3)
            assert armed.accepted, armed.message
            started = await link.start_mission()
            assert started.accepted, started.message
            await watch.until(lambda s: s.mode == FlightMode.AUTO and s.alt_rel_m > 12, 60, "climb")
            await watch.until(lambda s: (s.mission_seq or 0) >= 4, 90, "first survey line")

            # Pause holds position; resume continues the mission.
            assert (await link.pause()).accepted
            await asyncio.sleep(4)
            held = (watch.state.lat, watch.state.lon)
            await asyncio.sleep(3)
            frame = LocalFrame(*held)
            assert math.hypot(*frame.to_en(watch.state.lat, watch.state.lon)) < 2.0
            assert (await link.resume()).accepted
            await watch.until(lambda s: s.mode == FlightMode.AUTO, 10, "resume")

            # Let it finish. The mission's last item returns home and lands; ArduPilot
            # does that inside AUTO, so the thing to wait for is the disarm.
            await watch.until(lambda s: not s.armed, 420, "return, landing and disarm")

            home_frame = LocalFrame(home.lat, home.lon)
            assert math.hypot(*home_frame.to_en(watch.state.lat, watch.state.lon)) < 3.0
            reached = {e.data["seq"] for e in watch.events if e.kind == EventKind.ITEM_REACHED}
            waypoints = {i.seq for i in compiled.items if i.kind == "waypoint"}
            assert waypoints <= reached
            # It stayed at survey height and inside the fence.
            assert max(a for _, _, a in watch.track) < 35
            for lat, lon, _ in watch.track:
                e, n = home_frame.to_en(lat, lon)
                assert -40 <= e <= 90 and -40 <= n <= 100
        finally:
            await link.disconnect()

    asyncio.run(scenario())
