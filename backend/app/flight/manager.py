"""The flight manager: owns the link to one vehicle and is the only part that commands it.

It relays telemetry to the browser, keeps the pre-flight checklist, uploads and
verifies missions, guards commands, watches the link, and records every flight.
"""

import asyncio
import logging
import shutil
import time
from collections import deque
from contextlib import suppress
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from app.config import Settings
from app.core.conventions import utc_now
from app.db.session import Database
from app.db.tables import Mission
from app.flight.preflight import MANUAL_CHECKS, Preflight, Snapshot, evaluate
from app.flight.recorder import FlightRecorder
from app.mission.service import Evaluated, evaluate_mission
from app.registry import ModelRegistry
from app.vehicle.link import (
    CommandResult,
    EventKind,
    FailsafeAction,
    FlightMode,
    LinkError,
    SafetyConfig,
    Severity,
    VehicleEvent,
    VehicleKind,
    VehicleLink,
    VehicleState,
    refused,
)
from app.vehicle.sim import KinematicSim, SimOptions
from app.ws.hub import Hub

log = logging.getLogger(__name__)


class LinkStatus(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    LOST = "lost"


class ConnectSpec(BaseModel):
    kind: VehicleKind = VehicleKind.SIM
    url: str = "tcp:127.0.0.1:5760"
    baud: int = 57600
    sim: SimOptions | None = None


class ActiveMission(BaseModel):
    """The mission currently on the vehicle."""

    mission_id: int
    name: str
    revision: int
    segment: int
    segments: int
    item_count: int
    verified: bool
    fence_uploaded: bool
    fence_points: int
    safety_applied: bool
    valid: bool
    battery_pct: float
    storage_mb: float
    models_ready: bool | None
    models_detail: str
    safety: SafetyConfig
    route: list[tuple[float, float, float]]
    geofence: list[tuple[float, float]]
    area: list[tuple[float, float]]


class FlightManager:
    def __init__(self, settings: Settings, db: Database, hub: Hub, registry: ModelRegistry) -> None:
        self.settings = settings
        self.db = db
        self.hub = hub
        self.registry = registry
        self.recorder = FlightRecorder(db, settings.record_hz)

        self.link: VehicleLink | None = None
        self.status = LinkStatus.DISCONNECTED
        self.spec: ConnectSpec | None = None
        self.state: VehicleState | None = None
        self.active: ActiveMission | None = None
        self.events: deque[VehicleEvent] = deque(maxlen=200)
        self.confirmations: dict[str, bool] = {}
        self.last_flight_id: int | None = None

        self._state_mono = 0.0
        self._last_broadcast = 0.0
        self._arrivals: deque[float] = deque(maxlen=50)
        self._flying = False
        self._battery_failsafe_sent = False
        self._ticks = 0
        self._watchdog: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        self.recorder.start_worker()
        self.recorder.check()
        self._watchdog = asyncio.create_task(self._watch())

    async def stop(self) -> None:
        if self._watchdog:
            self._watchdog.cancel()
            with suppress(asyncio.CancelledError):
                await self._watchdog
        await self.disconnect()
        await self.recorder.stop_worker()

    async def connect(self, spec: ConnectSpec) -> None:
        async with self._lock:
            if self.link is not None:
                raise LinkError("Already connected. Disconnect first.")
            if spec.kind == VehicleKind.SIM:
                link: VehicleLink = KinematicSim(spec.sim or SimOptions())
            else:
                from app.vehicle.mavlink import MavlinkLink  # imports pymavlink, which is slow

                link = MavlinkLink(spec.url, spec.baud, spec.kind)
            link.subscribe(self._on_state, self._on_event)
            self.status = LinkStatus.CONNECTING
            self._publish_status()
            try:
                await link.connect()
            except LinkError:
                self.status = LinkStatus.DISCONNECTED
                self._publish_status()
                raise
            self.link = link
            self.spec = spec
            self.status = LinkStatus.CONNECTED
            self._state_mono = time.monotonic()
            self.active = None
            self.confirmations = {}
            self._publish_status()

    async def disconnect(self) -> None:
        async with self._lock:
            if self.link is None:
                return
            if self.state is not None and self.state.in_air and self.status == LinkStatus.CONNECTED:
                raise LinkError("The vehicle is in the air. Land it before disconnecting.")
            link, self.link = self.link, None
            await link.disconnect()
            if self._flying:
                self._end_flight()
            self.status = LinkStatus.DISCONNECTED
            self.spec = None
            self.state = None
            self.active = None
            self.confirmations = {}
            self._record_event(EventKind.LINK, "Disconnected")
            self._publish_status()

    # ------------------------------------------------------------------ telemetry in
    def _on_state(self, state: VehicleState) -> None:
        now = time.monotonic()
        self.state = state
        self._state_mono = now
        self._arrivals.append(now)
        if self.status == LinkStatus.LOST:
            self.status = LinkStatus.CONNECTED
            self._record_event(EventKind.LINK, "Link restored", Severity.WARNING)

        if state.armed and not self._flying:
            self._begin_flight(state)
        elif not state.armed and self._flying:
            self.recorder.add_state(state, force=True)  # the record ends on the ground
            self._end_flight()
        self.recorder.add_state(state)

        if now - self._last_broadcast >= 1.0 / self.settings.telemetry_hz:
            self._last_broadcast = now
            self.hub.publish("telemetry", state.model_dump(mode="json"), "vehicle")

    def _on_event(self, event: VehicleEvent) -> None:
        self.events.append(event)
        # The record opens at the arming itself, so "Armed" is its first line.
        if event.kind == EventKind.ARMED and not self._flying and self.state is not None:
            self._begin_flight(self.state)
        self.recorder.add_event(event)
        self.hub.publish("event", event.model_dump(mode="json"), "vehicle")

    def _record_event(
        self, kind: EventKind, message: str, severity: Severity = Severity.INFO, **data: Any
    ) -> None:
        # Stamp with the vehicle's clock when there is one, so the ground station's own
        # entries line up with the vehicle's in a recorded flight (the simulator's clock
        # runs fast when the simulation is sped up).
        when = self.state.time if self.state is not None and self.link is not None else utc_now()
        self._on_event(
            VehicleEvent(time=when, kind=kind, severity=severity, message=message, data=data)
        )

    def _begin_flight(self, state: VehicleState) -> None:
        self._flying = True
        self._battery_failsafe_sent = False
        a = self.active
        meta = {
            "mission_id": a.mission_id if a else None,
            "mission_name": a.name if a else "Manual flight",
            "mission_revision": a.revision if a else None,
            "segment": a.segment if a else None,
            "vehicle_kind": self.link.kind.value if self.link else "",
            "vehicle_description": self.link.description if self.link else "",
            "plan_snapshot": {
                "route": a.route if a else [],
                "geofence": a.geofence if a else [],
                "area": a.area if a else [],
                "home": [state.home_lat, state.home_lon] if state.home_lat is not None else None,
            },
        }
        self.recorder.begin(state, meta)

    def _end_flight(self) -> None:
        self._flying = False
        summary = self.recorder.end()
        self.last_flight_id = self.recorder.flight_id
        self.confirmations = {}
        self._record_event(
            EventKind.MISSION,
            f"Flight ended: {summary['distance_m']:.0f} m flown, {summary['captures']} photos",
            flight_id=self.last_flight_id,
        )

    # ------------------------------------------------------------------ watchdog
    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            try:
                self._tick()
            except Exception:  # the watchdog must survive anything
                log.exception("watchdog tick failed")

    def _tick(self) -> None:
        if self.link is not None and self.status == LinkStatus.CONNECTED:
            age = time.monotonic() - self._state_mono
            if age > self.settings.link_timeout_s:
                self.status = LinkStatus.LOST
                self._record_event(
                    EventKind.LINK,
                    "Link lost: no telemetry. The vehicle is following its own failsafe.",
                    Severity.CRITICAL,
                )
        self._ground_battery_failsafe()
        self.recorder.flush()
        self._ticks += 1
        if self._ticks % 20 == 0:  # every ten seconds
            self.recorder.check()
        self._publish_status()

    def _ground_battery_failsafe(self) -> None:
        """A second line of defence: the autopilot's own battery failsafe is voltage-based,
        so the ground station also acts on the reported percentage while the link is up."""
        s, link = self.state, self.link
        if link is None or s is None or link.kind == VehicleKind.SIM or self._battery_failsafe_sent:
            return
        safety = self.active.safety if self.active else SafetyConfig()
        landing = s.mode in (FlightMode.RTL, FlightMode.LAND)
        if s.in_air and not landing and s.battery_pct is not None:
            if s.battery_pct <= safety.battery_crit_pct:
                self._battery_failsafe_sent = True
                action = safety.on_battery_critical
                self._record_event(
                    EventKind.FAILSAFE,
                    f"Battery critical ({s.battery_pct:.0f}%): ground station commands "
                    f"{action.value.upper()}",
                    Severity.CRITICAL,
                    failsafe="battery",
                    action=action.value,
                )
                command = link.land() if action == FailsafeAction.LAND else link.rtl()
                task = asyncio.ensure_future(command)
                task.add_done_callback(lambda t: t.exception())

    # ------------------------------------------------------------------ status out
    @property
    def telemetry_hz(self) -> float:
        now = time.monotonic()
        recent = [t for t in self._arrivals if now - t <= 2.0]
        return len(recent) / 2.0

    def summary(self) -> dict[str, Any]:
        a = self.active
        pre = self.preflight()
        return {
            "link": self.status.value,
            "kind": self.link.kind.value if self.link else None,
            "description": self.link.description if self.link else "",
            "flying": self._flying,
            "flight_id": self.recorder.flight_id if self._flying else None,
            "last_flight_id": self.last_flight_id,
            "recording": self.recorder.ok,
            "mission": a.model_dump(mode="json", exclude={"route", "geofence", "area"})
            if a
            else None,
            "preflight": {"ready": pre.ready, "blocking": pre.blocking},
            "sim": self.link.options.model_dump() if isinstance(self.link, KinematicSim) else None,
        }

    def full_status(self) -> dict[str, Any]:
        """Everything a browser needs when it opens or reconnects."""
        out = self.summary()
        a = self.active
        out["mission_geometry"] = (
            {"route": a.route, "geofence": a.geofence, "area": a.area} if a else None
        )
        out["state"] = self.state.model_dump(mode="json") if self.state else None
        out["events"] = [e.model_dump(mode="json") for e in self.events]
        return out

    def _publish_status(self) -> None:
        self.hub.publish("status", self.summary(), "vehicle")

    # ------------------------------------------------------------------ pre-flight
    def preflight(self) -> Preflight:
        a = self.active
        data_dir = self.settings.data_dir
        probe = data_dir if data_dir.exists() else data_dir.parent
        snapshot = Snapshot(
            connected=self.status == LinkStatus.CONNECTED,
            kind=self.link.kind if self.link else None,
            state=self.state,
            state_age_s=(time.monotonic() - self._state_mono) if self.state else None,
            telemetry_hz=self.telemetry_hz,
            safety=a.safety if a else SafetyConfig(),
            mission_loaded=a is not None,
            mission_name=f"{a.name} (revision {a.revision})" if a else "",
            mission_valid=a.valid if a else False,
            mission_verified=a.verified if a else False,
            mission_battery_pct=a.battery_pct if a else 0.0,
            fence_uploaded=a.fence_uploaded if a else False,
            fence_points=a.fence_points if a else 0,
            safety_applied=a.safety_applied if a else False,
            models_ready=a.models_ready if a else None,
            models_detail=a.models_detail if a else "",
            storage_free_mb=shutil.disk_usage(probe).free / 1e6,
            storage_needed_mb=a.storage_mb if a else 0.0,
            recording_ok=self.recorder.ok,
            confirmations=self.confirmations,
        )
        return evaluate(snapshot)

    def confirm(self, check_id: str, value: bool) -> None:
        if check_id not in MANUAL_CHECKS:
            raise KeyError(check_id)
        self.confirmations[check_id] = value

    # ------------------------------------------------------------------ mission upload
    def _need_link(self) -> VehicleLink:
        if self.link is None or self.status == LinkStatus.DISCONNECTED:
            raise LinkError("No vehicle connected")
        if self.status == LinkStatus.LOST:
            raise LinkError("The link to the vehicle is down")
        return self.link

    async def upload_mission(self, mission_id: int, segment: int = 0) -> dict[str, Any]:
        """Validate, upload settings, fence and items, then read the items back and compare."""
        link = self._need_link()
        if self.state is not None and self.state.mode == FlightMode.AUTO:
            raise LinkError("A mission is being flown. Pause or land before uploading.")

        def load() -> tuple[Mission, Evaluated]:
            with self.db.session() as s:
                row = s.get(Mission, mission_id)
                if row is None:
                    raise LookupError(f"mission {mission_id} not found")
                return row, evaluate_mission(s, row, self.registry, self.settings.data_dir)

        row, ev = await asyncio.to_thread(load)
        if not ev.validation.ok:
            failed = [c.label for c in ev.validation.checks if c.status == "fail"]
            raise LinkError("Mission not uploaded. Validation failed: " + ", ".join(failed))
        if not 0 <= segment < len(ev.compiled.segments):
            raise LinkError(f"This mission has {len(ev.compiled.segments)} flights")
        seg = ev.compiled.segments[segment]
        plan = ev.plan
        fence = [p.tuple() for p in plan.geofence] if plan.safety.fence_enabled else []

        steps: list[dict[str, Any]] = []

        def step(name: str, result: CommandResult) -> bool:
            steps.append({"step": name, "ok": result.accepted, "message": result.message})
            return result.accepted

        self.active = None
        safety_ok = step("Emergency settings", await link.apply_safety(plan.safety))
        fence_ok = step("Geofence", await link.upload_fence(fence, plan.safety.max_alt_m))
        items_ok = step("Mission items", await link.upload_mission(seg.items))
        verified = False
        if items_ok:
            back = await link.read_mission()
            verified = len(back) == len(seg.items) and all(
                sent.matches(got) for sent, got in zip(seg.items, back, strict=False)
            )
            step(
                "Read-back",
                CommandResult(
                    accepted=verified,
                    message=f"{len(back)} items identical"
                    if verified
                    else "The vehicle holds something different from what was sent",
                ),
            )

        self.active = ActiveMission(
            mission_id=row.id,
            name=row.name,
            revision=row.revision,
            segment=segment,
            segments=len(ev.compiled.segments),
            item_count=len(seg.items),
            verified=verified,
            fence_uploaded=fence_ok and bool(fence),
            fence_points=len(fence),
            safety_applied=safety_ok,
            valid=ev.validation.ok,
            battery_pct=seg.estimate.battery_pct,
            storage_mb=ev.compiled.stats.storage_mb,
            models_ready=ev.crop.models_ready if ev.crop else None,
            models_detail=ev.crop.models_detail if ev.crop else "",
            safety=plan.safety,
            route=ev.compiled.route if len(ev.compiled.segments) == 1 else _route_of(seg, plan),
            geofence=[p.tuple() for p in plan.geofence],
            area=[p.tuple() for p in plan.survey.polygon] if plan.survey else [],
        )
        ok = safety_ok and fence_ok and items_ok and verified
        self._record_event(
            EventKind.MISSION,
            f"Mission '{row.name}' uploaded and verified"
            if ok
            else f"Mission '{row.name}' upload incomplete",
            Severity.INFO if ok else Severity.CRITICAL,
            mission_id=row.id,
        )
        self._publish_status()
        return {"ok": ok, "steps": steps}

    # ------------------------------------------------------------------ commands
    async def command(self, name: str, args: dict[str, Any] | None = None) -> CommandResult:
        args = args or {}
        try:
            link = self._need_link()
            result = await self._dispatch(link, name, args)
        except LinkError as e:
            result = refused(str(e))
        self._record_event(
            EventKind.COMMAND,
            f"{name.upper()} accepted" if result.accepted else result.message or f"{name} refused",
            Severity.INFO if result.accepted else Severity.WARNING,
            command=name,
            accepted=result.accepted,
        )
        return result

    async def _dispatch(self, link: VehicleLink, name: str, args: dict[str, Any]) -> CommandResult:
        if name == "arm":
            if not args.get("override"):
                pre = self.preflight()
                if not pre.ready:
                    return refused("Pre-flight not passed: " + ", ".join(pre.blocking))
            else:
                self._record_event(
                    EventKind.COMMAND,
                    "Pre-flight checklist overridden by operator",
                    Severity.WARNING,
                )
            return await link.arm()
        if name == "disarm":
            return await link.disarm()
        if name == "takeoff":
            return await link.takeoff(float(args.get("alt_m", 10.0)))
        if name == "start":
            if self.active is None or not self.active.verified:
                return refused("Upload and verify a mission before starting it")
            return await link.start_mission()
        if name == "pause":
            return await link.pause()
        if name == "resume":
            return await link.resume()
        if name == "rtl":
            return await link.rtl()
        if name == "land":
            return await link.land()
        if name == "goto":
            return await link.goto(float(args["lat"]), float(args["lon"]), float(args["alt_m"]))
        return refused(f"Unknown command '{name}'")

    async def manual(self, forward: float, right: float, up: float, yaw_rate: float) -> None:
        """Stick input from the browser. Silently ignored when it cannot apply."""
        if self.link is None or self.status != LinkStatus.CONNECTED:
            return
        with suppress(LinkError):
            await self.link.set_velocity(forward, right, up, yaw_rate)

    def inject(self, **conditions: Any) -> None:
        if not isinstance(self.link, KinematicSim):
            raise LinkError("Conditions can only be changed on the built-in simulator")
        self.link.inject(**conditions)
        self._record_event(
            EventKind.STATUS_TEXT,
            "Simulator conditions changed: "
            + ", ".join(f"{k}={v}" for k, v in conditions.items() if v is not None),
            Severity.WARNING,
        )


def _route_of(seg: Any, plan: Any) -> list[tuple[float, float, float]]:
    from app.mission.compiler import _route

    return _route(seg.items, plan)
