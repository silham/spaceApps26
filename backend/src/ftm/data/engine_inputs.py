"""Everything the engine needs for a loaded site, read from the database. Owner: M3 (used by M1's API).

One place turns stored rows into engine inputs, so the API (``POST /runs``) and the command-line runner
(``scripts/run_engine_site.py``) feed the engine identically. Nothing is assumed when an input is missing:
``EngineInputsNotAvailableError`` names what to load.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.config import get_settings
from ftm.contracts.models import Site, SoilProfile, Source
from ftm.data.forcing import ForcingNotAvailableError, get_daily_forcing
from ftm.db.models import ProcessingRunRow, SiteRow, SoilProfileRow, SourceRow
from ftm.engine.forcing import from_store_frame
from ftm.engine.params import SoilSpec, soil_spec_from_profile
from ftm.engine.scenarios import Scenario, build_ks_field_2

# Full weather record loaded by scripts/load_power.py (1981-2025); the sample pool is a subset (validation plan s1).
RECORD = (date(1981, 1, 1), date(2025, 12, 31))
# Validation plan v1.2 section 1: ET0-based ranges draw from 1984-2019; 2020-2025 are held out.
DEFAULT_POOL = (1984, 2019)
# M3 integrates AWC over 0-1 m (soil adapters' DEFAULT_DEPTH_M).
SOIL_DATA_DEPTH_M = 1.0

# Strategies are defined per site (D5). A site without an entry has no scenarios, so runs are refused.
SCENARIO_BUILDERS: dict[str, Callable[..., Scenario]] = {"ks-field-2": build_ks_field_2}


class EngineInputsNotAvailableError(LookupError):
    """A required stored input is missing. The message says what to load."""


@dataclass(frozen=True)
class SiteEngineInputs:
    site: Site
    weather_source: Source
    soil_profile: SoilProfile
    soil: SoilSpec
    forcing: pd.DataFrame
    elevation_m: float
    elevation_note: str


def site_contract(row: SiteRow) -> Site:
    return Site(
        id=row.id,
        name=row.name,
        latitude=row.latitude,
        longitude=row.longitude,
        timezone=row.timezone,
        area_ha=row.area_ha,
        farmer_context=row.farmer_context or {},
        is_demo=row.is_demo,
    )


def source_contract(row: SourceRow) -> Source:
    fields = {k: getattr(row, k) for k in Source.model_fields if k != "footprint_geojson"}
    return Source.model_validate(fields)


def latest_weather_source_id(session: Session, site_id: str) -> str | None:
    """The weather (POWER) source of the site's newest processing run; one rainfall source per run (D7)."""
    rows = session.execute(
        select(ProcessingRunRow).where(ProcessingRunRow.site_id == site_id).order_by(ProcessingRunRow.created_at.desc())
    ).scalars()
    for run in rows:
        for sid in run.input_source_ids or []:
            if sid.startswith("power_"):
                return str(sid)
    return None


def latest_soil_profile(session: Session, site_id: str) -> SoilProfileRow | None:
    q = select(SoilProfileRow).where(SoilProfileRow.site_id == site_id).order_by(SoilProfileRow.created_at.desc())
    return session.scalars(q).first()


def elevation_from_power(source: Source) -> tuple[float, str]:
    """POWER grid-cell elevation from the immutable raw snapshot (until ``Site.elevation_m`` exists)."""
    from ftm.data.adapters import nasa_power

    if not source.raw_path:
        raise EngineInputsNotAvailableError(f"weather source {source.id} has no raw snapshot; elevation unknown")
    path = get_settings().data_dir / source.raw_path
    if not path.exists():
        raise EngineInputsNotAvailableError(
            f"raw snapshot {source.raw_path} for {source.id} is missing on disk; elevation unknown "
            "(restore data/raw or rerun scripts/load_power.py)"
        )
    parsed = nasa_power.parse_daily(path.read_bytes())
    if parsed.elevation_m is None:
        raise EngineInputsNotAvailableError("POWER reported no elevation; the engine never assumes one")
    return float(parsed.elevation_m), f"{parsed.elevation_m:.0f} m, POWER grid-cell elevation ({source.id})"


def load_site_engine_inputs(session: Session, site_id: str, weather_source_id: str | None = None) -> SiteEngineInputs:
    site_row = session.get(SiteRow, site_id)
    if site_row is None:
        raise EngineInputsNotAvailableError(f"site {site_id!r} is not in the database; run scripts/load_site.py")
    weather_source_id = weather_source_id or latest_weather_source_id(session, site_id)
    if weather_source_id is None:
        raise EngineInputsNotAvailableError(f"no processed weather for {site_id!r}; run scripts/load_power.py")
    src_row = session.get(SourceRow, weather_source_id)
    if src_row is None:
        raise EngineInputsNotAvailableError(f"weather source {weather_source_id!r} is not in the database")
    soil_row = latest_soil_profile(session, site_id)
    if soil_row is None:
        raise EngineInputsNotAvailableError(
            f"no soil profile for {site_id!r}; run scripts/load_soil.py (the engine never assumes a soil)"
        )
    site, source = site_contract(site_row), source_contract(src_row)
    profile = SoilProfile.model_validate(soil_row.params)
    start = source.coverage_start or RECORD[0]
    end = source.coverage_end or RECORD[1]
    try:
        forcing = from_store_frame(get_daily_forcing(site.id, start, end, source.id, session=session))
    except ForcingNotAvailableError as exc:
        raise EngineInputsNotAvailableError(str(exc)) from exc
    elevation, note = elevation_from_power(source)
    soil = soil_spec_from_profile(profile, data_depth_m=SOIL_DATA_DEPTH_M)
    return SiteEngineInputs(site, source, profile, soil, forcing, elevation, note)


def build_site_scenario(inputs: SiteEngineInputs, pool: tuple[int, int] = DEFAULT_POOL) -> Scenario:
    builder = SCENARIO_BUILDERS.get(inputs.site.id)
    if builder is None:
        raise EngineInputsNotAvailableError(
            f"no strategies are defined for site {inputs.site.id!r} (D5 covers ks-field-2 only)"
        )
    return builder(inputs.forcing, list(range(pool[0], pool[1] + 1)), site_id=inputs.site.id)
