"""Connection, pre-flight, mission upload, commands and the live channel."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.api.deps import get_manager
from app.flight.manager import ConnectSpec, FlightManager
from app.flight.preflight import Preflight
from app.vehicle.link import CommandResult, LinkError
from app.ws.hub import Hub, envelope

router = APIRouter(prefix="/api/vehicle", tags=["vehicle"])
ws_router = APIRouter()

Mgr = Annotated[FlightManager, Depends(get_manager)]

MAX_MANUAL_SPEED = 5.0
MAX_MANUAL_CLIMB = 2.0
MAX_MANUAL_YAW = 60.0


class CommandIn(BaseModel):
    command: str
    args: dict[str, Any] = Field(default_factory=dict)


class ConfirmIn(BaseModel):
    id: str
    value: bool


class InjectIn(BaseModel):
    battery_pct: float | None = Field(default=None, ge=0, le=100)
    gps_ok: bool | None = None
    wind_mps: float | None = Field(default=None, ge=0, le=25)
    wind_from_deg: float | None = None
    speedup: float | None = Field(default=None, ge=0.1, le=20)
    link_blackout_s: float | None = Field(default=None, ge=0, le=60)


@router.get("/ports")
def ports() -> list[dict[str, str]]:
    from app.vehicle.mavlink import list_serial_ports

    return list_serial_ports()


@router.get("/status")
async def status(manager: Mgr) -> dict:
    return manager.full_status()


@router.post("/connect")
async def connect(spec: ConnectSpec, manager: Mgr) -> dict:
    try:
        await manager.connect(spec)
    except LinkError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return manager.full_status()


@router.post("/disconnect")
async def disconnect(manager: Mgr) -> dict:
    try:
        await manager.disconnect()
    except LinkError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return manager.full_status()


@router.get("/preflight")
async def preflight(manager: Mgr) -> Preflight:
    return manager.preflight()


@router.post("/preflight/confirm")
async def confirm(body: ConfirmIn, manager: Mgr) -> Preflight:
    try:
        manager.confirm(body.id, body.value)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="Not a manual check") from e
    return manager.preflight()


@router.post("/mission/{mission_id}/upload")
async def upload(mission_id: int, manager: Mgr, segment: int = 0) -> dict:
    try:
        return await manager.upload_mission(mission_id, segment)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except LinkError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("/command")
async def command(body: CommandIn, manager: Mgr) -> CommandResult:
    return await manager.command(body.command, body.args)


@router.post("/sim/conditions")
async def sim_conditions(body: InjectIn, manager: Mgr) -> dict:
    try:
        manager.inject(**body.model_dump())
    except LinkError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return manager.summary()


def _clamp(value: Any, limit: float) -> float:
    try:
        return max(-limit, min(limit, float(value)))
    except (TypeError, ValueError):
        return 0.0


@ws_router.websocket("/ws")
async def websocket(ws: WebSocket) -> None:
    hub: Hub = ws.app.state.hub
    manager: FlightManager = ws.app.state.manager
    await hub.connect(ws)
    try:
        await ws.send_json(envelope("snapshot", manager.full_status(), "vehicle"))
        while True:
            message = await ws.receive_json()
            kind = message.get("type")
            if kind == "ping":
                await ws.send_json(envelope("pong", message.get("data")))
            elif kind == "manual":
                d = message.get("data") or {}
                await manager.manual(
                    _clamp(d.get("forward"), MAX_MANUAL_SPEED),
                    _clamp(d.get("right"), MAX_MANUAL_SPEED),
                    _clamp(d.get("up"), MAX_MANUAL_CLIMB),
                    _clamp(d.get("yaw_rate"), MAX_MANUAL_YAW),
                )
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(ws)
