"""PostgreSQL/PostGIS schema.

Owner: M3 (data tables) and M1 (Strategy/SimulationRun/Result/DecisionRecord). Changes need M1 approval
plus a new Alembic migration (``make migration m="..."``). Never edit an applied migration.

Storage rule: queryable data lives here; immutable raw files, rasters and Parquet traces live on disk
and are referenced by path + SHA-256.
"""

from datetime import date, datetime
from typing import Any, ClassVar

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSONB, list[Any]: JSONB}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserRow(TimestampMixin, Base):
    __tablename__ = "app_user"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSessionRow(Base):
    __tablename__ = "user_session"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SiteRow(TimestampMixin, Base):
    __tablename__ = "site"

    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("app_user.id"), index=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    boundary = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64))
    area_ha: Mapped[float | None] = mapped_column(Float)
    farmer_context: Mapped[dict[str, Any]] = mapped_column(default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class SourceRow(TimestampMixin, Base):
    __tablename__ = "source"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(200))
    product: Mapped[str] = mapped_column(String(200))
    version: Mapped[str | None] = mapped_column(String(64))
    variables: Mapped[list[Any]] = mapped_column(default=list)
    units: Mapped[dict[str, Any]] = mapped_column(default=dict)
    kind: Mapped[str] = mapped_column(String(32))
    spatial_resolution: Mapped[str | None] = mapped_column(String(64))
    temporal_resolution: Mapped[str | None] = mapped_column(String(64))
    coverage_start: Mapped[date | None] = mapped_column(Date)
    coverage_end: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    url: Mapped[str | None] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(String(200))
    license: Mapped[str | None] = mapped_column(String(200))
    attribution: Mapped[str | None] = mapped_column(Text)
    qa_notes: Mapped[str | None] = mapped_column(Text)
    limitations: Mapped[str | None] = mapped_column(Text)
    footprint = mapped_column(Geometry("GEOMETRY", srid=4326), nullable=True)
    raw_path: Mapped[str | None] = mapped_column(Text)
    raw_sha256: Mapped[str | None] = mapped_column(String(64))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class ProcessingRunRow(TimestampMixin, Base):
    __tablename__ = "processing_run"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32))
    site_id: Mapped[str] = mapped_column(ForeignKey("site.id"))
    input_source_ids: Mapped[list[Any]] = mapped_column(default=list)
    steps: Mapped[list[Any]] = mapped_column(default=list)
    summary: Mapped[dict[str, Any]] = mapped_column(default=dict)


class ObservationRow(Base):
    """One row per site/source/variable/timestamp. ``raw_value`` is never updated after insert."""

    __tablename__ = "observation"
    __table_args__ = (
        UniqueConstraint("site_id", "source_id", "variable", "observed_at", "processing_run_id"),
        Index("ix_observation_lookup", "site_id", "variable", "observed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    variable: Mapped[str] = mapped_column(String(64))
    unit: Mapped[str] = mapped_column(String(32))
    raw_value: Mapped[float | None] = mapped_column(Float)
    processed_value: Mapped[float | None] = mapped_column(Float)
    quality_flag: Mapped[str] = mapped_column(String(16), default="ok")
    value_kind: Mapped[str] = mapped_column(String(32))
    imputation_method: Mapped[str | None] = mapped_column(String(64))
    processing_run_id: Mapped[str | None] = mapped_column(ForeignKey("processing_run.id"))


class CropProfileRow(TimestampMixin, Base):
    __tablename__ = "crop_profile"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    params: Mapped[dict[str, Any]] = mapped_column(default=dict, comment="CropProfile contract as JSON")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class SoilProfileRow(TimestampMixin, Base):
    __tablename__ = "soil_profile"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.id"))
    params: Mapped[dict[str, Any]] = mapped_column(default=dict, comment="SoilProfile contract as JSON")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class StrategyRow(TimestampMixin, Base):
    __tablename__ = "strategy"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.id"))
    name: Mapped[str] = mapped_column(String(200))
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    seasons: Mapped[list[Any]] = mapped_column(default=list)
    feasibility: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    # A user-built rotation replaced by a newer save (D15). Kept, not deleted: earlier results reference it.
    superseded: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class SimulationRunRow(TimestampMixin, Base):
    __tablename__ = "simulation_run"

    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("app_user.id"), index=True)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.id"))
    strategy_ids: Mapped[list[Any]] = mapped_column(default=list)
    mode: Mapped[str] = mapped_column(String(32))
    allocation_mm: Mapped[float | None] = mapped_column(Float)
    weather_source_id: Mapped[str] = mapped_column(ForeignKey("source.id"))
    resampling_method: Mapped[str] = mapped_column(String(64))
    sample_start: Mapped[date] = mapped_column(Date)
    sample_end: Mapped[date] = mapped_column(Date)
    n_paths: Mapped[int] = mapped_column(Integer)
    horizon_years: Mapped[int] = mapped_column(Integer)
    seed: Mapped[int] = mapped_column(BigInteger)
    model_version: Mapped[str] = mapped_column(String(32))
    input_versions: Mapped[dict[str, Any]] = mapped_column(default=dict)
    inputs_hash: Mapped[str] = mapped_column(String(64), index=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="RunDetail contract (minus run) + Simulate journey stage"
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class ResultRow(TimestampMixin, Base):
    __tablename__ = "result"
    __table_args__ = (Index("ix_result_run_strategy", "run_id", "strategy_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_run.id"))
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategy.id"))
    metric: Mapped[str] = mapped_column(String(64))
    unit: Mapped[str] = mapped_column(String(32))
    p10: Mapped[float | None] = mapped_column(Float)
    p50: Mapped[float | None] = mapped_column(Float)
    p90: Mapped[float | None] = mapped_column(Float)
    sample_count: Mapped[int] = mapped_column(Integer)
    season_index: Mapped[int | None] = mapped_column(Integer)
    crop_id: Mapped[str | None] = mapped_column(String(64))
    trace_path: Mapped[str | None] = mapped_column(Text)
    source_ids: Mapped[list[Any]] = mapped_column(default=list)
    limitations: Mapped[list[Any]] = mapped_column(default=list)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class PairedDeltaRow(TimestampMixin, Base):
    """Strategy minus baseline per weather path, summarised (PairedDelta contract)."""

    __tablename__ = "paired_delta"
    __table_args__ = (Index("ix_paired_delta_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_run.id"))
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategy.id"))
    baseline_strategy_id: Mapped[str] = mapped_column(ForeignKey("strategy.id"))
    metric: Mapped[str] = mapped_column(String(64))
    unit: Mapped[str] = mapped_column(String(32))
    p10: Mapped[float | None] = mapped_column(Float)
    p50: Mapped[float | None] = mapped_column(Float)
    p90: Mapped[float | None] = mapped_column(Float)
    better_direction: Mapped[str | None] = mapped_column(String(8))
    share_better: Mapped[float | None] = mapped_column(Float)
    share_worse: Mapped[float | None] = mapped_column(Float)
    sample_count: Mapped[int] = mapped_column(Integer)
    source_ids: Mapped[list[Any]] = mapped_column(default=list)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class ValidationRow(TimestampMixin, Base):
    __tablename__ = "validation"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target: Mapped[str] = mapped_column(String(200))
    reference: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict, comment="Validation contract as JSON")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class DecisionRecordRow(TimestampMixin, Base):
    __tablename__ = "decision_record"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.id"))
    chosen_strategy_id: Mapped[str] = mapped_column(ForeignKey("strategy.id"))
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_run.id"))
    reason: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, comment="DecisionCard contract")
    json_path: Mapped[str | None] = mapped_column(Text)
    pdf_path: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64))


class ForecastSnapshotRow(TimestampMixin, Base):
    """One seasonal-forecast download for a farm (D16). Raw daily members are the source's raw snapshot; the
    monthly anomaly file is referenced here. Odds and weights are recomputed from these files on demand."""

    __tablename__ = "forecast_snapshot"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id"))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    forecast_start: Mapped[date] = mapped_column(Date)
    forecast_end: Mapped[date] = mapped_column(Date)
    n_members: Mapped[int] = mapped_column(Integer)
    monthly_raw_path: Mapped[str] = mapped_column(Text)
    monthly_raw_sha256: Mapped[str] = mapped_column(String(64))
