"""Database tables for the ground station.

Geometry is stored as lists of [lat, lon] in JSON columns. PostGIS is installed
for the analysis phases; the ground station itself does its geometry in Python.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _updated() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Crop(Base):
    __tablename__ = "crop"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # slug, e.g. "papaya"
    name: Mapped[str] = mapped_column(String(128))
    plant_architecture: Mapped[str] = mapped_column(String(32))
    profile: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = _updated()

    model_versions: Mapped[list["ModelVersion"]] = relationship(
        back_populates="crop", cascade="all, delete-orphan"
    )


class ModelVersion(Base):
    __tablename__ = "model_version"
    __table_args__ = (UniqueConstraint("crop_id", "kind", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    crop_id: Mapped[str] = mapped_column(ForeignKey("crop.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))  # tree | fruit
    version: Mapped[str] = mapped_column(String(64))
    framework: Mapped[str] = mapped_column(String(32))
    sha256: Mapped[str] = mapped_column(String(64))
    # active | available | missing | checksum_mismatch
    status: Mapped[str] = mapped_column(String(32))
    manifest: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = _updated()

    crop: Mapped[Crop] = relationship(back_populates="model_versions")


class Orchard(Base):
    __tablename__ = "orchard"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    crop_id: Mapped[str] = mapped_column(String(64))
    boundary: Mapped[list] = mapped_column(JSON, default=list)  # [[lat, lon], ...]
    area_ha: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str] = mapped_column(Text, default="")
    # Model versions pinned for this orchard; null means the crop's active version.
    tree_model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fruit_model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Mission(Base):
    __tablename__ = "mission"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    orchard_id: Mapped[int | None] = mapped_column(
        ForeignKey("orchard.id", ondelete="SET NULL"), nullable=True
    )
    plan: Mapped[dict] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    valid: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Flight(Base):
    __tablename__ = "flight"

    id: Mapped[int] = mapped_column(primary_key=True)
    mission_id: Mapped[int | None] = mapped_column(
        ForeignKey("mission.id", ondelete="SET NULL"), nullable=True
    )
    mission_name: Mapped[str] = mapped_column(String(128), default="")
    mission_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    segment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vehicle_kind: Mapped[str] = mapped_column(String(16))
    vehicle_description: Mapped[str] = mapped_column(String(128), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="in_progress")
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    # What was planned, frozen at take-off, so the record stays readable if the mission changes.
    plan_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)


class TelemetrySample(Base):
    __tablename__ = "telemetry_sample"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    flight_id: Mapped[int] = mapped_column(ForeignKey("flight.id", ondelete="CASCADE"), index=True)
    t: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    alt_rel_m: Mapped[float] = mapped_column(Float)
    heading_deg: Mapped[float] = mapped_column(Float)
    groundspeed_mps: Mapped[float] = mapped_column(Float)
    vel_up_mps: Mapped[float] = mapped_column(Float)
    roll_deg: Mapped[float] = mapped_column(Float)
    pitch_deg: Mapped[float] = mapped_column(Float)
    battery_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    satellites: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(16))
    mission_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)


class FlightEvent(Base):
    __tablename__ = "flight_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    flight_id: Mapped[int] = mapped_column(ForeignKey("flight.id", ondelete="CASCADE"), index=True)
    t: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(24))
    severity: Mapped[str] = mapped_column(String(12))
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class Capture(Base):
    __tablename__ = "capture"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    flight_id: Mapped[int] = mapped_column(ForeignKey("flight.id", ondelete="CASCADE"), index=True)
    index: Mapped[int] = mapped_column(Integer)
    t: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    alt_rel_m: Mapped[float] = mapped_column(Float)
    heading_deg: Mapped[float] = mapped_column(Float)
    gimbal_pitch_deg: Mapped[float] = mapped_column(Float)
    mission_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Setting(Base):
    __tablename__ = "setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = _updated()
