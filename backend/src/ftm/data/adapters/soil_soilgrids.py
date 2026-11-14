"""ISRIC SoilGrids 2.0 soil properties via the REST point query. Owner: M3. Global, 250 m.

Service: https://rest.isric.org/soilgrids/v2.0/docs
Citation: Poggio, L. et al. (2021). SoilGrids 2.0: producing soil information for the globe with
quantified spatial uncertainty. SOIL 7, 217-240. doi:10.5194/soil-7-217-2021. License: CC BY 4.0.

AWC is derived per depth interval as volumetric water at 33 kPa (``wv0033``, field capacity) minus
1500 kPa (``wv1500``, wilting point), using the predicted means. SoilGrids publishes 5%/95% quantiles
for each property, but the quantiles of a difference cannot be obtained by subtracting quantiles, so
no AWC interval is produced here; those quantiles are reported as context instead.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx

from ftm.config import get_settings
from ftm.contracts.models import ParamValue, SoilProfile, Source, ValueKind
from ftm.data.raw_cache import RawSnapshot, find_latest_raw, save_raw
from ftm.data.soil import DEFAULT_DEPTH_M, Layer, SoilResult, water_mm_per_m
from ftm.provenance import sha256_file

QUERY_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
SOURCE_KEY = "soilgrids"
PROPERTIES = ("wv0033", "wv1500", "clay", "sand", "silt")
DEPTHS = ("0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm")
VALUES = ("mean", "Q0.05", "Q0.5", "Q0.95")
CITATION = (
    "Poggio, L. et al. (2021). SoilGrids 2.0: producing soil information for the globe with quantified "
    "spatial uncertainty. SOIL 7, 217-240. doi:10.5194/soil-7-217-2021"
)


class SoilGridsError(ValueError):
    """The SoilGrids answer is missing a property, depth or value we rely on."""


def raw_filename(lat: float, lon: float) -> str:
    return f"point_{lat:.5f}_{lon:.5f}.json"


def fetch_cached(lat: float, lon: float, *, raw_dir: Any = None, client: httpx.Client | None = None) -> RawSnapshot:
    root = raw_dir or get_settings().raw_dir
    existing = find_latest_raw(SOURCE_KEY, raw_filename(lat, lon), root)
    if existing is not None:
        retrieved = datetime.strptime(existing.parent.name, "%Y-%m-%d").replace(tzinfo=UTC)
        return RawSnapshot(existing, existing.relative_to(root.parent).as_posix(), sha256_file(existing), retrieved)
    params: list[tuple[str, str | float]] = [("lon", round(lon, 5)), ("lat", round(lat, 5))]
    params += [("property", p) for p in PROPERTIES] + [("depth", d) for d in DEPTHS] + [("value", v) for v in VALUES]
    own = client is None
    http = client or httpx.Client(timeout=120, transport=httpx.HTTPTransport(retries=3))
    try:
        resp = http.get(QUERY_URL, params=params)
        resp.raise_for_status()
    finally:
        if own:
            http.close()
    parse(resp.content)
    return save_raw(SOURCE_KEY, raw_filename(lat, lon), resp.content, root)


def parse(content: bytes) -> dict[str, dict[str, dict[str, float | None]]]:
    """Return ``{property: {depth_label: {value_name: value in target units}}}`` (d_factor applied)."""
    try:
        layers = json.loads(content)["properties"]["layers"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SoilGridsError(f"unexpected SoilGrids response: {exc}") from exc
    out: dict[str, dict[str, dict[str, float | None]]] = {}
    for layer in layers:
        d_factor = float(layer["unit_measure"]["d_factor"])
        out[layer["name"]] = {
            d["label"]: {k: (None if v is None else v / d_factor) for k, v in d["values"].items()}
            for d in layer["depths"]
        }
    missing = [p for p in ("wv0033", "wv1500") if p not in out]
    if missing:
        raise SoilGridsError(f"SoilGrids response lacks {missing}")
    return out


def _bounds(label: str) -> tuple[float, float]:
    top, bottom = label.removesuffix("cm").split("-")
    return float(top), float(bottom)


def build(site_id: str, snapshot: RawSnapshot, depth_m: float = DEFAULT_DEPTH_M) -> SoilResult:
    data = parse(snapshot.path.read_bytes())
    fc, wp = data["wv0033"], data["wv1500"]
    layers = []
    table = []
    for label in DEPTHS:
        top, bottom = _bounds(label)
        f = fc.get(label, {}).get("mean")
        w = wp.get(label, {}).get("mean")
        awc = None if f is None or w is None else (f - w) / 100.0  # % vol -> cm3/cm3
        layers.append(Layer(top, bottom, awc))
        table.append(
            {
                "depth": label,
                "fc_pct_mean": f,
                "fc_pct_q05_q95": [fc.get(label, {}).get("Q0.05"), fc.get(label, {}).get("Q0.95")],
                "wp_pct_mean": w,
                "wp_pct_q05_q95": [wp.get(label, {}).get("Q0.05"), wp.get(label, {}).get("Q0.95")],
                "awc_cm3_cm3": None if awc is None else round(awc, 4),
            }
        )
    awc_mm_m = water_mm_per_m(layers, depth_m)
    top30 = ("0-5cm", "5-15cm", "15-30cm")
    texture = None
    if all(p in data for p in ("clay", "sand", "silt")):
        frac = {p: _depth_mean(data[p], top30) for p in ("clay", "sand", "silt")}
        if all(v is not None for v in frac.values()):
            texture = (
                f"clay {frac['clay']:.0f}%, sand {frac['sand']:.0f}%, silt {frac['silt']:.0f}% "
                "(0-30 cm, SoilGrids mean)"
            )

    source_id = f"soilgrids_{snapshot.sha256[:16]}"
    source = Source(
        id=source_id,
        provider="ISRIC - World Soil Information",
        product="SoilGrids 2.0 (REST point query)",
        version="2.0",
        variables=list(PROPERTIES),
        units={"wv0033": "% vol", "wv1500": "% vol", "clay": "%", "sand": "%", "silt": "%"},
        kind=ValueKind.REANALYSIS,  # model-based digital soil mapping; contract has no "modeled" kind yet
        spatial_resolution="250 m grid",
        temporal_resolution="static",
        retrieved_at=snapshot.retrieved_at,
        url=QUERY_URL,
        doi="10.5194/soil-7-217-2021",
        license="CC BY 4.0",
        attribution=CITATION,
        qa_notes="Values are model predictions with published 5%/95% quantiles per property and depth.",
        limitations=(
            "Machine-learning predictions at 250 m, not measurements at the field. Uncertainty can be very "
            "large where few soil profiles were sampled. AWC is derived from predicted means; no AWC "
            "interval is available from the source."
        ),
        raw_path=snapshot.relative_path,
        raw_sha256=snapshot.sha256,
    )
    profile = SoilProfile(
        id=f"soil_{site_id}_{source_id}",
        site_id=site_id,
        available_water_capacity_mm_per_m=ParamValue(
            value=None if awc_mm_m is None else round(awc_mm_m, 1),
            unit="mm/m",
            reference=CITATION if awc_mm_m is not None else None,
            region_relevance="Global 250 m model prediction at the site point",
            uncertainty=(
                "No AWC interval from source (quantiles of field capacity and wilting point cannot be "
                "differenced). For sensitivity use the validation plan's declared +/-20% assumption."
            ),
        ),
        root_zone_depth_m=ParamValue(
            value=None,
            unit="m",
            reference=None,
            uncertainty="Crop-dependent: set from the crop catalog (M4). Soil data does not define root depth.",
        ),
        texture=texture,
        source_ids=[source_id],
    )
    return SoilResult(
        profile=profile,
        source=source,
        awc_low_mm_per_m=None,
        awc_high_mm_per_m=None,
        details={"depth_m": depth_m, "layers": table},
    )


def _depth_mean(prop: dict[str, dict[str, float | None]], labels: tuple[str, ...]) -> float | None:
    total = weight = 0.0
    for label in labels:
        v = prop.get(label, {}).get("mean")
        if v is None:
            return None
        top, bottom = _bounds(label)
        total += v * (bottom - top)
        weight += bottom - top
    return total / weight
