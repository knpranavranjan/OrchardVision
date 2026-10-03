"""Flight recorder: every armed period becomes a flight with telemetry, events and captures.

The flight manager calls add_state and add_event on the event loop. Database
writes happen on a worker thread, in order, so a slow disk never delays telemetry.
If the database is unreachable the flight still happens; it is just not recorded.
"""

import asyncio
import logging
import math
from datetime import datetime
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.core.conventions import LocalFrame, utc_now
from app.db.session import Database
from app.db.tables import Capture, Flight, FlightEvent, TelemetrySample
from app.vehicle.link import EventKind, VehicleEvent, VehicleState

log = logging.getLogger(__name__)


class FlightRecorder:
    def __init__(self, db: Database, record_hz: float) -> None:
        self.db = db
        self.period = 1.0 / record_hz
        self.flight_id: int | None = None
        self.active = False
        self.ok = True
        self._samples: list[dict] = []
        self._events: list[dict] = []
        self._captures: list[dict] = []
        self._last_sample: datetime | None = None
        self._last_time: datetime | None = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self._summary: dict[str, Any] = {}
        self._last_pos: tuple[float, float] | None = None

    def start_worker(self) -> None:
        self._worker = asyncio.create_task(self._work())

    async def stop_worker(self) -> None:
        if self._worker:
            await self._queue.join()
            self._worker.cancel()
            self._worker = None

    async def _work(self) -> None:
        while True:
            fn, args = await self._queue.get()
            try:
                if await asyncio.to_thread(fn, *args):
                    self.ok = True
            except SQLAlchemyError as e:
                if self.ok:
                    log.warning("flight recording unavailable: %s", e.__class__.__name__)
                self.ok = False
            finally:
                self._queue.task_done()

    # ------------------------------------------------------------------ called on the event loop
    def begin(self, state: VehicleState, meta: dict[str, Any]) -> None:
        self.active = True
        self.flight_id = None
        self._samples, self._events, self._captures = [], [], []
        self._last_sample = None
        self._last_pos = None
        self._summary = {
            "distance_m": 0.0,
            "max_alt_m": 0.0,
            "max_speed_mps": 0.0,
            "battery_start_pct": state.battery_pct,
            "battery_end_pct": state.battery_pct,
            "captures": 0,
            "failsafes": [],
            "mission_completed": False,
        }
        self._queue.put_nowait((self._insert_flight, (state.time, meta)))
        self.add_state(state)

    def add_state(self, state: VehicleState, force: bool = False) -> None:
        """Keep one sample per period. `force` records this one regardless (the landing)."""
        if not self.active:
            return
        s = self._summary
        self._last_time = state.time
        s["max_alt_m"] = max(s["max_alt_m"], state.alt_rel_m)
        s["max_speed_mps"] = max(s["max_speed_mps"], state.groundspeed_mps)
        s["battery_end_pct"] = state.battery_pct
        if self._last_pos is not None:
            e, n = LocalFrame(*self._last_pos).to_en(state.lat, state.lon)
            step = math.hypot(e, n)
            if step < 100:  # ignore GPS jumps
                s["distance_m"] += step
        self._last_pos = (state.lat, state.lon)

        since = (state.time - self._last_sample).total_seconds() if self._last_sample else None
        if since is not None and since < self.period and not force:
            return
        self._last_sample = state.time
        self._samples.append(
            {
                "t": state.time,
                "lat": state.lat,
                "lon": state.lon,
                "alt_rel_m": state.alt_rel_m,
                "heading_deg": state.heading_deg,
                "groundspeed_mps": state.groundspeed_mps,
                "vel_up_mps": state.vel_up_mps,
                "roll_deg": state.roll_deg,
                "pitch_deg": state.pitch_deg,
                "battery_pct": state.battery_pct,
                "satellites": state.satellites,
                "mode": state.mode.value,
                "mission_seq": state.mission_seq,
            }
        )

    def add_event(self, event: VehicleEvent) -> None:
        if not self.active:
            return
        if event.kind == EventKind.CAPTURE:
            d = event.data
            self._summary["captures"] += 1
            self._captures.append(
                {
                    "index": d.get("index", self._summary["captures"]),
                    "t": event.time,
                    "lat": d.get("lat", 0.0),
                    "lon": d.get("lon", 0.0),
                    "alt_rel_m": d.get("alt_rel_m", 0.0),
                    "heading_deg": d.get("heading_deg", 0.0),
                    "gimbal_pitch_deg": d.get("gimbal_pitch_deg", -90.0),
                    "mission_seq": d.get("mission_seq"),
                }
            )
            return
        if event.kind == EventKind.FAILSAFE:
            self._summary["failsafes"].append(event.message)
        if event.kind == EventKind.MISSION and event.message == "Mission complete":
            self._summary["mission_completed"] = True
        self._events.append(
            {
                "t": event.time,
                "kind": event.kind.value,
                "severity": event.severity.value,
                "message": event.message,
                "data": event.data,
            }
        )

    def flush(self) -> None:
        if not (self._samples or self._events or self._captures):
            return
        batch = (self._samples, self._events, self._captures)
        self._samples, self._events, self._captures = [], [], []
        self._queue.put_nowait((self._insert_batch, batch))

    def end(self) -> dict[str, Any]:
        self.flush()
        self.active = False
        summary = dict(self._summary)
        summary["distance_m"] = round(summary["distance_m"], 1)
        summary["max_alt_m"] = round(summary["max_alt_m"], 1)
        summary["max_speed_mps"] = round(summary["max_speed_mps"], 1)
        status = "aborted" if summary["failsafes"] else "completed"
        ended = self._last_time or utc_now()
        self._queue.put_nowait((self._close_flight, (ended, status, summary)))
        return summary

    def check(self) -> None:
        """Ask the worker to test the database, so the checklist is right before a flight."""
        if not self.active and self._queue.empty():
            self._queue.put_nowait((self._probe, ()))

    # ------------------------------------------------------------------ run on a worker thread
    # Each returns True when it reached the database; errors mark recording unavailable.
    def _probe(self) -> bool:
        if not self.db.ping():
            self.ok = False
            return False
        return True

    def _insert_flight(self, started: datetime, meta: dict[str, Any]) -> bool:
        with self.db.session() as s:
            flight = Flight(started_at=started, status="in_progress", summary={}, **meta)
            s.add(flight)
            s.flush()
            self.flight_id = flight.id
        return True

    def _insert_batch(self, samples: list[dict], events: list[dict], captures: list[dict]) -> bool:
        if self.flight_id is None:
            return False
        fid = self.flight_id
        with self.db.session() as s:
            s.add_all(TelemetrySample(flight_id=fid, **row) for row in samples)
            s.add_all(FlightEvent(flight_id=fid, **row) for row in events)
            s.add_all(Capture(flight_id=fid, **row) for row in captures)
        return True

    def _close_flight(self, ended: datetime, status: str, summary: dict[str, Any]) -> bool:
        if self.flight_id is None:
            return False
        with self.db.session() as s:
            flight = s.get(Flight, self.flight_id)
            if flight is not None:
                flight.ended_at = ended
                flight.status = status
                summary["duration_s"] = round((ended - flight.started_at).total_seconds(), 1)
                flight.summary = summary
        return True
