from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_registry, get_session
from app.core.conventions import LocalFrame
from app.core.geometry import is_simple_polygon, polygon_area
from app.db.tables import Orchard
from app.mission.schema import LatLon
from app.mission.service import crop_context
from app.registry import ModelKind, ModelRegistry, RegistryError

router = APIRouter(prefix="/api/orchards", tags=["orchards"])


class OrchardIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    crop: str
    boundary: list[LatLon] = Field(default_factory=list)
    notes: str = ""
    tree_model_version: str | None = None
    fruit_model_version: str | None = None


def area_ha(boundary: list[LatLon]) -> float:
    if len(boundary) < 3:
        return 0.0
    frame = LocalFrame(boundary[0].lat, boundary[0].lon)
    return round(polygon_area([frame.to_en(p.lat, p.lon) for p in boundary]) / 10_000.0, 3)


def _out(o: Orchard, registry: ModelRegistry) -> dict:
    ctx = crop_context(registry, o)
    return {
        "id": o.id,
        "name": o.name,
        "crop": o.crop_id,
        "boundary": [{"lat": lat, "lon": lon} for lat, lon in o.boundary],
        "area_ha": o.area_ha,
        "notes": o.notes,
        "tree_model_version": o.tree_model_version,
        "fruit_model_version": o.fruit_model_version,
        "models_ready": ctx.models_ready if ctx else False,
        "models_detail": ctx.models_detail if ctx else "",
        "created_at": o.created_at,
        "updated_at": o.updated_at,
    }


def _apply(o: Orchard, body: OrchardIn, registry: ModelRegistry) -> None:
    try:
        registry.crop(body.crop)
        for kind, version in (
            (ModelKind.TREE, body.tree_model_version),
            (ModelKind.FRUIT, body.fruit_model_version),
        ):
            if version:
                registry.resolve(body.crop, kind, version)
    except RegistryError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if len(body.boundary) >= 3:
        frame = LocalFrame(body.boundary[0].lat, body.boundary[0].lon)
        if not is_simple_polygon([frame.to_en(p.lat, p.lon) for p in body.boundary]):
            raise HTTPException(status_code=422, detail="The boundary's edges cross each other")
    o.name = body.name
    o.crop_id = body.crop
    o.boundary = [[p.lat, p.lon] for p in body.boundary]
    o.area_ha = area_ha(body.boundary)
    o.notes = body.notes
    o.tree_model_version = body.tree_model_version
    o.fruit_model_version = body.fruit_model_version


Db = Annotated[Session, Depends(get_session)]
Reg = Annotated[ModelRegistry, Depends(get_registry)]


@router.get("")
def list_orchards(session: Db, registry: Reg) -> list[dict]:
    rows = session.scalars(select(Orchard).order_by(Orchard.name)).all()
    return [_out(o, registry) for o in rows]


@router.post("", status_code=201)
def create_orchard(body: OrchardIn, session: Db, registry: Reg) -> dict:
    o = Orchard()
    _apply(o, body, registry)
    session.add(o)
    session.flush()
    session.refresh(o)
    return _out(o, registry)


def _get(session: Session, orchard_id: int) -> Orchard:
    o = session.get(Orchard, orchard_id)
    if o is None:
        raise HTTPException(status_code=404, detail="Orchard not found")
    return o


@router.get("/{orchard_id}")
def get_orchard(orchard_id: int, session: Db, registry: Reg) -> dict:
    return _out(_get(session, orchard_id), registry)


@router.put("/{orchard_id}")
def update_orchard(orchard_id: int, body: OrchardIn, session: Db, registry: Reg) -> dict:
    o = _get(session, orchard_id)
    _apply(o, body, registry)
    session.flush()
    session.refresh(o)
    return _out(o, registry)


@router.delete("/{orchard_id}", status_code=204)
def delete_orchard(orchard_id: int, session: Db) -> None:
    session.delete(_get(session, orchard_id))
