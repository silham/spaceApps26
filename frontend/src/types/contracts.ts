/* Generated from contracts/schemas/bundle.json by json-schema-to-typescript. Do not edit; run make contracts. */

export type Id = string;
export type Name = string;
export type Latitude = number;
export type Longitude = number;
export type BoundaryGeojson = {
  [k: string]: unknown;
} | null;
/**
 * IANA timezone used for analysis, e.g. 'America/Chicago'
 */
export type Timezone = string;
export type AreaHa = number | null;
export type IsDemo = boolean;
export type Id1 = string;
export type Provider = string;
export type Product = string;
export type Version = string | null;
export type Variables = string[];
/**
 * Keeps observed, estimated, farmer, reanalysis, literature and simulated values distinguishable.
 */
export type ValueKind = "observed" | "reanalysis" | "estimated" | "farmer_input" | "literature" | "simulated" | "demo";
export type SpatialResolution = string | null;
export type TemporalResolution = string | null;
export type CoverageStart = string | null;
export type CoverageEnd = string | null;
export type RetrievedAt = string | null;
export type Url = string | null;
export type Doi = string | null;
export type License = string | null;
export type Attribution = string | null;
export type QaNotes = string | null;
export type Limitations = string | null;
/**
 * Native pixel/grid footprint
 */
export type FootprintGeojson = {
  [k: string]: unknown;
} | null;
/**
 * Path of the immutable raw snapshot, relative to data/
 */
export type RawPath = string | null;
export type RawSha256 = string | null;
export type IsDemo1 = boolean;
export type SiteId = string;
export type SourceId = string;
/**
 * Original timestamp, timezone-aware
 */
export type ObservedAt = string;
export type Variable = string;
export type Unit = string;
/**
 * As delivered by the source; never modified
 */
export type RawValue = number | null;
export type ProcessedValue = number | null;
export type QualityFlag = "ok" | "flagged" | "rejected" | "missing" | "duplicate" | "estimated";
export type ImputationMethod = string | null;
export type ProcessingRunId = string | null;
export type Id2 = string;
export type Version1 = string;
export type SiteId1 = string;
export type InputSourceIds = string[];
export type Name1 = string;
export type AffectedCount = number;
export type Reason = string;
export type Steps = ProcessingStep[];
export type CreatedAt = string;
export type Id3 = string;
export type Name2 = string;
export type Value = number | null;
export type Unit1 = string;
/**
 * Citation (DOI/URL/table). Required when value is set.
 */
export type Reference = string | null;
export type RegionRelevance = string | null;
export type Uncertainty = string | null;
/**
 * MM-DD start/end
 */
export type PlantingWindow = [unknown, unknown] | null;
export type IsCoverCrop = boolean;
export type Notes = string | null;
export type IsDemo2 = boolean;
export type Id4 = string;
export type SiteId2 = string;
export type Texture = string | null;
export type SourceIds = string[];
export type IsDemo3 = boolean;
export type Id5 = string;
export type SiteId3 = string;
export type Name3 = string;
export type IsBaseline = boolean;
/**
 * None = fallow
 */
export type CropId = string | null;
export type PlantDate = string;
/**
 * Harvest or termination date
 */
export type EndDate = string;
export type IrrigationRule = string | null;
export type ResidueManagement = string | null;
export type Seasons = SeasonPlan[];
export type Feasible = boolean;
/**
 * Human-readable; required when infeasible
 */
export type Reasons = string[];
export type IsDemo4 = boolean;
export type Id6 = string;
export type SiteId4 = string;
export type StrategyIds = string[];
export type SimulationMode = "irrigation_needed" | "fixed_allocation";
/**
 * Required for fixed_allocation mode
 */
export type AllocationMm = number | null;
/**
 * Exactly one rainfall/weather source per run
 */
export type WeatherSourceId = string;
export type ResamplingMethod = string;
/**
 * @minItems 2
 * @maxItems 2
 */
export type SamplePeriod = [unknown, unknown];
export type NPaths = number;
export type HorizonYears = number;
export type Seed = number;
export type ModelVersion = string;
export type CreatedAt1 = string;
export type IsDemo5 = boolean;
export type Id7 = string;
export type RunId = string;
export type StrategyId = string;
export type Metric = string;
export type Unit2 = string;
export type P10 = number | null;
export type P50 = number | null;
export type P90 = number | null;
export type RangeLabel = string;
export type SampleCount = number;
/**
 * Parquet traces under results/
 */
export type TracePath = string | null;
export type SourceIds1 = string[];
export type Limitations1 = string[];
export type IsDemo6 = boolean;
export type Id8 = string;
export type Target = string;
export type Reference1 = string;
export type CalibrationPeriod = [unknown, unknown] | null;
export type TestPeriod = [unknown, unknown] | null;
export type SampleCount1 = number;
export type Failures = string[];
export type IndependenceNotes = string;
export type IsDemo7 = boolean;
export type Id9 = string;
export type SiteId5 = string;
export type ChosenStrategyId = string;
export type RunId1 = string;
export type Reason1 = string;
export type CreatedAt2 = string;
export type JourneyStageName =
  "collect" | "check" | "clean" | "handle_gaps" | "align" | "extract" | "simulate" | "validate" | "compare";
export type StageStatus = "not_started" | "ok" | "warning" | "failed" | "unavailable";
/**
 * One plain-language sentence
 */
export type Summary1 = string;
export type SourceIds2 = string[];
export type ProcessingRunId1 = string | null;
/**
 * Data for the stage's single chart
 */
export type Chart = {
  [k: string]: unknown;
} | null;
export type IsDemo8 = boolean;

/**
 * Schema version 1.0.0. Generated - do not edit.
 */
export interface FarmTimeMachineContracts {
  Site?: Site;
  Source?: Source;
  Observation?: Observation;
  ProcessingRun?: ProcessingRun;
  CropProfile?: CropProfile;
  SoilProfile?: SoilProfile;
  Strategy?: Strategy;
  SimulationRun?: SimulationRun;
  Result?: Result;
  Validation?: Validation;
  DecisionRecord?: DecisionRecord;
  JourneyStage?: JourneyStage;
}
export interface Site {
  id: Id;
  name: Name;
  latitude: Latitude;
  longitude: Longitude;
  boundary_geojson?: BoundaryGeojson;
  timezone: Timezone;
  area_ha?: AreaHa;
  farmer_context?: FarmerContext;
  is_demo?: IsDemo;
}
/**
 * Farmer-confirmed context (irrigation allocation, equipment, ...)
 */
export interface FarmerContext {
  [k: string]: unknown;
}
/**
 * Source register entry. Only list sources actually used (AGENTS.md rule 2).
 */
export interface Source {
  id: Id1;
  provider: Provider;
  product: Product;
  version?: Version;
  variables: Variables;
  units: Units;
  kind: ValueKind;
  spatial_resolution?: SpatialResolution;
  temporal_resolution?: TemporalResolution;
  coverage_start?: CoverageStart;
  coverage_end?: CoverageEnd;
  retrieved_at?: RetrievedAt;
  url?: Url;
  doi?: Doi;
  license?: License;
  attribution?: Attribution;
  qa_notes?: QaNotes;
  limitations?: Limitations;
  footprint_geojson?: FootprintGeojson;
  raw_path?: RawPath;
  raw_sha256?: RawSha256;
  is_demo?: IsDemo1;
}
/**
 * variable -> unit
 */
export interface Units {
  [k: string]: string;
}
export interface Observation {
  site_id: SiteId;
  source_id: SourceId;
  observed_at: ObservedAt;
  variable: Variable;
  unit: Unit;
  raw_value: RawValue;
  processed_value?: ProcessedValue;
  quality_flag?: QualityFlag;
  value_kind: ValueKind;
  imputation_method?: ImputationMethod;
  processing_run_id?: ProcessingRunId;
}
export interface ProcessingRun {
  id: Id2;
  version: Version1;
  site_id: SiteId1;
  input_source_ids: InputSourceIds;
  steps: Steps;
  created_at: CreatedAt;
  summary?: Summary;
}
export interface ProcessingStep {
  name: Name1;
  params?: Params;
  affected_count?: AffectedCount;
  reason: Reason;
}
export interface Params {
  [k: string]: unknown;
}
export interface Summary {
  [k: string]: unknown;
}
export interface CropProfile {
  id: Id3;
  name: Name2;
  kc_ini: ParamValue;
  kc_mid: ParamValue;
  kc_end: ParamValue;
  stage_lengths_days: StageLengthsDays;
  max_root_depth_m: ParamValue;
  depletion_fraction_p: ParamValue;
  planting_window?: PlantingWindow;
  is_cover_crop?: IsCoverCrop;
  notes?: Notes;
  is_demo?: IsDemo2;
}
/**
 * A literature/local parameter. ``value=None`` means missing: the claim it supports is blocked.
 */
export interface ParamValue {
  value: Value;
  unit: Unit1;
  reference: Reference;
  region_relevance?: RegionRelevance;
  uncertainty?: Uncertainty;
}
export interface StageLengthsDays {
  [k: string]: ParamValue;
}
export interface SoilProfile {
  id: Id4;
  site_id: SiteId2;
  available_water_capacity_mm_per_m: ParamValue;
  root_zone_depth_m: ParamValue;
  texture?: Texture;
  source_ids: SourceIds;
  is_demo?: IsDemo3;
}
export interface Strategy {
  id: Id5;
  site_id: SiteId3;
  name: Name3;
  is_baseline?: IsBaseline;
  seasons: Seasons;
  feasibility?: Feasibility | null;
  is_demo?: IsDemo4;
}
export interface SeasonPlan {
  crop_id: CropId;
  plant_date: PlantDate;
  end_date: EndDate;
  irrigation_rule?: IrrigationRule;
  residue_management?: ResidueManagement;
}
export interface Feasibility {
  feasible: Feasible;
  reasons?: Reasons;
}
export interface SimulationRun {
  id: Id6;
  site_id: SiteId4;
  strategy_ids: StrategyIds;
  mode: SimulationMode;
  allocation_mm?: AllocationMm;
  weather_source_id: WeatherSourceId;
  resampling_method: ResamplingMethod;
  sample_period: SamplePeriod;
  n_paths: NPaths;
  horizon_years: HorizonYears;
  seed: Seed;
  model_version: ModelVersion;
  input_versions?: InputVersions;
  created_at: CreatedAt1;
  is_demo?: IsDemo5;
}
export interface InputVersions {
  [k: string]: string;
}
export interface Result {
  id: Id7;
  run_id: RunId;
  strategy_id: StrategyId;
  metric: Metric;
  unit: Unit2;
  p10: P10;
  p50: P50;
  p90: P90;
  range_label?: RangeLabel;
  sample_count: SampleCount;
  trace_path?: TracePath;
  source_ids: SourceIds1;
  limitations?: Limitations1;
  is_demo?: IsDemo6;
}
export interface Validation {
  id: Id8;
  target: Target;
  reference: Reference1;
  calibration_period?: CalibrationPeriod;
  test_period?: TestPeriod;
  sample_count: SampleCount1;
  metrics?: Metrics;
  failures?: Failures;
  independence_notes: IndependenceNotes;
  is_demo?: IsDemo7;
}
export interface Metrics {
  [k: string]: number;
}
export interface DecisionRecord {
  id: Id9;
  site_id: SiteId5;
  chosen_strategy_id: ChosenStrategyId;
  run_id: RunId1;
  reason: Reason1;
  created_at: CreatedAt2;
}
/**
 * Payload for one Data Journey card (AGENTS.md rule 4).
 */
export interface JourneyStage {
  stage: JourneyStageName;
  status: StageStatus;
  summary: Summary1;
  source_ids?: SourceIds2;
  processing_run_id?: ProcessingRunId1;
  chart?: Chart;
  details?: Details;
  is_demo?: IsDemo8;
}
export interface Details {
  [k: string]: unknown;
}
