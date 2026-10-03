"""Shared builders for tests."""

from app.core.conventions import LocalFrame
from app.mission.schema import DEFAULT_CAMERAS, LatLon, MissionPlan, SurveySpec
from app.vehicle.link import EventKind, VehicleEvent, VehicleState
from app.vehicle.sim import KinematicSim, SimOptions

HOME = LatLon(lat=12.9716, lon=77.5946)
FRAME = LocalFrame(HOME.lat, HOME.lon)
ONE_INCH = DEFAULT_CAMERAS[2]


def rect(east0: float, north0: float, east1: float, north1: float) -> list[LatLon]:
    """A rectangle given in metres east and north of HOME."""
    corners = [(east0, north0), (east1, north0), (east1, north1), (east0, north1)]
    return [LatLon(lat=lat, lon=lon) for lat, lon in (FRAME.to_latlon(e, n) for e, n in corners)]


def survey_plan(**survey: float) -> MissionPlan:
    """A 100 m by 60 m block starting 10 m north-east of home, fenced with a 20 m margin."""
    return MissionPlan(
        home=HOME,
        takeoff_alt_m=25,
        survey=SurveySpec(polygon=rect(10, 10, 110, 70), **survey),
        geofence=rect(-20, -20, 130, 90),
        camera=ONE_INCH,
    )


class Recorder:
    """Collects what a link emits."""

    def __init__(self) -> None:
        self.states: list[VehicleState] = []
        self.events: list[VehicleEvent] = []

    def of(self, kind: EventKind) -> list[VehicleEvent]:
        return [e for e in self.events if e.kind == kind]


def make_sim(**options: float) -> tuple[KinematicSim, Recorder]:
    sim = KinematicSim(SimOptions(home_lat=HOME.lat, home_lon=HOME.lon, **options))
    rec = Recorder()
    sim.subscribe(rec.states.append, rec.events.append)
    return sim, rec


def run(sim: KinematicSim, until, max_seconds: float = 3600.0, dt: float = 0.05) -> float:
    """Step the simulator until the condition holds. Returns simulated seconds used."""
    start = sim.t
    while not until():
        sim.step(dt)
        if sim.t - start > max_seconds:
            raise AssertionError(f"condition not reached in {max_seconds} simulated seconds")
    return sim.t - start
