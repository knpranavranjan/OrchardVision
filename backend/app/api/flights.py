"""Flight records and replay data."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_manager, get_session
from app.core.conventions import to_iso_ms
from app.db.tables import Capture, Flight, FlightEvent, TelemetrySample
from app.flight.manager import FlightManager

router = APIRouter(prefix="/api/flights", tags=["flights"])

Db = Annotated[Session, Depends(get_session)]


def _summary(f: Flight) -> dict:
    return {
        "id": f.id,
        "mission_id": f.mission_id,
        "mission_name": f.mission_name,
        "mission_revision": f.mission_revision,
        "segment": f.segment,
        "vehicle_kind": f.vehicle_kind,
        "vehicle_description": f.vehicle_description,
        "started_at": f.started_at,
        "ended_at": f.ended_at,
        "status": f.status,
        "summary": f.summary,
    }


@router.get("")
def list_flights(session: Db, limit: int = 100) -> list[dict]:
    rows = session.scalars(select(Flight).order_by(Flight.started_at.desc()).limit(limit)).all()
    return [_summary(f) for f in rows]


def _get(session: Session, flight_id: int) -> Flight:
    f = session.get(Flight, flight_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Flight not found")
    return f


@router.get("/{flight_id}")
def get_flight(flight_id: int, session: Db) -> dict:
    """Everything needed to replay a flight."""
    f = _get(session, flight_id)
    samples = session.scalars(
        select(TelemetrySample)
        .where(TelemetrySample.flight_id == flight_id)
        .order_by(TelemetrySample.t)
    ).all()
    events = session.scalars(
        select(FlightEvent).where(FlightEvent.flight_id == flight_id).order_by(FlightEvent.t)
    ).all()
    captures = session.scalars(
        select(Capture).where(Capture.flight_id == flight_id).order_by(Capture.index)
    ).all()
    t0 = f.started_at
    return {
        **_summary(f),
        "plan_snapshot": f.plan_snapshot,
        "telemetry": [
            {
                "t": round((s.t - t0).total_seconds(), 2),
                "lat": s.lat,
                "lon": s.lon,
                "alt": s.alt_rel_m,
                "hdg": s.heading_deg,
                "spd": s.groundspeed_mps,
                "vz": s.vel_up_mps,
                "roll": s.roll_deg,
                "pitch": s.pitch_deg,
                "batt": s.battery_pct,
                "sats": s.satellites,
                "mode": s.mode,
                "seq": s.mission_seq,
            }
            for s in samples
        ],
        "events": [
            {
                "t": round((e.t - t0).total_seconds(), 2),
                "time": e.t,
                "kind": e.kind,
                "severity": e.severity,
                "message": e.message,
            }
            for e in events
        ],
        "captures": [
            {
                "index": c.index,
                "t": round((c.t - t0).total_seconds(), 2),
                "lat": c.lat,
                "lon": c.lon,
                "alt": c.alt_rel_m,
                "hdg": c.heading_deg,
                "gimbal": c.gimbal_pitch_deg,
            }
            for c in captures
        ],
    }


@router.get("/{flight_id}/captures.csv", response_class=PlainTextResponse)
def captures_csv(flight_id: int, session: Db) -> PlainTextResponse:
    """The capture log: one row per photo, for matching image files after the flight."""
    _get(session, flight_id)
    rows = session.scalars(
        select(Capture).where(Capture.flight_id == flight_id).order_by(Capture.index)
    ).all()
    lines = ["index,time_utc,lat,lon,alt_rel_m,heading_deg,gimbal_pitch_deg,mission_seq"]
    lines += [
        f"{c.index},{to_iso_ms(c.t)},{c.lat:.7f},{c.lon:.7f},{c.alt_rel_m:.2f},"
        f"{c.heading_deg:.1f},{c.gimbal_pitch_deg:.1f},"
        f"{'' if c.mission_seq is None else c.mission_seq}"
        for c in rows
    ]
    return PlainTextResponse(
        "\n".join(lines) + "\n",
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="flight_{flight_id}_captures.csv"'},
    )


@router.delete("/{flight_id}", status_code=204)
def delete_flight(
    flight_id: int, session: Db, manager: Annotated[FlightManager, Depends(get_manager)]
) -> None:
    f = _get(session, flight_id)
    if (
        f.status == "in_progress"
        and manager.recorder.flight_id == flight_id
        and manager.recorder.active
    ):
        raise HTTPException(status_code=409, detail="This flight is still being recorded")
    session.delete(f)


@router.get("/stats/totals")
def totals(session: Db) -> dict:
    count = session.scalar(select(func.count()).select_from(Flight)) or 0
    captures = session.scalar(select(func.count()).select_from(Capture)) or 0
    return {"flights": count, "captures": captures}
