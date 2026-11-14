"""Shared data contracts: the single source of truth for API and data shapes.

Owner: M1. Change only with M1 approval, then run ``make contracts`` to regenerate
``contracts/schemas/*.json`` and ``frontend/src/types/contracts.ts``.

Entities follow DEVELOPMENT_GUIDE.md section 9.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0.0"

# Wording agreed in DEVELOPMENT_GUIDE.md section 7: p10-p90 is NOT a calibrated prediction interval.
RANGE_LABEL = "central 80% simulation range (p10–p90)"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


# --------------------------------------------------------------------------- enums


class ValueKind(StrEnum):
    """Keeps observed, estimated, farmer, reanalysis, literature and simulated values distinguishable."""

    OBSERVED = "observed"
    REANALYSIS = "reanalysis"  # e.g. NASA POWER, GWETROOT, SMAP L4 (model-assisted)
    ESTIMATED = "estimated"  # gap-filled by a declared method
    FARMER_INPUT = "farmer_input"
    LITERATURE = "literature"
    SIMULATED = "simulated"
    DEMO = "demo"


class QualityFlag(StrEnum):
    OK = "ok"
    FLAGGED = "flagged"
    REJECTED = "rejected"
    MISSING = "missing"
    DUPLICATE = "duplicate"
    ESTIMATED = "estimated"


class SimulationMode(StrEnum):
    IRRIGATION_NEEDED = "irrigation_needed"  # irrigation required under a stated management rule
    FIXED_ALLOCATION = "fixed_allocation"  # water stress under a fixed allocation, never extra water


class JourneyStageName(StrEnum):
    COLLECT = "collect"
    CHECK = "check"
    CLEAN = "clean"
    HANDLE_GAPS = "handle_gaps"
    ALIGN = "align"
    EXTRACT = "extract"
    SIMULATE = "simulate"
    VALIDATE = "validate"
    COMPARE = "compare"


class StageStatus(StrEnum):
    NOT_STARTED = "not_started"
    OK = "ok"
    WARNING = "warning"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


# --------------------------------------------------------------------------- entities


class Site(Contract):
    id: str
    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    boundary_geojson: dict[str, Any] | None = None
    timezone: str = Field(description="IANA timezone used for analysis, e.g. 'America/Chicago'")
    area_ha: float | None = None
    farmer_context: dict[str, Any] = Field(
        default_factory=dict, description="Farmer-confirmed context (irrigation allocation, equipment, ...)"
    )
    is_demo: bool = False


class Source(Contract):
    """Source register entry. Only list sources actually used (AGENTS.md rule 2)."""

    id: str
    provider: str
    product: str
    version: str | None = None
    variables: list[str]
    units: dict[str, str] = Field(description="variable -> unit")
    kind: ValueKind
    spatial_resolution: str | None = None
    temporal_resolution: str | None = None
    coverage_start: date | None = None
    coverage_end: date | None = None
    retrieved_at: datetime | None = None
    url: str | None = None
    doi: str | None = None
    license: str | None = None
    attribution: str | None = None
    qa_notes: str | None = None
    limitations: str | None = None
    footprint_geojson: dict[str, Any] | None = Field(default=None, description="Native pixel/grid footprint")
    raw_path: str | None = Field(default=None, description="Path of the immutable raw snapshot, relative to data/")
    raw_sha256: str | None = None
    is_demo: bool = False


class Observation(Contract):
    site_id: str
    source_id: str
    observed_at: datetime = Field(description="Original timestamp, timezone-aware")
    variable: str
    unit: str
    raw_value: float | None = Field(description="As delivered by the source; never modified")
    processed_value: float | None = None
    quality_flag: QualityFlag = QualityFlag.OK
    value_kind: ValueKind
    imputation_method: str | None = None
    processing_run_id: str | None = None


class ProcessingStep(Contract):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)
    affected_count: int = 0
    reason: str


class ProcessingRun(Contract):
    id: str
    version: str
    site_id: str
    input_source_ids: list[str]
    steps: list[ProcessingStep]
    created_at: datetime
    summary: dict[str, Any] = Field(default_factory=dict)


class ParamValue(Contract):
    """A literature/local parameter. ``value=None`` means missing: the claim it supports is blocked."""

    value: float | None
    unit: str
    reference: str | None = Field(description="Citation (DOI/URL/table). Required when value is set.")
    region_relevance: str | None = None
    uncertainty: str | None = None


class CropProfile(Contract):
    id: str
    name: str
    kc_ini: ParamValue
    kc_mid: ParamValue
    kc_end: ParamValue
    stage_lengths_days: dict[Literal["ini", "dev", "mid", "late"], ParamValue]
    max_root_depth_m: ParamValue
    depletion_fraction_p: ParamValue
    planting_window: tuple[str, str] | None = Field(default=None, description="MM-DD start/end")
    is_cover_crop: bool = False
    notes: str | None = None
    is_demo: bool = False


class SoilProfile(Contract):
    id: str
    site_id: str
    available_water_capacity_mm_per_m: ParamValue
    root_zone_depth_m: ParamValue
    texture: str | None = None
    source_ids: list[str]
    is_demo: bool = False


class SeasonPlan(Contract):
    crop_id: str | None = Field(description="None = fallow")
    plant_date: date
    end_date: date = Field(description="Harvest or termination date")
    irrigation_rule: str | None = None
    residue_management: str | None = None


class Feasibility(Contract):
    feasible: bool
    reasons: list[str] = Field(default_factory=list, description="Human-readable; required when infeasible")


class Strategy(Contract):
    id: str
    site_id: str
    name: str
    is_baseline: bool = False
    seasons: list[SeasonPlan]
    feasibility: Feasibility | None = None
    is_demo: bool = False


class SimulationRun(Contract):
    id: str
    site_id: str
    strategy_ids: list[str]
    mode: SimulationMode
    allocation_mm: float | None = Field(default=None, description="Required for fixed_allocation mode")
    weather_source_id: str = Field(description="Exactly one rainfall/weather source per run")
    resampling_method: str
    sample_period: tuple[date, date]
    n_paths: int
    horizon_years: int
    seed: int
    model_version: str
    input_versions: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    is_demo: bool = False


class Result(Contract):
    id: str
    run_id: str
    strategy_id: str
    metric: str
    unit: str
    p10: float | None
    p50: float | None
    p90: float | None
    range_label: str = RANGE_LABEL
    sample_count: int
    trace_path: str | None = Field(default=None, description="Parquet traces under results/")
    source_ids: list[str]
    limitations: list[str] = Field(default_factory=list)
    is_demo: bool = False


class Validation(Contract):
    id: str
    target: str
    reference: str
    calibration_period: tuple[date, date] | None = None
    test_period: tuple[date, date] | None = None
    sample_count: int
    metrics: dict[str, float] = Field(default_factory=dict)
    failures: list[str] = Field(default_factory=list)
    independence_notes: str
    is_demo: bool = False


class DecisionRecord(Contract):
    id: str
    site_id: str
    chosen_strategy_id: str
    run_id: str
    reason: str
    created_at: datetime


class JourneyStage(Contract):
    """Payload for one Data Journey card (AGENTS.md rule 4)."""

    stage: JourneyStageName
    status: StageStatus
    summary: str = Field(description="One plain-language sentence")
    source_ids: list[str] = Field(default_factory=list)
    processing_run_id: str | None = None
    chart: dict[str, Any] | None = Field(default=None, description="Data for the stage's single chart")
    details: dict[str, Any] = Field(default_factory=dict)
    is_demo: bool = False


ALL_CONTRACTS: list[type[Contract]] = [
    Site,
    Source,
    Observation,
    ProcessingRun,
    CropProfile,
    SoilProfile,
    Strategy,
    SimulationRun,
    Result,
    Validation,
    DecisionRecord,
    JourneyStage,
]
