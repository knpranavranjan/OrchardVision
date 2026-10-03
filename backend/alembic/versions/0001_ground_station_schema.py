"""ground station schema

Revision ID: 0001
Revises:
Create Date: 2026-10-03 09:59:40.419952
"""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostGIS is for the analysis sections; the ground station stores geometry as JSON.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "crop",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("plant_architecture", sa.String(length=32), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "orchard",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("crop_id", sa.String(length=64), nullable=False),
        sa.Column("boundary", sa.JSON(), nullable=False),
        sa.Column("area_ha", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("tree_model_version", sa.String(length=64), nullable=True),
        sa.Column("fruit_model_version", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "setting",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "mission",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("orchard_id", sa.Integer(), nullable=True),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["orchard_id"], ["orchard.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "model_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("crop_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("framework", sa.String(length=32), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["crop_id"], ["crop.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("crop_id", "kind", "version"),
    )
    op.create_table(
        "flight",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mission_id", sa.Integer(), nullable=True),
        sa.Column("mission_name", sa.String(length=128), nullable=False),
        sa.Column("mission_revision", sa.Integer(), nullable=True),
        sa.Column("segment", sa.Integer(), nullable=True),
        sa.Column("vehicle_kind", sa.String(length=16), nullable=False),
        sa.Column("vehicle_description", sa.String(length=128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("plan_snapshot", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["mission_id"], ["mission.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "capture",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("flight_id", sa.Integer(), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("t", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("alt_rel_m", sa.Float(), nullable=False),
        sa.Column("heading_deg", sa.Float(), nullable=False),
        sa.Column("gimbal_pitch_deg", sa.Float(), nullable=False),
        sa.Column("mission_seq", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["flight_id"], ["flight.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_capture_flight_id"), "capture", ["flight_id"], unique=False)
    op.create_table(
        "flight_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("flight_id", sa.Integer(), nullable=False),
        sa.Column("t", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("severity", sa.String(length=12), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["flight_id"], ["flight.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_flight_event_flight_id"), "flight_event", ["flight_id"], unique=False)
    op.create_table(
        "telemetry_sample",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("flight_id", sa.Integer(), nullable=False),
        sa.Column("t", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("alt_rel_m", sa.Float(), nullable=False),
        sa.Column("heading_deg", sa.Float(), nullable=False),
        sa.Column("groundspeed_mps", sa.Float(), nullable=False),
        sa.Column("vel_up_mps", sa.Float(), nullable=False),
        sa.Column("roll_deg", sa.Float(), nullable=False),
        sa.Column("pitch_deg", sa.Float(), nullable=False),
        sa.Column("battery_pct", sa.Float(), nullable=True),
        sa.Column("satellites", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("mission_seq", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["flight_id"], ["flight.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_telemetry_sample_flight_id"), "telemetry_sample", ["flight_id"], unique=False
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_telemetry_sample_flight_id"), table_name="telemetry_sample")
    op.drop_table("telemetry_sample")
    op.drop_index(op.f("ix_flight_event_flight_id"), table_name="flight_event")
    op.drop_table("flight_event")
    op.drop_index(op.f("ix_capture_flight_id"), table_name="capture")
    op.drop_table("capture")
    op.drop_table("flight")
    op.drop_table("model_version")
    op.drop_table("mission")
    op.drop_table("setting")
    op.drop_table("orchard")
    op.drop_table("crop")
    # ### end Alembic commands ###
