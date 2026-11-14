"""User-selected farms anywhere in the world (D13: observe only). Owner: M1, using M3's loaders.

``create_site`` registers the location and starts a background load that runs M3's existing loader scripts
unchanged (weather: NASA POWER, global; soil: SSURGO in the contiguous US, SoilGrids elsewhere per D8;
vegetation: MODIS via Earth Engine when it is signed in). A step that fails is reported with its reason and
the farm keeps whatever loaded; nothing is substituted. Comparison runs stay limited to sites with locally
reviewed strategies (D5); every other farm is observe-only and the API says so.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import threading
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ftm.contracts.models import MAX_NEW_SITE_AREA_HA, NewSiteRequest, SiteLoadStatus, SiteLoadStep
from ftm.data.engine_inputs import SCENARIO_BUILDERS, latest_weather_source_id
from ftm.db.models import SiteRow, SourceRow, StrategyRow
from ftm.provenance import inputs_hash

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
RECORD_START = date(1981, 1, 1)  # same start as ks-field-2 (scripts/load_site.py)
# D16: the record runs to yesterday (UTC); POWER's last few days come back missing (-999) and stay missing.
STALE_AFTER = timedelta(days=3)
FORECAST_STALE_AFTER = timedelta(days=7)


def record_end(today: date | None = None) -> date:
    return (today or datetime.now(UTC).date()) - timedelta(days=1)


STATUS = "user-selected location; not locally reviewed (D13: observe only)"
STEP_TIMEOUT_S = 900
EE_NOT_SIGNED_IN = "Earth Engine is not signed in on the server (run `earthengine authenticate`); vegetation not loaded"


class SiteRequestError(ValueError):
    """The location or outline cannot be accepted; the message is shown to the user."""


_lock = threading.Lock()
_jobs: dict[str, SiteLoadStatus] = {}
# One load at a time: NASA POWER and SoilGrids throttle concurrent requests from one client.
_one_load = threading.Semaphore(1)


def in_conus(lat: float, lon: float) -> bool:
    return 24.0 <= lat <= 49.5 and -125.0 <= lon <= -66.5


# Ids derived from the site id (soil profile ``soil_<site>_<source>``, validation ``val_phenology_<site>_<utc>``) are
# stored in 64-character columns; with the longest source id that leaves 32 characters for the site id.
MAX_SITE_ID_LEN = 32
SLUG_LEN = 14


def site_id_for(req: NewSiteRequest, owner_user_id: str | None = None) -> str:
    """``<name slug>-<8 hex of the coordinates>[-<8 hex of the owner>]``: at most 32 characters, stable per farm."""
    slug = re.sub(r"[^a-z0-9]+", "-", req.name.lower()).strip("-")[:SLUG_LEN].strip("-") or "farm"
    site_id = f"{slug}-{inputs_hash({'lat': round(req.latitude, 5), 'lon': round(req.longitude, 5)})[:8]}"
    if owner_user_id:
        site_id += "-" + inputs_hash({"owner": owner_user_id})[:8]
    return site_id


def has_strategies(session: Session, site_id: str) -> bool:
    return (
        site_id in SCENARIO_BUILDERS
        or (
            session.scalar(
                select(func.count())
                .select_from(StrategyRow)
                .where(StrategyRow.site_id == site_id, StrategyRow.superseded.is_(False))
            )
            or 0
        )
        > 0
    )


def _timezone(lat: float, lon: float) -> str:
    from timezonefinder import TimezoneFinder  # MIT; offline polygon lookup

    tz = TimezoneFinder().timezone_at(lat=lat, lng=lon)
    if tz is None or tz.startswith("Etc/"):  # Etc/GMT±n zones are the open sea
        raise SiteRequestError("this point is not on land; pick a point inside a field")
    return tz


def _multipolygon(g: dict[str, Any]) -> dict[str, Any]:
    g = g.get("geometry", g)
    if g.get("type") == "Polygon":
        return {"type": "MultiPolygon", "coordinates": [g["coordinates"]]}
    if g.get("type") != "MultiPolygon":
        raise SiteRequestError(f"the field outline must be a polygon, got {g.get('type')!r}")
    return g


def _check_boundary(session: Session, req: NewSiteRequest) -> tuple[dict[str, Any] | None, float | None]:
    if req.boundary_geojson is None:
        return None, None
    g = _multipolygon(req.boundary_geojson)
    row = session.execute(
        text(
            "select ST_IsValid(g), ST_Area(g::geography) / 10000.0, "
            "ST_Covers(g, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)) "
            "from (select ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326) as g) t"
        ),
        {"g": json.dumps(g), "lat": req.latitude, "lon": req.longitude},
    ).one()
    valid, area_ha, covers = bool(row[0]), float(row[1]), bool(row[2])
    if not valid:
        raise SiteRequestError("the field outline crosses itself; redraw it")
    if area_ha > MAX_NEW_SITE_AREA_HA:
        limit = f"{MAX_NEW_SITE_AREA_HA:,.0f}"
        raise SiteRequestError(f"the outline covers {area_ha:,.0f} ha; draw one field (at most {limit} ha)")
    if not covers:
        raise SiteRequestError("the selected point must lie inside the drawn field")
    return g, round(area_ha, 1)


def _steps(lat: float, lon: float) -> list[SiteLoadStep]:
    soil = "USDA SSURGO" if in_conus(lat, lon) else "ISRIC SoilGrids 2.0"
    return [
        SiteLoadStep(name="weather", source="NASA POWER daily, 1981 to the latest day", status="pending"),
        SiteLoadStep(name="soil", source=soil, status="pending"),
        SiteLoadStep(name="vegetation", source="MODIS MOD13Q1 NDVI via Earth Engine", status="pending"),
        SiteLoadStep(name="forecast", source="ECMWF SEAS5 seasonal forecast via Open-Meteo", status="pending"),
    ]


def create_site(session: Session, req: NewSiteRequest, *, owner_user_id: str | None = None) -> SiteLoadStatus:
    site_id = site_id_for(req, owner_user_id)
    with _lock:
        job = _jobs.get(site_id)
    if job is not None and job.status in ("queued", "running"):
        return job
    tz = _timezone(req.latitude, req.longitude)
    boundary, area_ha = _check_boundary(session, req)
    if session.get(SiteRow, site_id) is not None:
        # Same farm again: only a failed (or interrupted) load is restarted ("try again"); otherwise report it.
        current = load_status(session, site_id)
        if current.status != "failed":
            return current
    else:
        _add_site_row(session, site_id, req, tz, boundary, area_ha, owner_user_id)
    job = SiteLoadStatus(
        site_id=site_id, status="queued", steps=_steps(req.latitude, req.longitude), has_strategies=False
    )
    with _lock:
        _jobs[site_id] = job
    threading.Thread(
        target=_load, args=(site_id, req, tz, boundary, area_ha), name=f"load-{site_id}", daemon=True
    ).start()
    return job


def _add_site_row(
    session: Session,
    site_id: str,
    req: NewSiteRequest,
    tz: str,
    boundary: dict[str, Any] | None,
    area_ha: float | None,
    owner_user_id: str | None,
) -> None:
    # The row exists from the start so the farm is listed (with its load progress) while data loads.
    session.add(
        SiteRow(
            id=site_id,
            name=req.name.strip(),
            latitude=req.latitude,
            longitude=req.longitude,
            timezone=tz,
            area_ha=area_ha,
            owner_user_id=owner_user_id,
            farmer_context={},
            boundary=func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(boundary)), 4326) if boundary else None,
        )
    )
    session.commit()


def _set(site_id: str, **changes: Any) -> None:
    with _lock:
        _jobs[site_id] = _jobs[site_id].model_copy(update=changes)


def _set_step(site_id: str, name: str, status: str, message: str | None = None) -> None:
    with _lock:
        job = _jobs[site_id]
        upd = {"status": status, "message": message}
        steps = [s.model_copy(update=upd) if s.name == name else s for s in job.steps]
        _jobs[site_id] = job.model_copy(update={"steps": steps})


def _run_script(script: str, *args: str) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args],
            capture_output=True,
            text=True,
            timeout=STEP_TIMEOUT_S,
            cwd=SCRIPTS.parent,
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {STEP_TIMEOUT_S // 60} minutes"
    if proc.returncode == 0:
        return True, ""
    out = proc.stderr or proc.stdout
    if "earthengine authenticate" in out or "ee.Authenticate" in out:
        return False, EE_NOT_SIGNED_IN
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    return False, _readable(lines[-1] if lines else f"exit code {proc.returncode}")


def _readable(line: str) -> str:
    """Last error line, with credentials never echoed (keys can appear in request URLs)."""
    line = re.sub(r"(key|token|api_key)=[^&\s]+", r"\1=***", line, flags=re.I)
    return line[-300:]


def _load(site_id: str, req: NewSiteRequest, tz: str, boundary: dict[str, Any] | None, area_ha: float | None) -> None:
    with _one_load:
        _load_steps(site_id, req, tz, boundary, area_ha)


def _load_steps(
    site_id: str, req: NewSiteRequest, tz: str, boundary: dict[str, Any] | None, area_ha: float | None
) -> None:
    _set(site_id, status="running", started_at=datetime.now(UTC))
    with tempfile.TemporaryDirectory() as tmp:
        power = [
            "--site-id", site_id, "--name", req.name,
            "--lat", f"{req.latitude}", "--lon", f"{req.longitude}", "--timezone", tz,
            "--start", RECORD_START.isoformat(), "--end", record_end().isoformat(), "--status", STATUS,
        ]  # fmt: skip
        if boundary is not None:
            path = Path(tmp) / "boundary.geojson"
            path.write_text(json.dumps(boundary), encoding="utf-8")
            power += ["--boundary", str(path)]
        if area_ha is not None:
            power += ["--area-ha", f"{area_ha}"]

        _set_step(site_id, "weather", "running")
        ok, msg = _run_script("load_power.py", *power)
        _set_step(site_id, "weather", "done" if ok else "failed", msg or None)
        if not ok:  # without weather nothing else can be aligned; the farm row stays and reports the failure
            _set(site_id, status="failed", finished_at=datetime.now(UTC))
            return

        soil = "ssurgo" if in_conus(req.latitude, req.longitude) else "soilgrids"
        _set_step(site_id, "soil", "running")
        ok, msg = _run_script("load_soil.py", "--site-id", site_id, "--source", soil)
        _set_step(site_id, "soil", "done" if ok else "failed", msg or None)

        _set_step(site_id, "vegetation", "running")
        ok, msg = _run_script("load_modis.py", "--site-id", site_id)
        _set_step(site_id, "vegetation", "done" if ok else "failed", msg or None)

        # Without a forecast the farm still works: every past year is then equally likely (stated in results).
        _set_step(site_id, "forecast", "running")
        ok, msg = _run_script("load_forecast.py", "--site-id", site_id)
        _set_step(site_id, "forecast", "done" if ok else "failed", msg or None)
    _set(site_id, status="done", finished_at=datetime.now(UTC))


# ----------------------------------------------------------------- refresh (D16): newer weather and forecast

_refresh: dict[str, SiteLoadStatus] = {}


def refresh_needed(session: Session, site_id: str) -> tuple[bool, bool]:
    """(weather stale, forecast stale): weather older than 3 days, forecast older than 7 days or absent."""
    from ftm.db.models import ForecastSnapshotRow

    now = datetime.now(UTC)
    src_id = latest_weather_source_id(session, site_id)
    src = session.get(SourceRow, src_id) if src_id else None
    weather = src is None or src.coverage_end is None or record_end() - src.coverage_end >= STALE_AFTER
    snap = session.scalars(
        select(ForecastSnapshotRow)
        .where(ForecastSnapshotRow.site_id == site_id)
        .order_by(ForecastSnapshotRow.retrieved_at.desc())
        .limit(1)
    ).first()
    forecast = snap is None or now - snap.retrieved_at >= FORECAST_STALE_AFTER
    return weather, forecast


def refresh_site(session: Session, site_id: str) -> SiteLoadStatus:
    """Fetch newer weather and/or forecast in the background. Never blocks editing; one refresh at a time."""
    with _lock:
        job = _refresh.get(site_id)
    if job is not None and job.status in ("queued", "running"):
        return job
    with _lock:
        loading = _jobs.get(site_id)
    if loading is not None and loading.status in ("queued", "running"):
        return loading
    row = session.get(SiteRow, site_id)
    if row is None:
        raise LookupError(f"site {site_id!r} not found")
    weather, forecast = refresh_needed(session, site_id)
    steps = []
    if weather:
        steps.append(SiteLoadStep(name="weather", source="NASA POWER daily, to the latest day", status="pending"))
    if forecast:
        steps.append(
            SiteLoadStep(name="forecast", source="ECMWF SEAS5 seasonal forecast via Open-Meteo", status="pending")
        )
    job = SiteLoadStatus(
        site_id=site_id,
        status="queued" if steps else "done",
        steps=steps,
        has_strategies=has_strategies(session, site_id),
    )
    if not steps:
        return job
    with _lock:
        _refresh[site_id] = job
    args = (site_id, row.name, row.latitude, row.longitude, row.timezone, weather, forecast)
    threading.Thread(target=_do_refresh, args=args, name=f"refresh-{site_id}", daemon=True).start()
    return job


def _refresh_step(site_id: str, name: str, status: str, message: str | None = None) -> None:
    with _lock:
        job = _refresh[site_id]
        steps = [
            s.model_copy(update={"status": status, "message": message}) if s.name == name else s for s in job.steps
        ]
        _refresh[site_id] = job.model_copy(update={"steps": steps})


def _do_refresh(site_id: str, name: str, lat: float, lon: float, tz: str, weather: bool, forecast: bool) -> None:
    with _lock:
        _refresh[site_id] = _refresh[site_id].model_copy(update={"status": "running", "started_at": datetime.now(UTC)})
    failed = False
    with _one_load:
        if weather:
            _refresh_step(site_id, "weather", "running")
            ok, msg = _run_script(
                "load_power.py",
                "--site-id", site_id, "--name", name, "--lat", f"{lat}", "--lon", f"{lon}", "--timezone", tz,
                "--start", RECORD_START.isoformat(), "--end", record_end().isoformat(), "--status", STATUS,
            )  # fmt: skip
            _refresh_step(site_id, "weather", "done" if ok else "failed", msg or None)
            failed |= not ok
        if forecast:
            _refresh_step(site_id, "forecast", "running")
            ok, msg = _run_script("load_forecast.py", "--site-id", site_id)
            _refresh_step(site_id, "forecast", "done" if ok else "failed", msg or None)
            failed |= not ok
    with _lock:
        _refresh[site_id] = _refresh[site_id].model_copy(
            update={"status": "failed" if failed else "done", "finished_at": datetime.now(UTC)}
        )


def load_status(session: Session, site_id: str) -> SiteLoadStatus:
    """The background job when one ran in this server process; otherwise the stored state."""
    with _lock:
        job = _jobs.get(site_id)
    strategies = has_strategies(session, site_id)
    if job is not None:
        return job.model_copy(update={"has_strategies": strategies})
    row = session.get(SiteRow, site_id)
    if row is None:
        raise LookupError(f"site {site_id!r} not found")
    if latest_weather_source_id(session, site_id) is None:
        # The farm row is stored before loading starts, so a row alone does not mean data loaded: a load that
        # failed, or was cut off by an API restart, leaves no weather. Report it so the user can try again.
        return SiteLoadStatus(
            site_id=site_id,
            status="failed",
            steps=[
                SiteLoadStep(
                    name="weather",
                    source="NASA POWER daily",
                    status="failed",
                    message="no weather is stored for this farm; the load failed or was interrupted",
                )
            ],
            has_strategies=strategies,
        )
    return SiteLoadStatus(site_id=site_id, status="done", steps=[], has_strategies=strategies)
