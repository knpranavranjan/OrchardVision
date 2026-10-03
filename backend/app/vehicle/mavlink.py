"""MAVLink link to an ArduPilot Copter: the software autopilot (SITL) or a real Pixhawk.

The same class serves both; only the address differs:

    tcp:127.0.0.1:5760      ArduPilot SITL
    udpin:0.0.0.0:14550     a telemetry bridge or companion computer sending to this PC
    COM5 (with a baud rate)  a USB cable or a SiK telemetry radio

pymavlink is blocking, so one thread owns the connection. It reads telemetry
continuously and runs commands handed to it; results come back to the event loop.
"""

import asyncio
import concurrent.futures
import logging
import os
import queue
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

os.environ.setdefault("MAVLINK20", "1")  # must be set before pymavlink is imported

from pymavlink import mavutil  # noqa: E402

from app.core.conventions import utc_now  # noqa: E402
from app.mission.export import mav_fields  # noqa: E402
from app.vehicle.link import (  # noqa: E402
    OK,
    CommandResult,
    EventKind,
    FailsafeAction,
    FlightMode,
    GpsFix,
    LinkError,
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

log = logging.getLogger(__name__)
mav = mavutil.mavlink

# ArduCopter flight mode numbers
COPTER_MODES = {
    0: "STABILIZE", 1: "ACRO", 2: "ALT_HOLD", 3: "AUTO", 4: "GUIDED", 5: "LOITER", 6: "RTL",
    7: "CIRCLE", 9: "LAND", 11: "DRIFT", 13: "SPORT", 14: "FLIP", 15: "AUTOTUNE", 16: "POSHOLD",
    17: "BRAKE", 18: "THROW", 19: "AVOID_ADSB", 20: "GUIDED_NOGPS", 21: "SMART_RTL",
    22: "FLOWHOLD", 23: "FOLLOW", 24: "ZIGZAG", 25: "SYSTEMID", 26: "AUTOROTATE", 27: "AUTO_RTL",
}  # fmt: skip
MODE_NUMBER = {name: number for number, name in COPTER_MODES.items()}
GENERIC_MODE = {
    "AUTO": FlightMode.AUTO,
    "GUIDED": FlightMode.GUIDED,
    "LOITER": FlightMode.HOLD,
    "BRAKE": FlightMode.HOLD,
    "POSHOLD": FlightMode.HOLD,
    "RTL": FlightMode.RTL,
    "SMART_RTL": FlightMode.RTL,
    "AUTO_RTL": FlightMode.RTL,
    "LAND": FlightMode.LAND,
    "STABILIZE": FlightMode.MANUAL,
    "ALT_HOLD": FlightMode.MANUAL,
    "ACRO": FlightMode.MANUAL,
    "SPORT": FlightMode.MANUAL,
    "DRIFT": FlightMode.MANUAL,
}
GPS_FIX = {
    2: GpsFix.FIX_2D, 3: GpsFix.FIX_3D, 4: GpsFix.DGPS, 5: GpsFix.RTK_FLOAT, 6: GpsFix.RTK_FIXED,
}  # fmt: skip
RESULT_TEXT = {
    1: "temporarily rejected", 2: "denied", 3: "unsupported", 4: "failed", 5: "in progress",
    6: "cancelled",
}  # fmt: skip
MISSION_TYPE_MISSION, MISSION_TYPE_FENCE = 0, 1
FENCE_VERTEX_INCLUSION = 5001
POSITION_ONLY_MASK = 0b0000_1111_1111_1000
VELOCITY_YAWRATE_MASK = 0b0000_0101_1100_0111
STATE_PERIOD_S = 0.1


def list_serial_ports() -> list[dict[str, str]]:
    from serial.tools import list_ports

    return [
        {
            "device": p.device,
            "description": p.description or "",
            "manufacturer": p.manufacturer or "",
        }
        for p in list_ports.comports()
    ]


def item_from_mav(seq: int, command: int, p: list[float], lat: float, lon: float, alt: float):
    """Inverse of mission.export.mav_fields, for the read-back comparison."""
    K = MissionItemKind
    if command == mav.MAV_CMD_NAV_TAKEOFF:
        return MissionItem(seq=seq, kind=K.TAKEOFF, alt_rel_m=alt)
    if command == mav.MAV_CMD_NAV_WAYPOINT:
        return MissionItem(seq=seq, kind=K.WAYPOINT, lat=lat, lon=lon, alt_rel_m=alt, value=p[0])
    if command == mav.MAV_CMD_DO_CHANGE_SPEED:
        return MissionItem(seq=seq, kind=K.SET_SPEED, value=p[1])
    if command == mav.MAV_CMD_DO_SET_CAM_TRIGG_DIST:
        return MissionItem(seq=seq, kind=K.CAMERA_TRIGGER_DISTANCE, value=p[0])
    if command == mav.MAV_CMD_DO_MOUNT_CONTROL:
        return MissionItem(seq=seq, kind=K.GIMBAL_PITCH, value=p[0])
    if command == mav.MAV_CMD_NAV_RETURN_TO_LAUNCH:
        return MissionItem(seq=seq, kind=K.RTL)
    if command == mav.MAV_CMD_NAV_LAND:
        return MissionItem(seq=seq, kind=K.LAND)
    return None


class MavlinkLink(VehicleLink):
    def __init__(
        self, url: str, baud: int = 57600, kind: VehicleKind = VehicleKind.PIXHAWK
    ) -> None:
        super().__init__()
        self.url = url
        self.baud = baud
        self.kind = kind
        self.description = f"ArduPilot at {url}"
        self._conn: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ops: queue.Queue = queue.Queue()
        self._running = False
        self._ready = threading.Event()
        self._error: Exception | None = None

        self._s: dict[str, Any] = {}  # latest telemetry values
        self._mode_name = ""
        self._armed = False
        self._captures = 0
        self._last_text = ""
        self._last_emit = 0.0

    # ------------------------------------------------------------------ lifecycle
    async def connect(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._running = True
        self._thread = threading.Thread(target=self._main, name="mavlink", daemon=True)
        self._thread.start()
        await self._loop.run_in_executor(None, self._ready.wait, 15.0)
        if self._error or not self._ready.is_set():
            self._running = False
            raise LinkError(str(self._error or f"no heartbeat from {self.url}"))

    async def disconnect(self) -> None:
        self._running = False
        if self._thread and self._loop:
            await self._loop.run_in_executor(None, self._thread.join, 3.0)
        self._thread = None

    def _main(self) -> None:
        try:
            self._conn = mavutil.mavlink_connection(
                self.url,
                baud=self.baud,
                source_system=255,
                source_component=mav.MAV_COMP_ID_MISSIONPLANNER,
                autoreconnect=True,
            )
            deadline = time.monotonic() + 12.0
            while True:
                hb = self._conn.recv_match(type="HEARTBEAT", blocking=True, timeout=1.0)
                if hb and hb.autopilot != mav.MAV_AUTOPILOT_INVALID and hb.type != mav.MAV_TYPE_GCS:
                    self._conn.target_system = hb.get_srcSystem()
                    self._conn.target_component = hb.get_srcComponent()
                    self._handle(hb)
                    break
                if time.monotonic() > deadline or not self._running:
                    raise LinkError(f"no heartbeat from {self.url}")
            self._request_streams()
            self._ready.set()
            self._emit_event(EventKind.LINK, f"Connected to {self.url}")

            last_heartbeat = 0.0
            while self._running:
                try:
                    fn, future = self._ops.get_nowait()
                except queue.Empty:
                    pass
                else:
                    self._run_op(fn, future)
                msg = self._conn.recv_match(blocking=True, timeout=0.05)
                if msg is not None:
                    self._handle(msg)
                now = time.monotonic()
                if now - last_heartbeat >= 1.0:
                    last_heartbeat = now
                    self._conn.mav.heartbeat_send(
                        mav.MAV_TYPE_GCS, mav.MAV_AUTOPILOT_INVALID, 0, 0, 0
                    )
        except Exception as e:  # the thread must report, never die silently
            log.warning("MAVLink link failed: %s", e)
            self._error = e
            self._ready.set()
        finally:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:  # noqa: BLE001
                    pass

    @staticmethod
    def _run_op(fn: Callable[[], Any], future: concurrent.futures.Future | None) -> None:
        try:
            result = fn()
        except Exception as e:  # noqa: BLE001
            if future:
                future.set_exception(e)
            else:
                log.warning("MAVLink send failed: %s", e)
        else:
            if future:
                future.set_result(result)

    async def _call(self, fn: Callable[[], Any]) -> Any:
        if not self._running or self._thread is None:
            raise LinkError("not connected")
        future: concurrent.futures.Future = concurrent.futures.Future()
        self._ops.put((fn, future))
        return await asyncio.wrap_future(future)

    def _request_streams(self) -> None:
        c = self._conn
        c.mav.request_data_stream_send(
            c.target_system, c.target_component, mav.MAV_DATA_STREAM_ALL, 4, 1
        )
        for message_id, hz in (
            (mav.MAVLINK_MSG_ID_GLOBAL_POSITION_INT, 10),
            (mav.MAVLINK_MSG_ID_ATTITUDE, 10),
            (mav.MAVLINK_MSG_ID_EXTENDED_SYS_STATE, 2),
            (mav.MAVLINK_MSG_ID_HOME_POSITION, 0.5),
        ):
            c.mav.command_long_send(
                c.target_system, c.target_component, mav.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                message_id, 1e6 / hz, 0, 0, 0, 0, 0,
            )  # fmt: skip

    # ------------------------------------------------------------------ telemetry
    def _emit_event(
        self, kind: EventKind, message: str, severity: Severity = Severity.INFO, **data: object
    ) -> None:
        if self._on_event and self._loop:
            event = VehicleEvent(
                time=utc_now(), kind=kind, severity=severity, message=message, data=data
            )
            self._loop.call_soon_threadsafe(self._on_event, event)

    def _handle(self, msg: Any) -> None:
        t = msg.get_type()
        s = self._s
        if t == "HEARTBEAT":
            if msg.autopilot == mav.MAV_AUTOPILOT_INVALID or msg.type == mav.MAV_TYPE_GCS:
                return
            armed = bool(msg.base_mode & mav.MAV_MODE_FLAG_SAFETY_ARMED)
            name = COPTER_MODES.get(msg.custom_mode, f"MODE_{msg.custom_mode}")
            if armed != self._armed:
                self._armed = armed
                self._emit_event(
                    EventKind.ARMED if armed else EventKind.DISARMED,
                    "Armed" if armed else "Disarmed",
                )
            if name != self._mode_name:
                self._mode_name = name
                self._emit_event(EventKind.MODE_CHANGE, f"Mode {name}", mode=name)
        elif t == "GLOBAL_POSITION_INT":
            s["lat"], s["lon"] = msg.lat / 1e7, msg.lon / 1e7
            s["alt_amsl"], s["alt_rel"] = msg.alt / 1000.0, msg.relative_alt / 1000.0
            s["vn"], s["ve"], s["vu"] = msg.vx / 100.0, msg.vy / 100.0, -msg.vz / 100.0
            if msg.hdg != 65535:
                s["heading"] = msg.hdg / 100.0
            self._maybe_emit_state()
        elif t == "ATTITUDE":
            s["roll"] = msg.roll * 57.29578
            s["pitch"] = msg.pitch * 57.29578
            s.setdefault("heading", (msg.yaw * 57.29578) % 360.0)
        elif t == "SYS_STATUS":
            s["batt_v"] = msg.voltage_battery / 1000.0 if msg.voltage_battery != 65535 else None
            s["batt_a"] = msg.current_battery / 100.0 if msg.current_battery >= 0 else None
            s["batt_pct"] = float(msg.battery_remaining) if msg.battery_remaining >= 0 else None
        elif t == "GPS_RAW_INT":
            s["fix"] = GPS_FIX.get(msg.fix_type, GpsFix.NONE)
            s["sats"] = msg.satellites_visible if msg.satellites_visible != 255 else 0
            s["hdop"] = msg.eph / 100.0 if msg.eph != 65535 else None
        elif t == "MISSION_CURRENT":
            # ArduPilot's item 0 is the home position; ours start at its item 1.
            s["seq"] = msg.seq - 1 if msg.seq >= 1 else None
        elif t == "MISSION_ITEM_REACHED":
            if msg.seq >= 1:
                self._emit_event(EventKind.ITEM_REACHED, f"Item {msg.seq - 1}", seq=msg.seq - 1)
        elif t == "STATUSTEXT":
            text = msg.text.strip("\x00 ")
            self._last_text = text
            severity = (
                Severity.CRITICAL
                if msg.severity <= 3
                else Severity.WARNING
                if msg.severity == 4
                else Severity.INFO
            )
            kind = EventKind.FAILSAFE if "failsafe" in text.lower() else EventKind.STATUS_TEXT
            self._emit_event(kind, text, severity)
        elif t == "CAMERA_FEEDBACK":
            self._captures += 1
            self._emit_event(
                EventKind.CAPTURE,
                f"Photo {self._captures}",
                index=self._captures,
                lat=msg.lat / 1e7,
                lon=msg.lng / 1e7,
                alt_rel_m=msg.alt_rel,
                heading_deg=msg.yaw % 360.0,
                gimbal_pitch_deg=msg.pitch,
                mission_seq=s.get("seq"),
            )
        elif t == "RC_CHANNELS":
            s["rc_ok"] = msg.chancount > 0 and msg.rssi != 0
        elif t == "EKF_STATUS_REPORT":
            need = mav.EKF_ATTITUDE | mav.EKF_VELOCITY_HORIZ | mav.EKF_POS_HORIZ_ABS
            s["ekf_ok"] = (msg.flags & need) == need
        elif t == "HOME_POSITION":
            s["home"] = (msg.latitude / 1e7, msg.longitude / 1e7)
        elif t == "EXTENDED_SYS_STATE":
            s["landed_state"] = msg.landed_state
        elif t == "NAV_CONTROLLER_OUTPUT":
            s["wp_dist"] = float(msg.wp_dist)

    def _maybe_emit_state(self) -> None:
        now = time.monotonic()
        if now - self._last_emit < STATE_PERIOD_S or not self._on_state or not self._loop:
            return
        self._last_emit = now
        self._loop.call_soon_threadsafe(self._on_state, self._state())

    def _state(self) -> VehicleState:
        s = self._s
        alt = s.get("alt_rel", 0.0)
        landed = s.get("landed_state")
        in_air = landed in (2, 3, 4) if landed else (self._armed and alt > 0.3)
        mode = GENERIC_MODE.get(self._mode_name, FlightMode.UNKNOWN)
        if not self._armed and not in_air:
            mode = FlightMode.STANDBY
        home = s.get("home")
        ve, vn = s.get("ve", 0.0), s.get("vn", 0.0)
        return VehicleState(
            time=utc_now(),
            lat=s.get("lat", 0.0),
            lon=s.get("lon", 0.0),
            alt_rel_m=round(alt, 2),
            alt_amsl_m=s.get("alt_amsl"),
            vel_north_mps=vn,
            vel_east_mps=ve,
            vel_up_mps=s.get("vu", 0.0),
            groundspeed_mps=round((ve * ve + vn * vn) ** 0.5, 2),
            roll_deg=round(s.get("roll", 0.0), 2),
            pitch_deg=round(s.get("pitch", 0.0), 2),
            heading_deg=round(s.get("heading", 0.0), 1),
            battery_pct=s.get("batt_pct"),
            battery_v=s.get("batt_v"),
            battery_a=s.get("batt_a"),
            gps_fix=s.get("fix", GpsFix.NONE),
            satellites=s.get("sats", 0),
            hdop=s.get("hdop"),
            mode=mode,
            mode_raw=self._mode_name,
            armed=self._armed,
            in_air=in_air,
            mission_seq=s.get("seq"),
            mission_count=s.get("mission_count", 0),
            wp_dist_m=s.get("wp_dist") if mode == FlightMode.AUTO else None,
            home_lat=home[0] if home else None,
            home_lon=home[1] if home else None,
            rc_ok=s.get("rc_ok"),
            ekf_ok=s.get("ekf_ok"),
            captures=self._captures,
        )

    # ------------------------------------------------------------------ protocol helpers
    # Everything below this line runs on the link thread.
    def _wait(self, types: Sequence[str], match: Callable[[Any], bool], timeout: float) -> Any:
        """Read until a matching message arrives. Everything read still updates telemetry."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = self._conn.recv_match(blocking=True, timeout=0.05)
            if msg is None:
                continue
            self._handle(msg)
            if msg.get_type() in types and match(msg):
                return msg
        return None

    def _command(self, command: int, *params: float, what: str) -> CommandResult:
        c = self._conn
        p = list(params) + [0.0] * (7 - len(params))
        self._last_text = ""
        for attempt in range(3):
            c.mav.command_long_send(c.target_system, c.target_component, command, attempt, *p)
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                ack = self._wait(["COMMAND_ACK"], lambda m: m.command == command, 2.0)
                if ack is None:
                    break
                if ack.result == mav.MAV_RESULT_ACCEPTED:
                    return OK
                if ack.result == mav.MAV_RESULT_IN_PROGRESS:
                    continue
                # Give the autopilot a moment to explain itself (for example "PreArm: ...").
                self._wait(["STATUSTEXT"], lambda m: True, 0.4)
                reason = self._last_text or RESULT_TEXT.get(ack.result, f"result {ack.result}")
                return refused(f"{what} refused: {reason}")
        return refused(f"{what}: no answer from the vehicle")

    def _set_mode(self, name: str) -> CommandResult:
        number = MODE_NUMBER[name]
        result = self._command(
            mav.MAV_CMD_DO_SET_MODE,
            mav.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            number,
            what=f"Mode {name}",
        )
        if not result.accepted:
            return result
        hb = self._wait(
            ["HEARTBEAT"],
            lambda m: m.autopilot != mav.MAV_AUTOPILOT_INVALID and m.custom_mode == number,
            3.0,
        )
        return OK if hb else refused(f"Mode {name}: the vehicle did not change mode")

    def _set_param(self, name: str, value: float) -> bool:
        c = self._conn
        for _ in range(3):
            c.mav.param_set_send(
                c.target_system, c.target_component, name.encode(), float(value),
                mav.MAV_PARAM_TYPE_REAL32,
            )  # fmt: skip
            got = self._wait(["PARAM_VALUE"], lambda m: m.param_id.strip("\x00") == name, 1.5)
            if got is not None:
                return abs(got.param_value - value) < 1e-3
        return False

    def _send_items(
        self, rows: list[tuple[int, int, list[float]]], mission_type: int
    ) -> CommandResult:
        """The MAVLink mission upload handshake. rows: (command, frame, [p1..p4, lat, lon, alt])."""
        c = self._conn
        ts, tc = c.target_system, c.target_component
        if not rows:
            c.mav.mission_clear_all_send(ts, tc, mission_type)
            ack = self._wait(["MISSION_ACK"], lambda m: m.mission_type == mission_type, 3.0)
            return (
                OK if ack is not None and ack.type == 0 else refused("Clear was not acknowledged")
            )

        c.mav.mission_count_send(ts, tc, len(rows), mission_type)
        deadline = time.monotonic() + 5.0 + len(rows) * 0.5
        retries = 0
        while time.monotonic() < deadline:
            msg = self._wait(
                ["MISSION_REQUEST_INT", "MISSION_REQUEST", "MISSION_ACK"],
                lambda m: getattr(m, "mission_type", 0) == mission_type,
                2.0,
            )
            if msg is None:
                retries += 1
                if retries > 3:
                    break
                c.mav.mission_count_send(ts, tc, len(rows), mission_type)
                continue
            if msg.get_type() == "MISSION_ACK":
                if msg.type == mav.MAV_MISSION_ACCEPTED:
                    return OK
                return refused(f"The vehicle rejected the upload (code {msg.type})")
            if msg.seq >= len(rows):
                return refused(f"The vehicle asked for item {msg.seq}, which does not exist")
            command, frame, p = rows[msg.seq]
            c.mav.mission_item_int_send(
                ts, tc, msg.seq, frame, command, 0, 1, p[0], p[1], p[2], p[3],
                int(round(p[4] * 1e7)), int(round(p[5] * 1e7)), p[6], mission_type,
            )  # fmt: skip
        return refused("Upload timed out")

    # ------------------------------------------------------------------ interface
    async def upload_mission(self, items: Sequence[MissionItem]) -> CommandResult:
        def op() -> CommandResult:
            home = self._s.get("home") or (self._s.get("lat", 0.0), self._s.get("lon", 0.0))
            # ArduPilot keeps the home position in slot 0.
            rows = [(mav.MAV_CMD_NAV_WAYPOINT, mav.MAV_FRAME_GLOBAL, [0, 0, 0, 0, *home, 0])]
            rows += [mav_fields(i) for i in items]
            result = self._send_items(rows, MISSION_TYPE_MISSION)
            if result.accepted:
                self._s["mission_count"] = len(items)
            return result

        return await self._call(op)

    async def read_mission(self) -> list[MissionItem]:
        def op() -> list[MissionItem]:
            c = self._conn
            ts, tc = c.target_system, c.target_component
            c.mav.mission_request_list_send(ts, tc, MISSION_TYPE_MISSION)
            count = self._wait(["MISSION_COUNT"], lambda m: m.mission_type == 0, 3.0)
            if count is None:
                raise LinkError("the vehicle did not report its mission")
            items: list[MissionItem] = []
            for seq in range(1, count.count):
                got = None
                for _ in range(3):
                    c.mav.mission_request_int_send(ts, tc, seq, MISSION_TYPE_MISSION)
                    got = self._wait(["MISSION_ITEM_INT"], lambda m, s=seq: m.seq == s, 1.5)
                    if got is not None:
                        break
                if got is None:
                    raise LinkError(f"the vehicle did not return mission item {seq}")
                item = item_from_mav(
                    seq - 1, got.command, [got.param1, got.param2, got.param3, got.param4],
                    got.x / 1e7, got.y / 1e7, got.z,
                )  # fmt: skip
                if item is None:
                    raise LinkError(
                        f"the vehicle holds an item this software did not send ({got.command})"
                    )
                items.append(item)
            c.mav.mission_ack_send(ts, tc, mav.MAV_MISSION_ACCEPTED, MISSION_TYPE_MISSION)
            return items

        return await self._call(op)

    async def upload_fence(
        self, polygon: Sequence[tuple[float, float]], max_alt_m: float
    ) -> CommandResult:
        def op() -> CommandResult:
            n = len(polygon)
            rows = [
                (FENCE_VERTEX_INCLUSION, mav.MAV_FRAME_GLOBAL, [n, 0, 0, 0, lat, lon, 0])
                for lat, lon in polygon
            ]
            result = self._send_items(rows, MISSION_TYPE_FENCE)
            if not result.accepted:
                return refused(f"Geofence: {result.message}")
            # Fence type is a bitmask: 1 height, 4 polygon.
            ok = self._set_param("FENCE_TYPE", 5 if n else 1)
            ok &= self._set_param("FENCE_ALT_MAX", max_alt_m)
            return OK if ok else refused("Geofence uploaded but its settings were not confirmed")

        return await self._call(op)

    async def apply_safety(self, safety: SafetyConfig) -> CommandResult:
        fence_action = {FailsafeAction.RTL: 1, FailsafeAction.LAND: 2, FailsafeAction.HOLD: 4}
        battery_action = {FailsafeAction.RTL: 2, FailsafeAction.LAND: 1, FailsafeAction.HOLD: 0}
        gcs_action = {FailsafeAction.RTL: 1, FailsafeAction.LAND: 5, FailsafeAction.HOLD: 1}
        ekf_action = {FailsafeAction.RTL: 1, FailsafeAction.LAND: 1, FailsafeAction.HOLD: 2}
        params = {
            "FENCE_ENABLE": 1 if safety.fence_enabled else 0,
            "FENCE_ACTION": fence_action[safety.on_fence_breach],
            "FENCE_ALT_MAX": safety.max_alt_m,
            "BATT_FS_CRT_ACT": battery_action[safety.on_battery_critical],
            "FS_GCS_ENABLE": gcs_action[safety.on_link_loss],
            "FS_EKF_ACTION": ekf_action[safety.on_gps_loss],
        }

        def op() -> CommandResult:
            failed = [name for name, value in params.items() if not self._set_param(name, value)]
            # Copter 4.7 renamed the return height to metres; older firmware uses centimetres.
            if not self._set_param("RTL_ALT_M", safety.rtl_alt_m) and not self._set_param(
                "RTL_ALT", safety.rtl_alt_m * 100
            ):
                failed.append("RTL_ALT")
            if failed:
                return refused("Not confirmed by the vehicle: " + ", ".join(failed))
            return OK

        return await self._call(op)

    async def arm(self) -> CommandResult:
        def op() -> CommandResult:
            if self._armed:
                return OK
            # Arm in GUIDED so the ground station, not the RC throttle, starts the motors.
            if self._mode_name != "GUIDED":
                mode = self._set_mode("GUIDED")
                if not mode.accepted:
                    return mode
            return self._command(mav.MAV_CMD_COMPONENT_ARM_DISARM, 1, what="Arm")

        return await self._call(op)

    async def disarm(self) -> CommandResult:
        return await self._call(
            lambda: self._command(mav.MAV_CMD_COMPONENT_ARM_DISARM, 0, what="Disarm")
        )

    async def takeoff(self, alt_rel_m: float) -> CommandResult:
        def op() -> CommandResult:
            if self._mode_name != "GUIDED":
                mode = self._set_mode("GUIDED")
                if not mode.accepted:
                    return mode
            return self._command(
                mav.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, alt_rel_m, what="Takeoff"
            )

        return await self._call(op)

    async def start_mission(self) -> CommandResult:
        def op() -> CommandResult:
            mode = self._set_mode("AUTO")
            if not mode.accepted:
                return mode
            return self._command(mav.MAV_CMD_MISSION_START, 0, 0, what="Mission start")

        return await self._call(op)

    async def pause(self) -> CommandResult:
        def op() -> CommandResult:
            if self._mode_name == "AUTO":
                paused = self._command(mav.MAV_CMD_DO_PAUSE_CONTINUE, 0, what="Pause")
                if paused.accepted:
                    return paused
            return self._set_mode("BRAKE")

        return await self._call(op)

    async def resume(self) -> CommandResult:
        def op() -> CommandResult:
            if self._mode_name == "AUTO":
                return self._command(mav.MAV_CMD_DO_PAUSE_CONTINUE, 1, what="Resume")
            return self._set_mode("AUTO")

        return await self._call(op)

    async def rtl(self) -> CommandResult:
        return await self._call(lambda: self._set_mode("RTL"))

    async def land(self) -> CommandResult:
        return await self._call(lambda: self._set_mode("LAND"))

    async def goto(self, lat: float, lon: float, alt_rel_m: float) -> CommandResult:
        def op() -> CommandResult:
            if self._mode_name != "GUIDED":
                mode = self._set_mode("GUIDED")
                if not mode.accepted:
                    return mode
            c = self._conn
            c.mav.set_position_target_global_int_send(
                0, c.target_system, c.target_component, mav.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                POSITION_ONLY_MASK, int(lat * 1e7), int(lon * 1e7), alt_rel_m,
                0, 0, 0, 0, 0, 0, 0, 0,
            )  # fmt: skip
            return OK

        return await self._call(op)

    async def set_velocity(
        self, forward_mps: float, right_mps: float, up_mps: float, yaw_rate_dps: float
    ) -> CommandResult:
        if self._mode_name == "AUTO":
            return refused("Pause the mission before taking manual control")

        def op() -> None:
            if self._mode_name != "GUIDED" and not self._set_mode("GUIDED").accepted:
                return
            c = self._conn
            # ArduPilot stops and holds if these stop arriving for three seconds.
            c.mav.set_position_target_local_ned_send(
                0, c.target_system, c.target_component, mav.MAV_FRAME_BODY_NED,
                VELOCITY_YAWRATE_MASK, 0, 0, 0, forward_mps, right_mps, -up_mps,
                0, 0, 0, 0, yaw_rate_dps * 0.0174533,
            )  # fmt: skip

        if not self._running:
            raise LinkError("not connected")
        self._ops.put((op, None))  # fire and forget: stick input must not queue behind acks
        return OK
