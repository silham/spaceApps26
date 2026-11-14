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
export type ValueKind =
  "observed" | "reanalysis" | "modeled" | "estimated" | "farmer_input" | "literature" | "simulated" | "demo";
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
 * Lower bound in ``unit`` if the source documents one
 */
export type Low = number | null;
/**
 * Upper bound in ``unit`` if the source documents one
 */
export type High = number | null;
/**
 * What low/high are, e.g. 'documented range (SSURGO awc_l/awc_h)' or 'declared assumption ±20%'. Never a statistical interval unless one was actually computed.
 */
export type BoundsKind = string | null;
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
/**
 * Sources actually used: the evaluated data and the reference (rule 2)
 */
export type SourceIds2 = string[];
/**
 * Training/tuning period (DEVELOPMENT_GUIDE.md section 8.3)
 */
export type TrainPeriod = [unknown, unknown] | null;
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
export type SourceIds3 = string[];
export type ProcessingRunId1 = string | null;
/**
 * Data for the stage's single chart
 */
export type Chart = {
  [k: string]: unknown;
} | null;
export type IsDemo8 = boolean;
export type SiteId6 = string;
export type SimulationMode1 = "irrigation_needed" | "fixed_allocation";
/**
 * Net irrigation allocation per irrigated season (mm); fixed_allocation only
 */
export type AllocationMm1 = number | null;
export type NPaths1 = number;
export type Seed1 = number;
export type Years = number[];
export type Enabled = boolean;
/**
 * Why the window cannot be replayed
 */
export type Reason2 = string | null;
/**
 * False: held out or outside the pool; replay only, never a range
 */
export type InSamplePool = boolean;
/**
 * Total usable rainfall over the window's years
 */
export type RainMm = number | null;
/**
 * As simulated (edits applied), each with its feasibility
 */
export type Strategies = Strategy[];
export type ReplayWindows = ReplayWindow[];
export type ExcludedBlocks = {
  [k: string]: unknown;
}[];
export type Limitations2 = string[];
export type SourceIds4 = string[];
/**
 * How planting dates were derived
 */
export type ScenarioNotes = string[];
/**
 * Shown as unavailable, never estimated
 */
export type UnsupportedClaims = string[];
/**
 * True: an identical earlier run was returned
 */
export type Cached = boolean;
export type Id10 = string;
export type RunId2 = string;
export type StrategyId1 = string;
export type BaselineStrategyId = string;
export type Metric1 = string;
export type Unit3 = string;
export type P101 = number | null;
export type P501 = number | null;
export type P901 = number | null;
export type RangeLabel1 = string;
/**
 * Which direction is preferable for this metric; None = no preferred direction
 */
export type BetterDirection = ("lower" | "higher") | null;
/**
 * Fraction of paths where the strategy beats the baseline
 */
export type ShareBetter = number | null;
export type ShareWorse = number | null;
export type SampleCount2 = number;
export type SourceIds5 = string[];
export type IsDemo9 = boolean;
export type StrategyId2 = string;
export type CropId1 = (string | null)[];
export type InCrop = boolean[];
/**
 * Root-zone soil water at the end of the day
 */
export type StorageMm = (number | null)[];
/**
 * FAO-56 water-stress coefficient (1 = no stress)
 */
export type Ks = (number | null)[];
export type IrrigationMm = (number | null)[];
export type AetMm = (number | null)[];
export type RunId3 = string;
export type Years1 = number[];
export type InSamplePool1 = boolean;
/**
 * Strategy-calendar dates (the comparison horizon)
 */
export type Dates = string[];
/**
 * The historical dates whose weather is replayed
 */
export type SourceDates = string[];
export type RainMm1 = (number | null)[];
export type Et0Mm = (number | null)[];
export type Series = ReplaySeries[];
export type TurningPoint = string | null;
export type TurningPointReason = string | null;
export type SourceIds6 = string[];
export type Limitations3 = string[];
export type IsDemo10 = boolean;
export type ValueKind1 = "farmer_input";
export type Confirmed = boolean;
export type PlantingHistory = string | null;
export type HarvestHistory = string | null;
/**
 * Farmer agrees with the stored soil profile
 */
export type SoilConfirmed = boolean | null;
export type SoilNotes = string | null;
/**
 * mm per irrigated season
 */
export type IrrigationAllocationMm = number | null;
export type Equipment = string[];
/**
 * Crops the farmer can grow; None = not stated (all catalog crops allowed)
 */
export type AvailableCropIds = string[] | null;
export type MarketUse = string | null;
export type UpdatedAt = string | null;
export type SiteId7 = string;
export type Start = string;
export type End = string;
export type WeatherSourceId1 = string | null;
export type ProcessingRunId2 = string | null;
export type Dates1 = string[];
export type RainMm2 = (number | null)[];
export type RainFlag = (string | null)[];
export type TmaxC = (number | null)[];
export type TminC = (number | null)[];
export type VegetationSourceId = string | null;
export type VegetationDates = string[];
export type Ndvi = (number | null)[];
export type VegetationNote = string | null;
export type SourceIds7 = string[];
export type IsDemo11 = boolean;
export type ConserveWater = number;
export type ProtectSoil = number;
export type SiteId8 = string;
export type RunId4 = string;
export type ChosenStrategyId1 = string;
export type Reason3 = string;
export type Id11 = string;
export type SiteId9 = string;
export type SiteName = string;
export type CreatedAt3 = string;
export type ChosenStrategyId2 = string;
export type Reason4 = string;
export type Strategies1 = Strategy[];
export type Results = Result[];
export type Deltas = PairedDelta[];
export type Sources = Source[];
export type Crops = CropProfile[];
export type Assumptions = string[];
export type Limitations4 = string[];
export type LocalReviewQuestions = string[];
export type UnsupportedClaims1 = string[];
export type JsonUrl = string;
export type PdfUrl = string | null;
/**
 * SHA-256 of the exported JSON
 */
export type Sha256 = string | null;
export type IsDemo12 = boolean;

/**
 * Schema version 1.2.0. Generated - do not edit.
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
  RunRequest?: RunRequest;
  ReplayWindow?: ReplayWindow;
  RunDetail?: RunDetail;
  PairedDelta?: PairedDelta;
  ReplaySeries?: ReplaySeries;
  ReplayTrace?: ReplayTrace;
  FarmerContext?: FarmerContext;
  EnvironmentalTimeline?: EnvironmentalTimeline;
  Priorities?: Priorities;
  DecisionCardRequest?: DecisionCardRequest;
  DecisionCard?: DecisionCard;
}
export interface Site {
  id: Id;
  name: Name;
  latitude: Latitude;
  longitude: Longitude;
  boundary_geojson?: BoundaryGeojson;
  timezone: Timezone;
  area_ha?: AreaHa;
  farmer_context?: SiteFarmerContext;
  is_demo?: IsDemo;
}
/**
 * Farmer-confirmed context as stored (FarmerContext contract, served by /sites/{id}/farmer-context)
 */
export interface SiteFarmerContext {
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
  low?: Low;
  high?: High;
  bounds_kind?: BoundsKind;
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
  source_ids?: SourceIds2;
  train_period?: TrainPeriod;
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
  source_ids?: SourceIds3;
  processing_run_id?: ProcessingRunId1;
  chart?: Chart;
  details?: Details;
  is_demo?: IsDemo8;
}
export interface Details {
  [k: string]: unknown;
}
/**
 * A comparison run with the D6 supported edits only. Unsupported edits are rejected, never approximated.
 */
export interface RunRequest {
  site_id: SiteId6;
  mode?: SimulationMode1;
  allocation_mm?: AllocationMm1;
  planting_shift_days?: PlantingShiftDays;
  n_paths?: NPaths1;
  seed?: Seed1;
}
/**
 * strategy_id -> days to move every crop season (|days| <= 14, D6)
 */
export interface PlantingShiftDays {
  [k: string]: number;
}
export interface ReplayWindow {
  years: Years;
  enabled: Enabled;
  reason?: Reason2;
  in_sample_pool: InSamplePool;
  rain_mm?: RainMm;
}
/**
 * A stored run with everything the comparison screens need besides results and deltas.
 */
export interface RunDetail {
  run: SimulationRun;
  request: RunRequest;
  strategies: Strategies;
  replay_windows: ReplayWindows;
  excluded_blocks?: ExcludedBlocks;
  limitations?: Limitations2;
  source_ids: SourceIds4;
  scenario_notes?: ScenarioNotes;
  unsupported_claims?: UnsupportedClaims;
  cached?: Cached;
}
/**
 * Strategy minus baseline on the same weather path, summarised across paths (paired comparison).
 */
export interface PairedDelta {
  id: Id10;
  run_id: RunId2;
  strategy_id: StrategyId1;
  baseline_strategy_id: BaselineStrategyId;
  metric: Metric1;
  unit: Unit3;
  p10: P101;
  p50: P501;
  p90: P901;
  range_label?: RangeLabel1;
  better_direction: BetterDirection;
  share_better: ShareBetter;
  share_worse: ShareWorse;
  sample_count: SampleCount2;
  source_ids?: SourceIds5;
  is_demo?: IsDemo9;
}
export interface ReplaySeries {
  strategy_id: StrategyId2;
  crop_id: CropId1;
  in_crop: InCrop;
  storage_mm: StorageMm;
  ks: Ks;
  irrigation_mm: IrrigationMm;
  aet_mm: AetMm;
  metrics: Metrics1;
}
/**
 * This single path's metrics (no range: one path)
 */
export interface Metrics1 {
  [k: string]: number;
}
/**
 * One historical weather window replayed day by day for every strategy (identical weather).
 */
export interface ReplayTrace {
  run_id: RunId3;
  years: Years1;
  in_sample_pool: InSamplePool1;
  dates: Dates;
  source_dates: SourceDates;
  rain_mm: RainMm1;
  et0_mm: Et0Mm;
  series: Series;
  turning_point: TurningPoint;
  turning_point_reason: TurningPointReason;
  source_ids: SourceIds6;
  limitations?: Limitations3;
  is_demo?: IsDemo10;
}
/**
 * Farmer-confirmed inputs (value kind farmer_input). Unconfirmed fields stay null, never guessed.
 */
export interface FarmerContext {
  value_kind?: ValueKind1;
  confirmed?: Confirmed;
  planting_history?: PlantingHistory;
  harvest_history?: HarvestHistory;
  soil_confirmed?: SoilConfirmed;
  soil_notes?: SoilNotes;
  irrigation_allocation_mm?: IrrigationAllocationMm;
  equipment?: Equipment;
  available_crop_ids?: AvailableCropIds;
  market_use?: MarketUse;
  updated_at?: UpdatedAt;
}
/**
 * Daily weather and satellite vegetation for the Observe timeline. Missing values stay null.
 */
export interface EnvironmentalTimeline {
  site_id: SiteId7;
  start: Start;
  end: End;
  weather_source_id: WeatherSourceId1;
  processing_run_id: ProcessingRunId2;
  dates: Dates1;
  rain_mm: RainMm2;
  rain_flag: RainFlag;
  tmax_c: TmaxC;
  tmin_c: TminC;
  vegetation_source_id?: VegetationSourceId;
  vegetation_dates?: VegetationDates;
  ndvi?: Ndvi;
  vegetation_note?: VegetationNote;
  source_ids: SourceIds7;
  is_demo?: IsDemo11;
}
/**
 * Farmer priorities rank feasible options; they never override hard constraints.
 */
export interface Priorities {
  conserve_water?: ConserveWater;
  protect_soil?: ProtectSoil;
}
export interface DecisionCardRequest {
  site_id: SiteId8;
  run_id: RunId4;
  chosen_strategy_id: ChosenStrategyId1;
  reason: Reason3;
  priorities?: Priorities | null;
}
/**
 * Everything needed to review a decision later: choice, reason, evidence, assumptions, open questions.
 */
export interface DecisionCard {
  id: Id11;
  site_id: SiteId9;
  site_name: SiteName;
  created_at: CreatedAt3;
  chosen_strategy_id: ChosenStrategyId2;
  reason: Reason4;
  priorities: Priorities | null;
  farmer_context: FarmerContext | null;
  run: SimulationRun;
  request: RunRequest;
  strategies: Strategies1;
  results: Results;
  deltas: Deltas;
  sources: Sources;
  crops: Crops;
  assumptions: Assumptions;
  limitations: Limitations4;
  local_review_questions: LocalReviewQuestions;
  unsupported_claims: UnsupportedClaims1;
  json_url: JsonUrl;
  pdf_url: PdfUrl;
  sha256?: Sha256;
  is_demo?: IsDemo12;
}
