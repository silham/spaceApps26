"""Shared data contracts: the single source of truth for API and data shapes.

Owner: M1. Change only with M1 approval, then run ``make contracts`` to regenerate
``contracts/schemas/*.json`` and ``frontend/src/types/contracts.ts``.

Entities follow DEVELOPMENT_GUIDE.md section 9.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.3.0"
# 1.1.0: additive (MODELED kind, ParamValue bounds, Validation periods/sources)
# 1.2.0: additive (RunRequest, RunDetail, PairedDelta, ReplayTrace, FarmerContext, EnvironmentalTimeline,
#        DecisionCardRequest, DecisionCard; D6 supported edits)
# 1.3.0: additive (NewSiteRequest, SiteLoadStep, SiteLoadStatus; user-selected locations, observe only, D13)

# Wording agreed in DEVELOPMENT_GUIDE.md section 7: p10-p90 is NOT a calibrated prediction interval.
RANGE_LABEL = "central 80% simulation range (p10–p90)"

# D6 (docs/decisions.md): the only supported edits are the mode, the irrigation allocation (fixed-allocation
# mode) and a planting-date shift within +/- this many days per strategy. Anything else is refused (422).
MAX_PLANTING_SHIFT_DAYS = 14
MIN_RUN_PATHS = 20  # below this the engine reports no p10/p90 (ftm.engine.ensemble.MIN_PATHS_FOR_RANGE)
MAX_RUN_PATHS = 500
DEFAULT_RUN_PATHS = 200
DEFAULT_RUN_SEED = 20261114


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


# --------------------------------------------------------------------------- enums


class ValueKind(StrEnum):
    """Keeps observed, estimated, farmer, reanalysis, literature and simulated values distinguishable."""

    OBSERVED = "observed"
    REANALYSIS = "reanalysis"  # e.g. NASA POWER, GWETROOT, SMAP L4 (model-assisted)
    MODELED = "modeled"  # statistical/ML prediction maps, e.g. SoilGrids (not observations, not reanalysis)
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
        default_factory=dict,
        title="Site Farmer Context",  # distinct name in generated TS; the typed shape is the FarmerContext contract
        description="Farmer-confirmed context as stored (FarmerContext contract, served by /sites/{id}/farmer-context)",
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
    low: float | None = Field(default=None, description="Lower bound in ``unit`` if the source documents one")
    high: float | None = Field(default=None, description="Upper bound in ``unit`` if the source documents one")
    bounds_kind: str | None = Field(
        default=None,
        description="What low/high are, e.g. 'documented range (SSURGO awc_l/awc_h)' or 'declared assumption ±20%'. "
        "Never a statistical interval unless one was actually computed.",
    )

    @model_validator(mode="after")
    def _bounds_consistent(self) -> "ParamValue":
        if (self.low is None) != (self.high is None):
            raise ValueError("set both low and high, or neither")
        if self.low is not None and self.high is not None:
            if self.low > self.high:
                raise ValueError("low must be <= high")
            if self.bounds_kind is None:
                raise ValueError("bounds_kind is required when low/high are set")
        return self


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
    source_ids: list[str] = Field(
        default_factory=list, description="Sources actually used: the evaluated data and the reference (rule 2)"
    )
    train_period: tuple[date, date] | None = Field(
        default=None, description="Training/tuning period (DEVELOPMENT_GUIDE.md section 8.3)"
    )
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


# --------------------------------------------------------------------------- runs, comparison, decision (1.2.0)


class RunRequest(Contract):
    """A comparison run with the D6 supported edits only. Unsupported edits are rejected, never approximated."""

    site_id: str
    mode: SimulationMode = SimulationMode.IRRIGATION_NEEDED
    allocation_mm: float | None = Field(
        default=None, ge=0, description="Net irrigation allocation per irrigated season (mm); fixed_allocation only"
    )
    planting_shift_days: dict[str, int] = Field(
        default_factory=dict,
        description=f"strategy_id -> days to move every crop season (|days| <= {MAX_PLANTING_SHIFT_DAYS}, D6)",
    )
    n_paths: int = Field(default=DEFAULT_RUN_PATHS, ge=MIN_RUN_PATHS, le=MAX_RUN_PATHS)
    seed: int = DEFAULT_RUN_SEED

    @model_validator(mode="after")
    def _supported_edits(self) -> "RunRequest":
        if self.mode is SimulationMode.FIXED_ALLOCATION and self.allocation_mm is None:
            raise ValueError("fixed_allocation mode needs an irrigation allocation (mm per irrigated season)")
        if self.mode is SimulationMode.IRRIGATION_NEEDED and self.allocation_mm is not None:
            raise ValueError("an allocation applies only in fixed_allocation mode; remove it or change the mode")
        for sid, days in self.planting_shift_days.items():
            if abs(days) > MAX_PLANTING_SHIFT_DAYS:
                raise ValueError(
                    f"planting shift {days:+d} days for {sid!r} is not supported: "
                    f"only shifts within ±{MAX_PLANTING_SHIFT_DAYS} days are computed (D6)"
                )
        return self


class ReplayWindow(Contract):
    years: list[int]
    enabled: bool
    reason: str | None = Field(default=None, description="Why the window cannot be replayed")
    in_sample_pool: bool = Field(description="False: held out or outside the pool; replay only, never a range")
    rain_mm: float | None = Field(default=None, description="Total usable rainfall over the window's years")


class RunDetail(Contract):
    """A stored run with everything the comparison screens need besides results and deltas."""

    run: SimulationRun
    request: RunRequest
    strategies: list[Strategy] = Field(description="As simulated (edits applied), each with its feasibility")
    replay_windows: list[ReplayWindow]
    excluded_blocks: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source_ids: list[str]
    scenario_notes: list[str] = Field(default_factory=list, description="How planting dates were derived")
    unsupported_claims: list[str] = Field(default_factory=list, description="Shown as unavailable, never estimated")
    cached: bool = Field(default=False, description="True: an identical earlier run was returned")


class PairedDelta(Contract):
    """Strategy minus baseline on the same weather path, summarised across paths (paired comparison)."""

    id: str
    run_id: str
    strategy_id: str
    baseline_strategy_id: str
    metric: str
    unit: str
    p10: float | None
    p50: float | None
    p90: float | None
    range_label: str = RANGE_LABEL
    better_direction: Literal["lower", "higher"] | None = Field(
        description="Which direction is preferable for this metric; None = no preferred direction"
    )
    share_better: float | None = Field(description="Fraction of paths where the strategy beats the baseline")
    share_worse: float | None
    sample_count: int
    source_ids: list[str] = Field(default_factory=list)
    is_demo: bool = False


class ReplaySeries(Contract):
    strategy_id: str
    crop_id: list[str | None]
    in_crop: list[bool]
    storage_mm: list[float | None] = Field(description="Root-zone soil water at the end of the day")
    ks: list[float | None] = Field(description="FAO-56 water-stress coefficient (1 = no stress)")
    irrigation_mm: list[float | None]
    aet_mm: list[float | None]
    metrics: dict[str, float] = Field(description="This single path's metrics (no range: one path)")


class ReplayTrace(Contract):
    """One historical weather window replayed day by day for every strategy (identical weather)."""

    run_id: str
    years: list[int]
    in_sample_pool: bool
    dates: list[date] = Field(description="Strategy-calendar dates (the comparison horizon)")
    source_dates: list[date] = Field(description="The historical dates whose weather is replayed")
    rain_mm: list[float | None]
    et0_mm: list[float | None]
    series: list[ReplaySeries]
    turning_point: date | None
    turning_point_reason: str | None
    source_ids: list[str]
    limitations: list[str] = Field(default_factory=list)
    is_demo: bool = False


class FarmerContext(Contract):
    """Farmer-confirmed inputs (value kind farmer_input). Unconfirmed fields stay null, never guessed."""

    value_kind: Literal[ValueKind.FARMER_INPUT] = ValueKind.FARMER_INPUT
    confirmed: bool = False
    planting_history: str | None = None
    harvest_history: str | None = None
    soil_confirmed: bool | None = Field(default=None, description="Farmer agrees with the stored soil profile")
    soil_notes: str | None = None
    irrigation_allocation_mm: float | None = Field(default=None, ge=0, description="mm per irrigated season")
    equipment: list[str] = Field(default_factory=list)
    available_crop_ids: list[str] | None = Field(
        default=None, description="Crops the farmer can grow; None = not stated (all catalog crops allowed)"
    )
    market_use: str | None = None
    updated_at: datetime | None = None


class EnvironmentalTimeline(Contract):
    """Daily weather and satellite vegetation for the Observe timeline. Missing values stay null."""

    site_id: str
    start: date
    end: date
    weather_source_id: str | None
    processing_run_id: str | None
    dates: list[date]
    rain_mm: list[float | None]
    rain_flag: list[str | None]
    tmax_c: list[float | None]
    tmin_c: list[float | None]
    vegetation_source_id: str | None = None
    vegetation_dates: list[date] = Field(default_factory=list)
    ndvi: list[float | None] = Field(default_factory=list)
    vegetation_note: str | None = None
    source_ids: list[str]
    is_demo: bool = False


class Priorities(Contract):
    """Farmer priorities rank feasible options; they never override hard constraints."""

    conserve_water: int = Field(default=50, ge=0, le=100)
    protect_soil: int = Field(default=50, ge=0, le=100)


class DecisionCardRequest(Contract):
    site_id: str
    run_id: str
    chosen_strategy_id: str
    reason: str = Field(min_length=1, max_length=4000)
    priorities: Priorities | None = None


class DecisionCard(Contract):
    """Everything needed to review a decision later: choice, reason, evidence, assumptions, open questions."""

    id: str
    site_id: str
    site_name: str
    created_at: datetime
    chosen_strategy_id: str
    reason: str
    priorities: Priorities | None
    farmer_context: FarmerContext | None
    run: SimulationRun
    request: RunRequest
    strategies: list[Strategy]
    results: list[Result]
    deltas: list[PairedDelta]
    sources: list[Source]
    crops: list[CropProfile]
    assumptions: list[str]
    limitations: list[str]
    local_review_questions: list[str]
    unsupported_claims: list[str]
    json_url: str
    pdf_url: str | None
    sha256: str | None = Field(default=None, description="SHA-256 of the exported JSON")
    is_demo: bool = False


# --------------------------------------------------------------------------- user-selected locations (1.3.0)

MAX_NEW_SITE_AREA_HA = 5000.0  # a field, not a region: larger outlines are refused


class NewSiteRequest(Contract):
    """A farm picked on the map anywhere in the world (D13: observe only unless strategies are reviewed)."""

    name: str = Field(min_length=1, max_length=120)
    latitude: float = Field(ge=-60, le=75, description="Cropland latitudes; polar regions are refused")
    longitude: float = Field(ge=-180, le=180)
    boundary_geojson: dict[str, Any] | None = Field(
        default=None, description="Polygon or MultiPolygon drawn by the user (WGS84); optional"
    )


class SiteLoadStep(Contract):
    name: Literal["weather", "soil", "vegetation"]
    source: str = Field(description="Product being loaded, e.g. 'NASA POWER daily'")
    status: Literal["pending", "running", "done", "failed", "skipped"]
    message: str | None = None


class SiteLoadStatus(Contract):
    site_id: str
    status: Literal["queued", "running", "done", "failed"]
    steps: list[SiteLoadStep]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    has_strategies: bool = Field(description="False: observe only, no locally reviewed strategies (D13)")


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
    RunRequest,
    ReplayWindow,
    RunDetail,
    PairedDelta,
    ReplaySeries,
    ReplayTrace,
    FarmerContext,
    EnvironmentalTimeline,
    Priorities,
    DecisionCardRequest,
    DecisionCard,
    NewSiteRequest,
    SiteLoadStep,
    SiteLoadStatus,
]
