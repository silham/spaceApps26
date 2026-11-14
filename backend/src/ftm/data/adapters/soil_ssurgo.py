"""USDA NRCS SSURGO soil data via the Soil Data Access (SDA) web service. Owner: M3. US only.

Service: https://sdmdataaccess.sc.egov.usda.gov/  (POST /Tabular/post.rest, SQL over the SSURGO tables)
Citation: Soil Survey Staff, Natural Resources Conservation Service, United States Department of
Agriculture. Soil Survey Geographic (SSURGO) Database. Public domain.

SSURGO gives available water capacity per horizon directly (``awc_r``, cm/cm) with documented low and
high values (``awc_l``, ``awc_h``). A map unit is a mix of soil components; we take the
component-percentage-weighted mean of each component's profile water.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import httpx

from ftm.config import get_settings
from ftm.contracts.models import ParamValue, SoilProfile, Source, ValueKind
from ftm.data.raw_cache import RawSnapshot, find_latest_raw, save_raw
from ftm.data.soil import DEFAULT_DEPTH_M, Layer, SoilResult, water_mm_per_m
from ftm.provenance import sha256_file

SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
SOURCE_KEY = "ssurgo"
CITATION = (
    "Soil Survey Staff, Natural Resources Conservation Service, United States Department of Agriculture. "
    "Soil Survey Geographic (SSURGO) Database, via Soil Data Access."
)

_QUERY = """
SELECT mu.mukey, mu.muname, l.areasymbol, sc.saverest,
       c.cokey, c.compname, c.comppct_r, c.majcompflag,
       ch.hzname, ch.hzdept_r, ch.hzdepb_r, ch.awc_l, ch.awc_r, ch.awc_h,
       ch.sandtotal_r, ch.silttotal_r, ch.claytotal_r,
       (SELECT TOP 1 tg.texdesc FROM chtexturegrp tg
         WHERE tg.chkey = ch.chkey AND tg.rvindicator = 'Yes') AS texdesc
FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('point({lon} {lat})') m
JOIN mapunit mu ON mu.mukey = m.mukey
JOIN legend l ON l.lkey = mu.lkey
JOIN sacatalog sc ON sc.areasymbol = l.areasymbol
JOIN component c ON c.mukey = mu.mukey
LEFT JOIN chorizon ch ON ch.cokey = c.cokey
ORDER BY c.comppct_r DESC, c.cokey, ch.hzdept_r
"""


class SsurgoError(ValueError):
    """SDA returned nothing usable for this point (outside the US, or no data)."""


def raw_filename(lat: float, lon: float) -> str:
    return f"sda_point_{lat:.5f}_{lon:.5f}.json"


def fetch_cached(lat: float, lon: float, *, raw_dir: Any = None, client: httpx.Client | None = None) -> RawSnapshot:
    """Reuse the newest raw SDA response for this point, else query SDA and store the body unchanged."""
    root = raw_dir or get_settings().raw_dir
    existing = find_latest_raw(SOURCE_KEY, raw_filename(lat, lon), root)
    if existing is not None:
        retrieved = datetime.strptime(existing.parent.name, "%Y-%m-%d").replace(tzinfo=UTC)
        return RawSnapshot(existing, existing.relative_to(root.parent).as_posix(), sha256_file(existing), retrieved)
    body = {"query": _QUERY.format(lat=f"{lat:.6f}", lon=f"{lon:.6f}"), "format": "JSON+COLUMNNAME"}
    own = client is None
    http = client or httpx.Client(timeout=90, transport=httpx.HTTPTransport(retries=3))
    try:
        resp = http.post(SDA_URL, json=body)
        resp.raise_for_status()
    finally:
        if own:
            http.close()
    parse(resp.content)  # never cache a response we cannot read
    return save_raw(SOURCE_KEY, raw_filename(lat, lon), resp.content, root)


def parse(content: bytes) -> list[dict[str, str | None]]:
    try:
        table = json.loads(content).get("Table") if content.strip() else None
    except json.JSONDecodeError as exc:
        raise SsurgoError(f"SDA response is not JSON: {exc}") from exc
    if not table or len(table) < 2:
        raise SsurgoError("SDA returned no soil map unit for this point (SSURGO covers the US only)")
    header, *rows = table
    return [dict(zip(header, r, strict=True)) for r in rows]


def build(site_id: str, snapshot: RawSnapshot, depth_m: float = DEFAULT_DEPTH_M) -> SoilResult:
    rows = parse(snapshot.path.read_bytes())
    first = rows[0]
    comps: dict[str, list[dict[str, str | None]]] = defaultdict(list)
    for r in rows:
        comps[str(r["cokey"])].append(r)

    per_comp = []
    for cokey, hz in comps.items():
        pct = _f(hz[0]["comppct_r"]) or 0.0
        values = {
            k: water_mm_per_m([Layer(_f(h["hzdept_r"]) or 0, _f(h["hzdepb_r"]) or 0, _f(h[k])) for h in hz], depth_m)
            if hz[0]["hzdept_r"] is not None
            else None
            for k in ("awc_l", "awc_r", "awc_h")
        }
        per_comp.append({"cokey": cokey, "name": hz[0]["compname"], "pct": pct, **values})

    usable = [c for c in per_comp if c["awc_r"] is not None and c["pct"] > 0]
    total_pct = sum(c["pct"] for c in per_comp)
    used_pct = sum(c["pct"] for c in usable)
    awc = _weighted(usable, "awc_r")
    low = _weighted(usable, "awc_l") if all(c["awc_l"] is not None for c in usable) else None
    high = _weighted(usable, "awc_h") if all(c["awc_h"] is not None for c in usable) else None
    dominant = max(per_comp, key=lambda c: c["pct"])
    surface = comps[dominant["cokey"]][0]

    source_id = f"ssurgo_{snapshot.sha256[:16]}"
    survey = f"{first['areasymbol']} (survey version {first['saverest']})"
    source = Source(
        id=source_id,
        provider="USDA Natural Resources Conservation Service",
        product="SSURGO via Soil Data Access",
        version=str(first["saverest"])[:64] if first["saverest"] else None,
        variables=["awc_l", "awc_r", "awc_h", "texdesc", "sand/silt/clay"],
        units={"awc_r": "cm/cm", "awc_l": "cm/cm", "awc_h": "cm/cm", "sand/silt/clay": "%"},
        kind=ValueKind.LITERATURE,
        spatial_resolution="Soil map unit polygon (survey scale)",
        temporal_resolution="static (survey)",
        retrieved_at=snapshot.retrieved_at,
        url=SDA_URL,
        license="US public domain",
        attribution=CITATION,
        qa_notes=f"Map unit {first['mukey']} '{first['muname']}', area {survey}.",
        limitations=(
            "A map unit generalises several soil components; values are representative estimates, not "
            "measurements at the field. Low/high are SSURGO's documented ranges, not a statistical interval."
        ),
        raw_path=snapshot.relative_path,
        raw_sha256=snapshot.sha256,
    )
    note = f"{first['muname']} (map unit {first['mukey']}, {survey})"
    profile = SoilProfile(
        id=f"soil_{site_id}_{source_id}",
        site_id=site_id,
        available_water_capacity_mm_per_m=ParamValue(
            value=_round(awc),
            unit="mm/m",
            reference=CITATION if awc is not None else None,
            region_relevance=note,
            uncertainty=(
                f"SSURGO low-high range {_round(low)}-{_round(high)} mm/m (awc_l/awc_h); "
                f"components with data cover {used_pct:.0f}% of the map unit"
            ),
        ),
        root_zone_depth_m=ParamValue(
            value=None,
            unit="m",
            reference=None,
            uncertainty="Crop-dependent: set from the crop catalog (M4). Soil data does not define root depth.",
        ),
        texture=surface["texdesc"],
        source_ids=[source_id],
    )
    return SoilResult(
        profile=profile,
        source=source,
        awc_low_mm_per_m=_round(low),
        awc_high_mm_per_m=_round(high),
        details={
            "depth_m": depth_m,
            "map_unit": {"mukey": first["mukey"], "name": first["muname"], "area": survey},
            "components": per_comp,
            "component_pct_total": total_pct,
            "component_pct_used": used_pct,
            "dominant_horizons": [
                {k: h[k] for k in ("hzname", "hzdept_r", "hzdepb_r", "awc_l", "awc_r", "awc_h", "texdesc")}
                for h in comps[dominant["cokey"]]
            ],
        },
    )


def _f(v: str | None) -> float | None:
    return None if v is None or v == "" else float(v)


def _weighted(comps: list[dict[str, Any]], key: str) -> float | None:
    total = sum(c["pct"] for c in comps)
    return None if total == 0 else sum(c[key] * c["pct"] for c in comps) / total


def _round(v: float | None) -> float | None:
    return None if v is None else round(v, 1)
