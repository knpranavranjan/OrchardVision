"""The mission plan: what the operator intends. The compiler turns it into mission items."""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.vehicle.link import SafetyConfig


class LatLon(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)

    def tuple(self) -> tuple[float, float]:
        return self.lat, self.lon


class CameraProfile(BaseModel):
    id: str = "rpi-gs-6mm"
    name: str = "Raspberry Pi Global Shutter, 6 mm lens"
    sensor_width_mm: float = 5.02
    sensor_height_mm: float = 3.75
    focal_length_mm: float = 6.0
    image_width_px: int = 1456
    image_height_px: int = 1088
    image_mb: float = 1.5

    def gsd_cm(self, altitude_m: float) -> float:
        """Ground covered by one pixel, in centimetres."""
        return (
            self.sensor_width_mm * altitude_m / (self.focal_length_mm * self.image_width_px) * 100
        )

    def footprint_m(self, altitude_m: float) -> tuple[float, float]:
        """Ground covered by one photo: (across the flight line, along it)."""
        return (
            self.sensor_width_mm * altitude_m / self.focal_length_mm,
            self.sensor_height_mm * altitude_m / self.focal_length_mm,
        )


DEFAULT_CAMERAS = [
    CameraProfile(),
    CameraProfile(
        id="rpi-hq-6mm",
        name="Raspberry Pi HQ (12 MP), 6 mm lens",
        sensor_width_mm=6.287,
        sensor_height_mm=4.712,
        focal_length_mm=6.0,
        image_width_px=4056,
        image_height_px=3040,
        image_mb=6.0,
    ),
    CameraProfile(
        id="one-inch-20mp",
        name="One-inch 20 MP, 8.8 mm lens",
        sensor_width_mm=13.2,
        sensor_height_mm=8.8,
        focal_length_mm=8.8,
        image_width_px=5472,
        image_height_px=3648,
        image_mb=10.0,
    ),
]


class VehicleProfile(BaseModel):
    name: str = "Quadcopter, 4S 5200 mAh"
    cruise_speed_mps: float = 5.0
    max_speed_mps: float = 10.0
    climb_rate_mps: float = 2.5
    descent_rate_mps: float = 1.5
    endurance_min: float = Field(default=18.0, gt=0)
    turn_time_s: float = 3.0


class MissionType(StrEnum):
    SURVEY = "survey"
    WAYPOINTS = "waypoints"


class EndAction(StrEnum):
    RTL = "rtl"
    LAND = "land"


class SurveySpec(BaseModel):
    polygon: list[LatLon] = Field(default_factory=list)
    altitude_m: float = Field(default=25.0, gt=0)
    speed_mps: float = Field(default=3.0, gt=0)
    front_overlap: float = Field(default=0.8, ge=0, lt=0.95)
    side_overlap: float = Field(default=0.7, ge=0, lt=0.95)
    angle_deg: float = Field(default=0.0, description="Heading of the flight lines")
    gimbal_pitch_deg: float = Field(default=-90.0, ge=-90, le=0)
    overshoot_m: float = Field(default=0.0, ge=0, le=50)


class WaypointSpec(BaseModel):
    lat: float
    lon: float
    alt_m: float = Field(default=20.0, gt=0)
    hold_s: float = Field(default=0.0, ge=0)
    speed_mps: float | None = Field(default=None, gt=0)


class MissionPlan(BaseModel):
    type: MissionType = MissionType.SURVEY
    home: LatLon
    takeoff_alt_m: float = Field(default=25.0, gt=0)
    survey: SurveySpec | None = None
    waypoints: list[WaypointSpec] = Field(default_factory=list)
    waypoint_speed_mps: float = Field(default=4.0, gt=0)
    waypoint_capture_distance_m: float = Field(default=0.0, ge=0)
    waypoint_gimbal_pitch_deg: float = Field(default=-90.0, ge=-90, le=0)
    geofence: list[LatLon] = Field(default_factory=list)
    end_action: EndAction = EndAction.RTL
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    camera: CameraProfile = Field(default_factory=CameraProfile)
    vehicle: VehicleProfile = Field(default_factory=VehicleProfile)

    @model_validator(mode="after")
    def _has_body(self) -> "MissionPlan":
        if self.type == MissionType.SURVEY and self.survey is None:
            self.survey = SurveySpec()
        return self
