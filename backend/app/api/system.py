"""Health, the model registry, and application settings."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import __version__
from app.api.deps import get_registry, get_session
from app.core.conventions import to_iso_ms, utc_now
from app.db.tables import Setting
from app.mission.schema import DEFAULT_CAMERAS, CameraProfile, LatLon, VehicleProfile
from app.registry import ModelRegistry, RegistryError, ResolvedModel
from app.vehicle.link import SafetyConfig

router = APIRouter(prefix="/api", tags=["system"])


class AppSettings(BaseModel):
    """Defaults applied to new missions, and the saved connection choices."""

    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    vehicle: VehicleProfile = Field(default_factory=VehicleProfile)
    cameras: list[CameraProfile] = Field(default_factory=lambda: list(DEFAULT_CAMERAS))
    default_camera_id: str = DEFAULT_CAMERAS[0].id
    map_center: LatLon = LatLon(lat=12.9716, lon=77.5946)
    serial_baud: int = 57600
    sitl_url: str = "tcp:127.0.0.1:5760"
    udp_url: str = "udpin:0.0.0.0:14550"


def _model_row(m: ResolvedModel) -> dict:
    return {
        "crop": m.crop,
        "kind": m.kind.value,
        "version": m.manifest.version,
        "framework": m.manifest.framework,
        "status": m.status,
        "sha256": m.manifest.sha256,
        "metrics": m.manifest.metrics,
        "notes": m.manifest.notes,
    }


@router.get("/health")
def health(request: Request) -> dict:
    registry: ModelRegistry = request.app.state.registry
    db_ok = request.app.state.db.ping()
    try:
        crops = len(registry.crops())
        registry_ok = True
    except RegistryError:
        crops = 0
        registry_ok = False
    return {
        "status": "ok" if db_ok and registry_ok else "degraded",
        "version": __version__,
        "time": to_iso_ms(utc_now()),
        "database": "ok" if db_ok else "down",
        "registry": {"ok": registry_ok, "crops": crops},
        "ws_clients": request.app.state.hub.client_count,
        "link": request.app.state.manager.status.value,
    }


@router.get("/crops")
def list_crops(registry: Annotated[ModelRegistry, Depends(get_registry)]) -> list[dict]:
    return [c.model_dump(mode="json") for c in registry.crops()]


@router.get("/crops/{crop}")
def get_crop(crop: str, registry: Annotated[ModelRegistry, Depends(get_registry)]) -> dict:
    try:
        return registry.crop(crop).model_dump(mode="json")
    except RegistryError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/models")
def list_models(registry: Annotated[ModelRegistry, Depends(get_registry)]) -> list[dict]:
    return [_model_row(m) for m in registry.all_versions()]


def load_settings(session: Session) -> AppSettings:
    row = session.get(Setting, "app")
    return AppSettings.model_validate(row.value) if row else AppSettings()


@router.get("/settings")
def get_settings_(session: Annotated[Session, Depends(get_session)]) -> AppSettings:
    return load_settings(session)


@router.put("/settings")
def put_settings(
    body: AppSettings, session: Annotated[Session, Depends(get_session)]
) -> AppSettings:
    if not any(c.id == body.default_camera_id for c in body.cameras):
        raise HTTPException(status_code=422, detail="The default camera is not in the camera list")
    row = session.get(Setting, "app")
    if row is None:
        row = Setting(key="app")
        session.add(row)
    row.value = body.model_dump(mode="json")
    return body
