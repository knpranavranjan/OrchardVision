import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.api import flights, geocode, missions, orchards, system, vehicle
from app.config import Settings, get_settings
from app.db.session import Database
from app.flight.manager import FlightManager
from app.log import configure_logging
from app.registry import ModelRegistry, RegistryError
from app.registry.sync import sync_registry
from app.ws.hub import Hub

log = logging.getLogger("orchardvision")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(settings.log_level)
        log.info("OrchardVision backend %s starting (%s)", __version__, settings.env)
        if app.state.db.ping():
            try:
                with app.state.db.session() as session:
                    counts = sync_registry(session, app.state.registry)
                log.info("registry mirrored to database: %s", counts)
            except (RegistryError, SQLAlchemyError) as e:  # a bad profile must not stop startup
                log.warning("registry sync skipped: %s", e)
        else:
            log.warning("database unreachable; start it with: docker compose up -d db")
        await app.state.manager.start()
        yield
        await app.state.manager.stop()
        app.state.db.dispose()

    app = FastAPI(title="OrchardVision", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.registry = ModelRegistry(settings.models_dir)
    app.state.db = Database(settings.database_url)
    app.state.hub = Hub()
    app.state.manager = FlightManager(settings, app.state.db, app.state.hub, app.state.registry)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (system, orchards, missions, vehicle, flights, geocode):
        app.include_router(module.router)
    app.include_router(vehicle.ws_router)
    return app


app = create_app()
