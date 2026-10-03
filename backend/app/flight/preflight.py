"""Pre-flight checklist.

Automatic checks are computed from live vehicle and software state. Manual checks
are things only the operator can see; they are confirmed by hand and cleared
whenever the vehicle disarms or the link drops.
"""

from enum import StrEnum

from pydantic import BaseModel

from app.vehicle.link import SafetyConfig, VehicleKind, VehicleState

MIN_SATELLITES = 8
MAX_HDOP = 2.0
MIN_TELEMETRY_HZ = 2.0

MANUAL_CHECKS = {
    "weather": ("Weather", "Wind, rain and visibility are acceptable"),
    "airspace": ("Airspace and permission", "Flying here is permitted and the area is clear"),
    "airframe": ("Airframe and propellers", "Propellers, arms, battery and camera are secure"),
    "pilot": ("Safety pilot", "A pilot with the remote control is ready to take over"),
}


class CheckStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    PENDING = "pending"  # a manual check not yet confirmed


class PreflightCheck(BaseModel):
    id: str
    group: str
    label: str
    status: CheckStatus
    detail: str = ""
    manual: bool = False


class Preflight(BaseModel):
    ready: bool
    blocking: list[str]
    checks: list[PreflightCheck]


class Snapshot(BaseModel):
    """Everything the checklist looks at, gathered by the flight manager."""

    connected: bool
    kind: VehicleKind | None = None
    state: VehicleState | None = None
    state_age_s: float | None = None
    telemetry_hz: float = 0.0
    safety: SafetyConfig = SafetyConfig()
    mission_loaded: bool = False
    mission_name: str = ""
    mission_valid: bool = False
    mission_verified: bool = False
    mission_battery_pct: float = 0.0
    fence_uploaded: bool = False
    fence_points: int = 0
    safety_applied: bool = False
    models_ready: bool | None = None
    models_detail: str = ""
    storage_free_mb: float = 0.0
    storage_needed_mb: float = 0.0
    recording_ok: bool = True
    confirmations: dict[str, bool] = {}


def evaluate(s: Snapshot) -> Preflight:
    checks: list[PreflightCheck] = []
    P, W, F = CheckStatus.PASS, CheckStatus.WARN, CheckStatus.FAIL

    def add(id_: str, group: str, label: str, status: CheckStatus, detail: str = "") -> None:
        checks.append(
            PreflightCheck(id=id_, group=group, label=label, status=status, detail=detail)
        )

    st = s.state
    simulated = s.kind == VehicleKind.SIM

    # --- link
    add("link", "Link", "Drone connected", P if s.connected else F,
        "" if s.connected else "Connect to a vehicle first")  # fmt: skip
    fresh = st is not None and s.state_age_s is not None and s.state_age_s < 3.0
    add("heartbeat", "Link", "Flight controller responding", P if fresh else F,
        f"last telemetry {s.state_age_s:.1f} s ago" if s.state_age_s is not None else "no telemetry")  # fmt: skip
    if fresh:
        ok = s.telemetry_hz >= MIN_TELEMETRY_HZ
        add(
            "telemetry",
            "Link",
            "Telemetry rate",
            P if ok else W,
            f"{s.telemetry_hz:.0f} per second",
        )
        if st.rc_ok is None:
            add("rc", "Link", "Remote control", P if simulated else W,
                "not needed in simulation" if simulated else "the vehicle does not report its receiver")  # fmt: skip
        else:
            add("rc", "Link", "Remote control", P if st.rc_ok else F,
                "receiver connected" if st.rc_ok else "no signal from the remote control")  # fmt: skip

    # --- position
    if fresh:
        add("gps", "Position", "GPS position", P if st.gps_fix.usable else F,
            st.gps_fix.value.replace("_", " ").upper())  # fmt: skip
        good = st.satellites >= MIN_SATELLITES and (st.hdop is None or st.hdop <= MAX_HDOP)
        hdop = f", HDOP {st.hdop:.1f}" if st.hdop is not None else ""
        add("gps_quality", "Position", "GPS accuracy", P if good else F,
            f"{st.satellites} satellites{hdop}")  # fmt: skip
        if st.ekf_ok is not None:
            add("estimator", "Position", "Position estimator", P if st.ekf_ok else F,
                "healthy" if st.ekf_ok else "not ready")  # fmt: skip
        add("home", "Position", "Home position", P if st.home_lat is not None else F,
            "set" if st.home_lat is not None else "not set yet")  # fmt: skip

    # --- power
    if fresh:
        pct = st.battery_pct
        if pct is None:
            add("battery", "Power", "Battery", W, "the vehicle does not report charge")
        else:
            need = s.mission_battery_pct + s.safety.battery_reserve_pct if s.mission_loaded else 0.0
            if pct <= s.safety.battery_warn_pct:
                add(
                    "battery", "Power", "Battery", F, f"{pct:.0f}% is at or below the warning level"
                )
            elif need and pct < need:
                add("battery", "Power", "Battery", F,
                    f"{pct:.0f}% charged; this flight needs {need:.0f}% including the reserve")  # fmt: skip
            else:
                volts = f", {st.battery_v:.1f} V" if st.battery_v else ""
                add("battery", "Power", "Battery", P, f"{pct:.0f}%{volts}")

    # --- mission
    if s.mission_loaded:
        add("mission_valid", "Mission", "Mission validated", P if s.mission_valid else F,
            s.mission_name if s.mission_valid else "the mission has validation failures")  # fmt: skip
        add("mission_verified", "Mission", "Mission on the vehicle", P if s.mission_verified else F,
            "uploaded and read back identical" if s.mission_verified else "upload not verified")  # fmt: skip
        if not s.safety.fence_enabled:
            add("fence", "Mission", "Geofence", W, "switched off")
        else:
            add("fence", "Mission", "Geofence", P if s.fence_uploaded else F,
                f"{s.fence_points} corners, {s.safety.max_alt_m:g} m ceiling" if s.fence_uploaded
                else "not on the vehicle")  # fmt: skip
        add("failsafes", "Mission", "Emergency settings", P if s.safety_applied else F,
            f"link loss {s.safety.on_link_loss.value.upper()}, "
            f"battery {s.safety.on_battery_critical.value.upper()}, "
            f"GPS loss {s.safety.on_gps_loss.value.upper()}" if s.safety_applied
            else "not confirmed by the vehicle")  # fmt: skip
    else:
        add("mission_valid", "Mission", "Mission", W,
            "no mission uploaded; manual flight only")  # fmt: skip

    # --- camera, storage, models, recording
    add("camera", "Payload", "Camera", P if simulated else W,
        "simulated camera" if simulated else "check the camera is recording; it is not reported over the link")  # fmt: skip
    if s.storage_needed_mb:
        ok = s.storage_free_mb >= 2 * s.storage_needed_mb
        add("storage", "Payload", "Storage", P if ok else F,
            f"{s.storage_free_mb / 1000:.0f} GB free, {s.storage_needed_mb:.0f} MB needed")  # fmt: skip
    else:
        add("storage", "Payload", "Storage", P, f"{s.storage_free_mb / 1000:.0f} GB free")
    if s.models_ready is not None:
        add("models", "Payload", "AI models", P if s.models_ready else F, s.models_detail)
    add("recording", "Payload", "Flight recording", P if s.recording_ok else W,
        "database connected" if s.recording_ok else "database unreachable; this flight will not be recorded")  # fmt: skip

    # --- vehicle state
    if fresh:
        add("state", "Vehicle", "On the ground, disarmed", P if not st.in_air else W,
            "ready" if not st.in_air else "already flying")  # fmt: skip

    # --- operator confirmations
    for id_, (label, detail) in MANUAL_CHECKS.items():
        if simulated and id_ in ("airframe", "pilot", "airspace", "weather"):
            continue
        checks.append(
            PreflightCheck(
                id=id_,
                group="Operator",
                label=label,
                status=P if s.confirmations.get(id_) else CheckStatus.PENDING,
                detail=detail,
                manual=True,
            )
        )

    blocking = [c.label for c in checks if c.status in (F, CheckStatus.PENDING)]
    return Preflight(ready=not blocking, blocking=blocking, checks=checks)
