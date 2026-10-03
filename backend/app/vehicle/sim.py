"""Built-in simulator: a virtual multirotor behind the VehicleLink interface.

It plays the role of the autopilot. It executes the same mission items a real
drone receives, holds position, obeys commands, drains a battery, enforces the
fence and applies the failsafe actions it was given. It is deliberately simple
physics (velocity-controlled point mass with acceleration and turn-rate limits),
fast and repeatable, so it can be stepped by tests and run faster than real time.
"""

import asyncio
import math
import random
import time
from collections.abc import Sequence
from contextlib import suppress
from datetime import datetime, timedelta

from pydantic import BaseModel

from app.core.conventions import LocalFrame, bearing_from_enu, heading_diff, utc_now, wrap_heading
from app.core.geometry import point_in_polygon
from app.vehicle.link import (
    NAV_KINDS,
    OK,
    CommandResult,
    EventKind,
    FailsafeAction,
    FlightMode,
    GpsFix,
    MissionItem,
    MissionItemKind,
    SafetyConfig,
    Severity,
    VehicleEvent,
    VehicleKind,
    VehicleLink,
    VehicleState,
    refused,
)

G = 9.81
WP_RADIUS_M = 0.6
ALT_TOLERANCE_M = 0.3
MANUAL_INPUT_TIMEOUT_S = 0.7
GROUND_IDLE_DISARM_S = 20.0


class SimOptions(BaseModel):
    home_lat: float = 12.9716
    home_lon: float = 77.5946
    home_alt_amsl_m: float = 900.0
    speedup: float = 1.0
    battery_start_pct: float = 100.0
    endurance_min: float = 18.0
    cruise_speed_mps: float = 5.0
    max_speed_mps: float = 10.0
    climb_rate_mps: float = 2.5
    descent_rate_mps: float = 1.5
    accel_mps2: float = 2.5
    yaw_rate_dps: float = 90.0
    gps_noise_m: float = 0.0
    wind_mps: float = 0.0
    wind_from_deg: float = 0.0
    tick_hz: float = 20.0
    seed: int = 1


class KinematicSim(VehicleLink):
    kind = VehicleKind.SIM

    def __init__(self, options: SimOptions | None = None) -> None:
        super().__init__()
        self.options = options or SimOptions()
        self.description = "Built-in simulator"
        o = self.options
        self.frame = LocalFrame(o.home_lat, o.home_lon, o.home_alt_amsl_m)
        self.safety = SafetyConfig()
        self._rng = random.Random(o.seed)

        self.t = 0.0  # simulated seconds since connect
        self._epoch = utc_now()
        self.e = self.n = self.u = 0.0
        self.ve = self.vn = self.vu = 0.0
        self.heading = 0.0
        self.roll = self.pitch = 0.0
        self.gimbal_pitch = -90.0
        self.mode = FlightMode.STANDBY
        self.armed = False
        self.battery_pct = o.battery_start_pct
        self.gps_ok = True

        self.items: list[MissionItem] = []
        self.seq: int | None = None
        self.speed_sp = o.cruise_speed_mps
        self.trigger_dist = 0.0
        self._since_capture = 0.0
        self.captures = 0
        self._hold_until: float | None = None
        self._mission_done = False

        self.fence: list[tuple[float, float]] = []
        self.fence_max_alt = 0.0
        self._takeoff_alt = 0.0
        self._after_takeoff = FlightMode.HOLD
        self._guided: tuple[float, float, float] | None = None
        self._resume_mode: FlightMode | None = None
        self._manual = (0.0, 0.0, 0.0, 0.0)
        self._manual_until = 0.0
        self._rtl_phase = 0
        self._armed_idle_since: float | None = None
        self._noise = (0.0, 0.0)
        self._moved = 0.0
        self._link_blackout_until = 0.0

        self._warned_battery = False
        self._failsafe_latched: set[str] = set()
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------ lifecycle
    async def connect(self) -> None:
        self._task = asyncio.create_task(self._run())
        self._event(EventKind.LINK, "Simulator connected")

    async def disconnect(self) -> None:
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        period = 1.0 / self.options.tick_hz
        last = time.monotonic()
        emit_toggle = False
        while True:
            await asyncio.sleep(period)
            now = time.monotonic()
            dt = min(now - last, 0.25) * self.options.speedup
            last = now
            # Sub-step so a high speed-up cannot tunnel through waypoints.
            steps = max(1, math.ceil(dt / 0.05))
            for _ in range(steps):
                self.step(dt / steps)
            emit_toggle = not emit_toggle
            if emit_toggle and now >= self._link_blackout_until:
                self._emit_state()

    # ------------------------------------------------------------------ helpers
    def now(self) -> datetime:
        """Simulated time. Runs faster than the wall clock when the simulation is sped up,
        so a recorded flight has the same durations whatever speed it was run at."""
        return self._epoch + timedelta(seconds=round(self.t, 3))

    @property
    def in_air(self) -> bool:
        return self.u > 0.05

    def _event(
        self,
        kind: EventKind,
        message: str,
        severity: Severity = Severity.INFO,
        **data: object,
    ) -> None:
        if self._on_event:
            self._on_event(
                VehicleEvent(
                    time=self.now(), kind=kind, severity=severity, message=message, data=data
                )
            )

    def _set_mode(self, mode: FlightMode) -> None:
        if mode != self.mode:
            self.mode = mode
            self._event(EventKind.MODE_CHANGE, f"Mode {mode.value.upper()}", mode=mode.value)

    def state(self) -> VehicleState:
        o = self.options
        ne, nn = self._noise
        lat, lon, _ = self.frame.to_geodetic(self.e + ne, self.n + nn, 0.0)
        wp_dist = None
        if self.mode == FlightMode.AUTO and self.seq is not None and self.seq < len(self.items):
            item = self.items[self.seq]
            if item.lat is not None and item.lon is not None:
                te, tn = self.frame.to_en(item.lat, item.lon)
                wp_dist = math.hypot(te - self.e, tn - self.n)
        return VehicleState(
            time=self.now(),
            lat=lat,
            lon=lon,
            alt_rel_m=round(self.u, 3),
            alt_amsl_m=round(o.home_alt_amsl_m + self.u, 3),
            vel_north_mps=round(self.vn, 3),
            vel_east_mps=round(self.ve, 3),
            vel_up_mps=round(self.vu, 3),
            groundspeed_mps=round(math.hypot(self.ve, self.vn), 3),
            roll_deg=round(self.roll, 2),
            pitch_deg=round(self.pitch, 2),
            heading_deg=round(wrap_heading(self.heading), 2),
            gimbal_pitch_deg=self.gimbal_pitch,
            battery_pct=round(self.battery_pct, 2),
            battery_v=round(14.0 + 2.8 * self.battery_pct / 100.0, 2),
            battery_a=round(self._load() * 18.0, 1) if self.armed else 0.0,
            gps_fix=GpsFix.FIX_3D if self.gps_ok else GpsFix.NONE,
            satellites=16 if self.gps_ok else 0,
            hdop=0.7 if self.gps_ok else None,
            mode=self.mode,
            mode_raw=self.mode.value.upper(),
            armed=self.armed,
            in_air=self.in_air,
            mission_seq=self.seq,
            mission_count=len(self.items),
            wp_dist_m=wp_dist,
            home_lat=o.home_lat,
            home_lon=o.home_lon,
            rc_ok=None,
            ekf_ok=self.gps_ok,
            captures=self.captures,
        )

    def _emit_state(self) -> None:
        if self._on_state:
            self._on_state(self.state())

    def _load(self) -> float:
        """Battery load relative to cruise."""
        if not self.armed:
            return 0.0
        if not self.in_air:
            return 0.1
        speed = math.hypot(self.ve, self.vn) / self.options.cruise_speed_mps
        climb = max(0.0, self.vu) / self.options.climb_rate_mps
        wind = self.options.wind_mps / 15.0
        return 0.9 + 0.1 * speed * speed + 0.5 * climb + wind

    # ------------------------------------------------------------------ physics
    def step(self, dt: float) -> None:
        """Advance the simulation by dt simulated seconds."""
        self.t += dt
        o = self.options

        target = (0.0, 0.0, 0.0)  # desired velocity east, north, up
        yaw_rate_cmd: float | None = None

        if self.mode == FlightMode.TAKEOFF:
            target = (0.0, 0.0, self._climb_toward(self._takeoff_alt))
            if abs(self._takeoff_alt - self.u) < ALT_TOLERANCE_M:
                self._set_mode(self._after_takeoff)
        elif self.mode == FlightMode.AUTO:
            target = self._auto_velocity()
        elif self.mode == FlightMode.GUIDED and self._guided:
            target = self._velocity_to(*self._guided, self.speed_sp)
        elif self.mode == FlightMode.MANUAL:
            if time.monotonic() > self._manual_until:
                self._manual = (0.0, 0.0, 0.0, 0.0)
            fwd, right, up, yaw_rate_cmd = self._manual
            h = math.radians(self.heading)
            target = (
                fwd * math.sin(h) + right * math.cos(h),
                fwd * math.cos(h) - right * math.sin(h),
                up,
            )
        elif self.mode == FlightMode.RTL:
            target = self._rtl_velocity()
        elif self.mode == FlightMode.LAND:
            rate = o.descent_rate_mps if self.u > 2.0 else 0.5
            target = (0.0, 0.0, -rate)

        self._integrate(target, yaw_rate_cmd, dt)
        self._battery(dt)
        self._ground(dt)
        self._capture()
        self._failsafes()
        if o.gps_noise_m > 0:
            a = 0.05
            self._noise = (
                self._noise[0] * (1 - a) + self._rng.gauss(0, o.gps_noise_m) * a,
                self._noise[1] * (1 - a) + self._rng.gauss(0, o.gps_noise_m) * a,
            )

    def _climb_toward(self, alt: float) -> float:
        dz = alt - self.u
        limit = self.options.climb_rate_mps if dz > 0 else self.options.descent_rate_mps
        return (
            math.copysign(min(limit, math.sqrt(2 * 1.5 * abs(dz))), dz) if abs(dz) > 0.02 else 0.0
        )

    def _velocity_to(
        self, te: float, tn: float, tu: float, speed: float
    ) -> tuple[float, float, float]:
        de, dn = te - self.e, tn - self.n
        dist = math.hypot(de, dn)
        speed = min(speed, self.safety.max_speed_mps, self.options.max_speed_mps)
        # Slow down so the vehicle can stop at the target.
        v = min(speed, math.sqrt(2 * self.options.accel_mps2 * 0.8 * dist))
        if dist < 0.05:
            return 0.0, 0.0, self._climb_toward(tu)
        return v * de / dist, v * dn / dist, self._climb_toward(tu)

    def _integrate(
        self, target: tuple[float, float, float], yaw_rate_cmd: float | None, dt: float
    ) -> None:
        o = self.options
        self._moved = 0.0
        if not self.in_air and target[2] <= 0:
            self.ve = self.vn = self.vu = 0.0
            self.roll = self.pitch = 0.0
            self.u = 0.0
            return

        # Horizontal acceleration limit
        dve, dvn = target[0] - self.ve, target[1] - self.vn
        dv = math.hypot(dve, dvn)
        max_dv = o.accel_mps2 * dt
        scale = min(1.0, max_dv / dv) if dv > 1e-9 else 0.0
        ae, an = dve * scale / dt, dvn * scale / dt
        self.ve += dve * scale
        self.vn += dvn * scale
        dvu = target[2] - self.vu
        self.vu += max(-3.0 * dt, min(3.0 * dt, dvu))

        # A small part of the wind is never compensated.
        wind_to = math.radians(o.wind_from_deg + 180.0)
        drift = 0.04 * o.wind_mps
        step_e = (self.ve + drift * math.sin(wind_to)) * dt
        step_n = (self.vn + drift * math.cos(wind_to)) * dt
        self.e += step_e
        self.n += step_n
        self._moved = math.hypot(step_e, step_n)
        self.u = max(0.0, self.u + self.vu * dt)

        # Heading follows the track, or the operator's yaw input in manual
        speed = math.hypot(self.ve, self.vn)
        if yaw_rate_cmd is not None:
            self.heading = wrap_heading(self.heading + yaw_rate_cmd * dt)
        elif speed > 0.7 and self.mode in (FlightMode.AUTO, FlightMode.GUIDED, FlightMode.RTL):
            want = bearing_from_enu(self.ve, self.vn)
            turn = heading_diff(want, self.heading)
            step = o.yaw_rate_dps * dt
            self.heading = wrap_heading(self.heading + max(-step, min(step, turn)))

        # Attitude is cosmetic: lean into acceleration and into speed.
        h = math.radians(self.heading)
        a_fwd = ae * math.sin(h) + an * math.cos(h)
        a_right = ae * math.cos(h) - an * math.sin(h)
        v_fwd = self.ve * math.sin(h) + self.vn * math.cos(h)
        v_right = self.ve * math.cos(h) - self.vn * math.sin(h)
        want_pitch = -math.degrees(math.atan2(a_fwd, G)) - 1.2 * v_fwd
        want_roll = math.degrees(math.atan2(a_right, G)) + 1.2 * v_right
        k = min(1.0, 6.0 * dt)
        self.pitch += (want_pitch - self.pitch) * k
        self.roll += (want_roll - self.roll) * k

    def _battery(self, dt: float) -> None:
        drain = 100.0 / (self.options.endurance_min * 60.0) * self._load() * dt
        self.battery_pct = max(0.0, self.battery_pct - drain)

    def _ground(self, dt: float) -> None:
        if self.mode == FlightMode.LAND and not self.in_air:
            self.u = self.ve = self.vn = self.vu = 0.0
            self._set_mode(FlightMode.STANDBY)
            self._disarm("Landed")
        if self.armed and not self.in_air and self.mode == FlightMode.STANDBY:
            if self._armed_idle_since is None:
                self._armed_idle_since = self.t
            elif self.t - self._armed_idle_since > GROUND_IDLE_DISARM_S:
                self._disarm("Disarmed after idling on the ground")
        else:
            self._armed_idle_since = None

    def _disarm(self, why: str) -> None:
        if self.armed:
            self.armed = False
            self.trigger_dist = 0.0
            self._event(EventKind.DISARMED, why)

    # ------------------------------------------------------------------ mission
    def _auto_velocity(self) -> tuple[float, float, float]:
        while self.seq is not None and self.seq < len(self.items):
            item = self.items[self.seq]
            if item.kind == MissionItemKind.SET_SPEED:
                self.speed_sp = item.value
            elif item.kind == MissionItemKind.CAMERA_TRIGGER_DISTANCE:
                self.trigger_dist = item.value
                self._since_capture = item.value  # take one photo immediately
            elif item.kind == MissionItemKind.GIMBAL_PITCH:
                self.gimbal_pitch = item.value
            elif item.kind == MissionItemKind.TAKEOFF:
                alt = item.alt_rel_m or 0.0
                if self.u < alt - ALT_TOLERANCE_M:
                    return 0.0, 0.0, self._climb_toward(alt)
            elif item.kind == MissionItemKind.WAYPOINT:
                te, tn = self.frame.to_en(item.lat, item.lon)
                tu = item.alt_rel_m if item.alt_rel_m is not None else self.u
                at_point = (
                    math.hypot(te - self.e, tn - self.n) < WP_RADIUS_M
                    and abs(tu - self.u) < ALT_TOLERANCE_M
                )
                if not at_point:
                    self._hold_until = None
                    return self._velocity_to(te, tn, tu, self.speed_sp)
                if item.value > 0:
                    if self._hold_until is None:
                        self._hold_until = self.t + item.value
                    if self.t < self._hold_until:
                        return self._velocity_to(te, tn, tu, self.speed_sp)
                    self._hold_until = None
            elif item.kind == MissionItemKind.RTL:
                self._reached(item)
                self._finish_mission()
                self._start_rtl()
                return 0.0, 0.0, 0.0
            elif item.kind == MissionItemKind.LAND:
                self._reached(item)
                self._finish_mission()
                self._set_mode(FlightMode.LAND)
                return 0.0, 0.0, 0.0
            self._reached(item)
            self.seq += 1

        # Ran off the end without RTL or LAND: hold where we are.
        self._finish_mission()
        self._set_mode(FlightMode.HOLD)
        return 0.0, 0.0, 0.0

    def _reached(self, item: MissionItem) -> None:
        self._event(EventKind.ITEM_REACHED, f"Item {item.seq} ({item.kind.value})", seq=item.seq)

    def _finish_mission(self) -> None:
        self.trigger_dist = 0.0
        if not self._mission_done:
            self._mission_done = True
            self._event(EventKind.MISSION, "Mission complete", captures=self.captures)

    def _capture(self) -> None:
        if self.trigger_dist <= 0 or self.mode != FlightMode.AUTO or not self.in_air:
            return
        self._since_capture += self._moved
        if self._since_capture >= self.trigger_dist:
            self._since_capture = 0.0
            self.captures += 1
            s = self.state()
            self._event(
                EventKind.CAPTURE,
                f"Photo {self.captures}",
                index=self.captures,
                lat=s.lat,
                lon=s.lon,
                alt_rel_m=s.alt_rel_m,
                heading_deg=s.heading_deg,
                gimbal_pitch_deg=s.gimbal_pitch_deg,
                mission_seq=self.seq,
            )

    # ------------------------------------------------------------------ RTL
    def _start_rtl(self) -> None:
        self._rtl_phase = 0
        self._set_mode(FlightMode.RTL)

    def _rtl_velocity(self) -> tuple[float, float, float]:
        rtl_alt = max(self.safety.rtl_alt_m, 0.0)
        dist_home = math.hypot(self.e, self.n)
        if self._rtl_phase == 0:
            want = max(self.u, rtl_alt) if dist_home > 2.0 else self.u
            if self.u >= want - ALT_TOLERANCE_M:
                self._rtl_phase = 1
            return 0.0, 0.0, self._climb_toward(want)
        if self._rtl_phase == 1:
            if dist_home < WP_RADIUS_M and math.hypot(self.ve, self.vn) < 0.3:
                self._set_mode(FlightMode.LAND)
                return 0.0, 0.0, 0.0
            return self._velocity_to(0.0, 0.0, self.u, self.speed_sp)
        return 0.0, 0.0, 0.0

    # ------------------------------------------------------------------ failsafes
    def _act(self, name: str, action: FailsafeAction, message: str) -> None:
        if name in self._failsafe_latched:
            return
        self._failsafe_latched.add(name)
        self._event(
            EventKind.FAILSAFE,
            f"{message}: {action.value.upper()}",
            Severity.CRITICAL,
            failsafe=name,
            action=action.value,
        )
        if not self.in_air:
            return
        if action == FailsafeAction.RTL:
            self._start_rtl()
        elif action == FailsafeAction.LAND:
            self._set_mode(FlightMode.LAND)
        else:
            self._set_mode(FlightMode.HOLD)

    def _failsafes(self) -> None:
        s = self.safety
        if self.battery_pct <= s.battery_warn_pct and not self._warned_battery:
            self._warned_battery = True
            self._event(
                EventKind.STATUS_TEXT, f"Battery low: {self.battery_pct:.0f}%", Severity.WARNING
            )
        if not self.armed:
            return
        landing = self.mode in (FlightMode.RTL, FlightMode.LAND)
        if self.battery_pct <= s.battery_crit_pct and not landing:
            self._act("battery", s.on_battery_critical, "Battery critical")
        if not self.gps_ok and self.mode != FlightMode.LAND:
            # Without position the only safe automatic actions are to land or hold attitude.
            action = s.on_gps_loss if s.on_gps_loss != FailsafeAction.RTL else FailsafeAction.LAND
            self._act("gps", action, "GPS lost")
        if s.fence_enabled and self.in_air and not landing:
            outside = bool(self.fence) and not point_in_polygon((self.e, self.n), self.fence)
            too_high = self.fence_max_alt > 0 and self.u > self.fence_max_alt + 1.0
            if outside or too_high:
                self._act("fence", s.on_fence_breach, "Geofence breached")
            else:
                self._failsafe_latched.discard("fence")

    # ------------------------------------------------------------------ interface
    async def upload_mission(self, items: Sequence[MissionItem]) -> CommandResult:
        if self.mode == FlightMode.AUTO:
            return refused("Cannot replace the mission while it is being flown")
        self.items = [i.model_copy() for i in items]
        self.seq = None
        self._mission_done = False
        self._event(EventKind.MISSION, f"Mission received: {len(self.items)} items")
        return OK

    async def read_mission(self) -> list[MissionItem]:
        return [i.model_copy() for i in self.items]

    async def upload_fence(
        self, polygon: Sequence[tuple[float, float]], max_alt_m: float
    ) -> CommandResult:
        self.fence = [self.frame.to_en(lat, lon) for lat, lon in polygon]
        self.fence_max_alt = max_alt_m
        self._failsafe_latched.discard("fence")
        return OK

    async def apply_safety(self, safety: SafetyConfig) -> CommandResult:
        self.safety = safety.model_copy()
        return OK

    async def arm(self) -> CommandResult:
        if self.armed:
            return OK
        if not self.gps_ok:
            return refused("Arming refused: no GPS position")
        if self.battery_pct <= self.safety.battery_crit_pct:
            return refused("Arming refused: battery below the critical level")
        self.armed = True
        self._failsafe_latched.clear()
        self._armed_idle_since = None
        self._event(EventKind.ARMED, "Armed")
        return OK

    async def disarm(self) -> CommandResult:
        if self.in_air:
            return refused("Disarm refused: the vehicle is in the air")
        self._disarm("Disarmed")
        self._set_mode(FlightMode.STANDBY)
        return OK

    async def takeoff(self, alt_rel_m: float) -> CommandResult:
        if not self.armed:
            return refused("Takeoff refused: not armed")
        if self.in_air:
            return refused("Takeoff refused: already in the air")
        if not self.safety.min_alt_m <= alt_rel_m <= self.safety.max_alt_m:
            return refused(
                f"Takeoff height must be between {self.safety.min_alt_m:g} "
                f"and {self.safety.max_alt_m:g} m"
            )
        self._takeoff_alt = alt_rel_m
        self._after_takeoff = FlightMode.HOLD
        self._set_mode(FlightMode.TAKEOFF)
        return OK

    async def start_mission(self) -> CommandResult:
        if not self.items:
            return refused("No mission on the vehicle")
        if not self.armed:
            return refused("Mission start refused: not armed")
        first_nav = next((i for i in self.items if i.kind in NAV_KINDS), None)
        if not self.in_air and (first_nav is None or first_nav.kind != MissionItemKind.TAKEOFF):
            return refused("Mission must begin with a takeoff when started from the ground")
        self.seq = 0
        self.captures = 0
        self._mission_done = False
        self._hold_until = None
        self._resume_mode = None
        self._set_mode(FlightMode.AUTO)
        return OK

    async def pause(self) -> CommandResult:
        if not self.in_air:
            return refused("Nothing to pause: the vehicle is on the ground")
        if self.mode in (FlightMode.LAND,):
            return refused("Cannot pause a landing")
        self._resume_mode = self.mode if self.mode == FlightMode.AUTO else None
        self._set_mode(FlightMode.HOLD)
        return OK

    async def resume(self) -> CommandResult:
        if self._resume_mode != FlightMode.AUTO or self.seq is None:
            return refused("No paused mission to resume")
        if not self.in_air:
            return refused("Resume refused: the vehicle is on the ground")
        self._resume_mode = None
        self._set_mode(FlightMode.AUTO)
        return OK

    async def rtl(self) -> CommandResult:
        if not self.in_air:
            return refused("Return refused: the vehicle is on the ground")
        self._start_rtl()
        return OK

    async def land(self) -> CommandResult:
        if not self.in_air:
            return refused("Land refused: the vehicle is on the ground")
        self._set_mode(FlightMode.LAND)
        return OK

    async def goto(self, lat: float, lon: float, alt_rel_m: float) -> CommandResult:
        if not self.in_air:
            return refused("Fly-to refused: take off first")
        if self.mode in (FlightMode.LAND, FlightMode.RTL):
            return refused("Fly-to refused while landing or returning")
        alt = min(max(alt_rel_m, self.safety.min_alt_m), self.safety.max_alt_m)
        e, n = self.frame.to_en(lat, lon)
        self._guided = (e, n, alt)
        self._resume_mode = None
        self._set_mode(FlightMode.GUIDED)
        return OK

    async def set_velocity(
        self, forward_mps: float, right_mps: float, up_mps: float, yaw_rate_dps: float
    ) -> CommandResult:
        if not self.in_air:
            return refused("Manual input ignored: the vehicle is on the ground")
        if self.mode not in (FlightMode.HOLD, FlightMode.GUIDED, FlightMode.MANUAL):
            return refused("Pause the mission before taking manual control")
        limit = min(self.safety.max_speed_mps, self.options.max_speed_mps)
        h = math.hypot(forward_mps, right_mps)
        if h > limit:
            forward_mps, right_mps = forward_mps * limit / h, right_mps * limit / h
        up_mps = max(-self.options.descent_rate_mps, min(self.options.climb_rate_mps, up_mps))
        # Do not let stick input push through the height limits.
        if (self.u >= self.safety.max_alt_m and up_mps > 0) or (
            self.u <= self.safety.min_alt_m and up_mps < 0
        ):
            up_mps = 0.0
        self._manual = (forward_mps, right_mps, up_mps, yaw_rate_dps)
        self._manual_until = time.monotonic() + MANUAL_INPUT_TIMEOUT_S
        self._resume_mode = None
        self._set_mode(FlightMode.MANUAL)
        return OK

    # ------------------------------------------------------------------ test bench controls
    def inject(
        self,
        battery_pct: float | None = None,
        gps_ok: bool | None = None,
        wind_mps: float | None = None,
        wind_from_deg: float | None = None,
        speedup: float | None = None,
        link_blackout_s: float | None = None,
    ) -> None:
        """Change conditions mid-flight to rehearse failures."""
        if battery_pct is not None:
            self.battery_pct = max(0.0, min(100.0, battery_pct))
            if battery_pct > self.safety.battery_warn_pct:
                self._warned_battery = False
        if gps_ok is not None:
            self.gps_ok = gps_ok
            if gps_ok:
                self._failsafe_latched.discard("gps")
        if wind_mps is not None:
            self.options.wind_mps = max(0.0, wind_mps)
        if wind_from_deg is not None:
            self.options.wind_from_deg = wrap_heading(wind_from_deg)
        if speedup is not None:
            self.options.speedup = max(0.1, min(20.0, speedup))
        if link_blackout_s:
            self._link_blackout_until = time.monotonic() + link_blackout_s
            self._act("link", self.safety.on_link_loss, "Link to ground station lost")
            self._failsafe_latched.discard("link")
