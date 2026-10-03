from collections.abc import Iterator

from fastapi import HTTPException, Request
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import Settings
from app.flight.manager import FlightManager
from app.registry import ModelRegistry


def get_session(request: Request) -> Iterator[Session]:
    try:
        with request.app.state.db.session() as session:
            yield session
    except OperationalError as e:
        raise HTTPException(
            status_code=503, detail="Database unreachable. Start it with: docker compose up -d db"
        ) from e


def get_manager(request: Request) -> FlightManager:
    return request.app.state.manager


def get_registry(request: Request) -> ModelRegistry:
    return request.app.state.registry


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings
