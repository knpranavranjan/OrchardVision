"""The one interface the ground station uses for every drone.

The built-in simulator, the ArduPilot software autopilot (SITL) and a real
Pixhawk each implement VehicleLink. Nothing above this module knows which one it
is talking to: same telemetry record, same events, same commands.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class VehicleKind(StrEnum):
    SIM = "sim"
    SITL = "sitl"
    PIXHAWK = "pixhawk"


class FlightMode(StrEnum):
    """Vehicle-independent modes. The autopilot's own name is kept in mode_raw."""

    STANDBY = "standby"
    TAKEOFF = "takeoff"
    AUTO = "auto"
    HOLD = "hold"
    GUIDED = "guided"
    MANUAL = "manual"
    RTL = "rtl"
    LAND = "land"
    UNKNOWN = "unknown"


class GpsFix(StrEnum):
    NONE = "none"
    FIX_2D = "2d"
    FIX_3D = "3d"
    DGPS = "dgps"
    RTK_FLOAT = "rtk_float"
    RTK_FIXED = "rtk_fixed"

    @property
    def usable(self) -> bool:
        return self not in (GpsFix.NONE, GpsFix.FIX_2D)


class VehicleState(BaseModel):
    """One normalised telemetry sample. SI units, WGS84 degrees, UTC."""

    time: datetime
    lat: float = 0.0
    lon: float = 0.0
    alt_rel_m: float = Field(default=0.0, description="Height above the home point")
    alt_amsl_m: float | None = None
    vel_north_mps: float = 0.0
    vel_east_mps: float = 0.0
    vel_up_mps: float = 0.0
    groundspeed_mps: float = 0.0
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    heading_deg: float = Field(default=0.0, description="Clockwise from true north, [0, 360)")
    gimbal_pitch_deg: float = Field(default=-90.0, description="0 is level, -90 is straight down")
    battery_pct: float | None = None
    battery_v: float | None = None
    battery_a: float | None = None
    gps_fix: GpsFix = GpsFix.NONE
    satellites: int = 0
    hdop: float | None = None
    mode: FlightMode = FlightMode.UNKNOWN
    mode_raw: str = ""
    armed: bool = False
    in_air: bool = False
    mission_seq: int | None = Field(default=None, description="Index of the current mission item")
    mission_count: int = 0
    wp_dist_m: float | None = None
    home_lat: float | None = None
    home_lon: float | None = None
    rc_ok: bool | None = Field(default=None, description="None when the vehicle does not report it")
    ekf_ok: bool | None = None
    captures: int = 0


class EventKind(StrEnum):
    CAPTURE = "capture"
    ITEM_REACHED = "item_reached"
    MODE_CHANGE = "mode_change"
    ARMED = "armed"
    DISARMED = "disarmed"
    FAILSAFE = "failsafe"
    STATUS_TEXT = "status_text"
    LINK = "link"
    COMMAND = "command"
    MISSION = "mission"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class VehicleEvent(BaseModel):
    time: datetime
    kind: EventKind
    severity: Severity = Severity.INFO
    message: str = ""
    data: dict = Field(default_factory=dict)


class MissionItemKind(StrEnum):
    TAKEOFF = "takeoff"
    WAYPOINT = "waypoint"
    SET_SPEED = "set_speed"
    CAMERA_TRIGGER_DISTANCE = "camera_trigger_distance"
    GIMBAL_PITCH = "gimbal_pitch"
    RTL = "rtl"
    LAND = "land"


NAV_KINDS = {
    MissionItemKind.TAKEOFF,
    MissionItemKind.WAYPOINT,
    MissionItemKind.RTL,
    MissionItemKind.LAND,
}


class MissionItem(BaseModel):
    """One step the autopilot executes. `value` is the item's single number:
    hold seconds for a waypoint, metres per second for set_speed, metres between
    photos for camera_trigger_distance (0 stops the camera), degrees for gimbal_pitch.
    """

    seq: int
    kind: MissionItemKind
    lat: float | None = None
    lon: float | None = None
    alt_rel_m: float | None = None
    value: float = 0.0

    def matches(self, other: "MissionItem", pos_tol_deg: float = 2e-7, tol: float = 0.02) -> bool:
        """Equality for the read-back check, allowing for the autopilot's integer storage."""
        if self.seq != other.seq or self.kind != other.kind:
            return False

        def close(a: float | None, b: float | None, t: float) -> bool:
            if a is None or b is None:
                return (a or 0.0) == (b or 0.0)
            return abs(a - b) <= t

        return (
            close(self.lat, other.lat, pos_tol_deg)
            and close(self.lon, other.lon, pos_tol_deg)
            and close(self.alt_rel_m, other.alt_rel_m, tol)
            and abs(self.value - other.value) <= tol
        )


class FailsafeAction(StrEnum):
    RTL = "rtl"
    LAND = "land"
    HOLD = "hold"


class SafetyConfig(BaseModel):
    """Limits and failsafe actions. Uploaded to the vehicle, which enforces them itself."""

    max_alt_m: float = 60.0
    min_alt_m: float = 3.0
    max_speed_mps: float = 8.0
    rtl_alt_m: float = 30.0
    battery_warn_pct: float = 30.0
    battery_crit_pct: float = 20.0
    battery_reserve_pct: float = 25.0
    on_battery_critical: FailsafeAction = FailsafeAction.RTL
    on_link_loss: FailsafeAction = FailsafeAction.RTL
    on_gps_loss: FailsafeAction = FailsafeAction.LAND
    on_fence_breach: FailsafeAction = FailsafeAction.RTL
    fence_enabled: bool = True


class CommandResult(BaseModel):
    accepted: bool
    message: str = ""


OK = CommandResult(accepted=True)


def refused(message: str) -> CommandResult:
    return CommandResult(accepted=False, message=message)


class LinkError(Exception):
    """The vehicle could not be reached or stopped answering."""


StateHandler = Callable[[VehicleState], None]
EventHandler = Callable[[VehicleEvent], None]


class VehicleLink(ABC):
    kind: VehicleKind
    description: str = ""

    def __init__(self) -> None:
        self._on_state: StateHandler | None = None
        self._on_event: EventHandler | None = None

    def subscribe(self, on_state: StateHandler, on_event: EventHandler) -> None:
        """Handlers are called on the event loop thread."""
        self._on_state = on_state
        self._on_event = on_event

    # --- lifecycle
    @abstractmethod
    async def connect(self) -> None:
        """Raise LinkError if no heartbeat arrives."""

    @abstractmethod
    async def disconnect(self) -> None: ...

    # --- mission, fence, settings
    @abstractmethod
    async def upload_mission(self, items: Sequence[MissionItem]) -> CommandResult: ...

    @abstractmethod
    async def read_mission(self) -> list[MissionItem]:
        """What the vehicle actually holds, for the read-back comparison."""

    @abstractmethod
    async def upload_fence(
        self, polygon: Sequence[tuple[float, float]], max_alt_m: float
    ) -> CommandResult:
        """Inclusion polygon as (lat, lon) vertices. An empty polygon clears the fence."""

    @abstractmethod
    async def apply_safety(self, safety: SafetyConfig) -> CommandResult: ...

    # --- commands
    @abstractmethod
    async def arm(self) -> CommandResult: ...

    @abstractmethod
    async def disarm(self) -> CommandResult: ...

    @abstractmethod
    async def takeoff(self, alt_rel_m: float) -> CommandResult: ...

    @abstractmethod
    async def start_mission(self) -> CommandResult: ...

    @abstractmethod
    async def pause(self) -> CommandResult: ...

    @abstractmethod
    async def resume(self) -> CommandResult: ...

    @abstractmethod
    async def rtl(self) -> CommandResult: ...

    @abstractmethod
    async def land(self) -> CommandResult: ...

    @abstractmethod
    async def goto(self, lat: float, lon: float, alt_rel_m: float) -> CommandResult:
        """Fly to a point and hold there."""

    @abstractmethod
    async def set_velocity(
        self, forward_mps: float, right_mps: float, up_mps: float, yaw_rate_dps: float
    ) -> CommandResult:
        """Operator stick input in the vehicle's body frame. Must be re-sent several
        times a second; the vehicle stops and holds when the input stops arriving."""
