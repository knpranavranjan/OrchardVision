from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_registry, get_session
from app.config import Settings
from app.db.tables import Mission, Orchard
from app.mission.export import to_kml, to_qgc_plan, to_waypoints
from app.mission.schema import MissionPlan
from app.mission.service import Evaluated, evaluate_plan
from app.registry import ModelRegistry

router = APIRouter(prefix="/api/missions", tags=["missions"])

Db = Annotated[Session, Depends(get_session)]
Reg = Annotated[ModelRegistry, Depends(get_registry)]
Cfg = Annotated[Settings, Depends(get_app_settings)]


class MissionIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    orchard_id: int | None = None
    plan: MissionPlan


class PreviewIn(BaseModel):
    orchard_id: int | None = None
    plan: MissionPlan


def _orchard(session: Session, orchard_id: int | None) -> Orchard | None:
    if orchard_id is None:
        return None
    orchard = session.get(Orchard, orchard_id)
    if orchard is None:
        raise HTTPException(status_code=422, detail="Orchard not found")
    return orchard


def _evaluation(ev: Evaluated) -> dict:
    c = ev.compiled
    return {
        "items": [i.model_dump(mode="json") for i in c.items],
        "route": c.route,
        "lines": c.lines,
        "capture_points": c.capture_points,
        "stats": c.stats.model_dump(),
        "segments": [
            {
                "index": s.index,
                "first_line": s.first_line,
                "last_line": s.last_line,
                "item_count": len(s.items),
                "estimate": s.estimate.model_dump(),
            }
            for s in c.segments
        ],
        "validation": ev.validation.model_dump(mode="json"),
    }


def _summary(m: Mission) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "orchard_id": m.orchard_id,
        "type": m.plan.get("type"),
        "revision": m.revision,
        "valid": m.valid,
        "stats": m.stats,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }


@router.post("/preview")
def preview(body: PreviewIn, session: Db, registry: Reg, cfg: Cfg) -> dict:
    """Compile and validate a plan without saving it. The planner calls this as you draw."""
    ev = evaluate_plan(body.plan, registry, _orchard(session, body.orchard_id), cfg.data_dir)
    return _evaluation(ev)


@router.get("")
def list_missions(session: Db) -> list[dict]:
    rows = session.scalars(select(Mission).order_by(Mission.updated_at.desc())).all()
    return [_summary(m) for m in rows]


@router.post("", status_code=201)
def create_mission(body: MissionIn, session: Db, registry: Reg, cfg: Cfg) -> dict:
    ev = evaluate_plan(body.plan, registry, _orchard(session, body.orchard_id), cfg.data_dir)
    m = Mission(
        name=body.name,
        orchard_id=body.orchard_id,
        plan=body.plan.model_dump(mode="json"),
        revision=1,
        stats=ev.compiled.stats.model_dump(),
        valid=ev.validation.ok,
    )
    session.add(m)
    session.flush()
    session.refresh(m)
    return {**_summary(m), "plan": m.plan, **_evaluation(ev)}


def _get(session: Session, mission_id: int) -> Mission:
    m = session.get(Mission, mission_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return m


@router.get("/{mission_id}")
def get_mission(mission_id: int, session: Db, registry: Reg, cfg: Cfg) -> dict:
    m = _get(session, mission_id)
    plan = MissionPlan.model_validate(m.plan)
    ev = evaluate_plan(plan, registry, _orchard(session, m.orchard_id), cfg.data_dir)
    return {**_summary(m), "plan": m.plan, **_evaluation(ev)}


@router.put("/{mission_id}")
def update_mission(mission_id: int, body: MissionIn, session: Db, registry: Reg, cfg: Cfg) -> dict:
    m = _get(session, mission_id)
    ev = evaluate_plan(body.plan, registry, _orchard(session, body.orchard_id), cfg.data_dir)
    new_plan = body.plan.model_dump(mode="json")
    if new_plan != m.plan:
        m.revision += 1  # a flown revision stays identifiable in flight records
    m.name = body.name
    m.orchard_id = body.orchard_id
    m.plan = new_plan
    m.stats = ev.compiled.stats.model_dump()
    m.valid = ev.validation.ok
    session.flush()
    session.refresh(m)
    return {**_summary(m), "plan": m.plan, **_evaluation(ev)}


@router.delete("/{mission_id}", status_code=204)
def delete_mission(mission_id: int, session: Db) -> None:
    session.delete(_get(session, mission_id))


@router.get("/{mission_id}/export/{fmt}", response_class=PlainTextResponse)
def export_mission(
    mission_id: int, fmt: str, session: Db, registry: Reg, cfg: Cfg, segment: int = 0
) -> PlainTextResponse:
    m = _get(session, mission_id)
    plan = MissionPlan.model_validate(m.plan)
    ev = evaluate_plan(plan, registry, _orchard(session, m.orchard_id), cfg.data_dir)
    if not 0 <= segment < len(ev.compiled.segments):
        raise HTTPException(status_code=404, detail="No such flight segment")
    items = ev.compiled.segments[segment].items
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in m.name)
    if fmt == "qgc":
        body, ext, media = to_qgc_plan(plan, items), "plan", "application/json"
    elif fmt == "waypoints":
        body, ext, media = to_waypoints(plan, items), "waypoints", "text/plain"
    elif fmt == "kml":
        body, ext, media = to_kml(m.name, plan, ev.compiled.route), "kml", "application/xml"
    else:
        raise HTTPException(status_code=404, detail="Formats: qgc, waypoints, kml")
    return PlainTextResponse(
        body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{safe}.{ext}"'},
    )
