"""Find real cropped fields near the candidate regions, as evidence for the site decision (D3).

Usage (from backend/, Earth Engine signed in, EE_PROJECT in .env):
  uv run python scripts/find_candidate_fields.py

Writes results/site_search/: candidates.json, candidates.geojson and one photo per candidate.
This produces a *shortlist with evidence*; choosing the site stays a team decision (docs/decisions.md D3).

Method
- Kansas: USDA NASS Cropland Data Layer (CDL, 30 m). A centre qualifies if, in EVERY year 2018-2024, the
  ~510 m square around it is a single cropped class. Any 232 m MODIS pixel containing the centre then lies
  inside one field, so season detection sees only that field. The outline is the connected patch with the
  same crop as the centre in every year (opened by 2 px to drop road edges).
- Sri Lanka: no field-level crop map exists, so ESA WorldCover 2021 (10 m) is used: >= 90 % cropland in a
  ~250 m block (one MODIS pixel). These are blocks of many small plots, not single fields.
- Both: MODIS MOD13Q1 NDVI yearly peak / amplitude (QA good+marginal) as an independent cropping signal.
"""

from __future__ import annotations

import json
import math
import urllib.request
from pathlib import Path
from typing import Any

import ee

from ftm.config import get_settings

YEARS = list(range(2018, 2025))
MODIS_M = 231.656
CDL_NAMES = {1: "Corn", 4: "Sorghum", 5: "Soybeans", 24: "Winter wheat", 36: "Alfalfa", 61: "Fallow/idle cropland"}


def _crop_mask(c: ee.Image) -> ee.Image:
    # CDL crop classes: 1-61 field crops (61 = fallow, part of dryland rotations), 66-77 tree crops,
    # 204-254 double crops. Excludes pasture/grass (62-65, 176), developed (121-124), water, forest.
    return c.gte(1).And(c.lte(61)).Or(c.gte(66).And(c.lte(77))).Or(c.gte(204).And(c.lte(254)))


def _km(lon: float, lat: float, lon0: float, lat0: float) -> float:
    return math.hypot((lon - lon0) * 111.32 * math.cos(math.radians(lat0)), (lat - lat0) * 110.57)


def _distinct(points: list[tuple[float, float, float]], min_km: float, n: int) -> list[tuple[float, float, float]]:
    out: list[tuple[float, float, float]] = []
    for d, lon, lat in points:
        if all(_km(lon, lat, o[1], o[2]) > min_km for o in out):
            out.append((d, lon, lat))
        if len(out) == n:
            break
    return out


def _ndvi_stats(p: ee.Geometry) -> dict[str, Any]:
    ts = (
        ee.ImageCollection("MODIS/061/MOD13Q1")
        .filterDate("2018-01-01", "2025-01-01")
        .select(["NDVI", "SummaryQA"])
        .getRegion(p, MODIS_M)
        .getInfo()
    )
    hdr = ts[0]
    i_n, i_q, i_t = hdr.index("NDVI"), hdr.index("SummaryQA"), hdr.index("id")
    good = [(r[i_t][:4], r[i_n] / 1e4) for r in ts[1:] if r[i_n] is not None and r[i_q] in (0, 1)]
    years: dict[str, list[float]] = {}
    for y, v in good:
        years.setdefault(y, []).append(v)
    return {
        "ndvi_peak": {y: round(max(v), 2) for y, v in sorted(years.items()) if len(v) >= 6},
        "ndvi_amplitude": {y: round(max(v) - min(v), 2) for y, v in sorted(years.items()) if len(v) >= 6},
        "modis_qa_pass_share": round(len(good) / max(1, len(ts) - 1), 2),
    }


def _photo(rgb: ee.Image, p: ee.Geometry, outline: ee.Geometry | None, path: Path) -> None:
    img = rgb
    if outline is not None:
        img = img.blend(
            ee.Image().byte().paint(ee.FeatureCollection([ee.Feature(outline)]), 1, 3).visualize(palette=["ffd400"])
        )
    pixel = ee.Image().byte().paint(ee.FeatureCollection([ee.Feature(p.buffer(MODIS_M / 2).bounds())]), 1, 2)
    img = img.blend(pixel.visualize(palette=["ff3b3b"]))
    url = img.getThumbURL({"region": p.buffer(1300).bounds(), "dimensions": 640, "format": "png"})
    urllib.request.urlretrieve(url, path)


def kansas(
    out: Path, lon0: float = -100.87, lat0: float = 37.97, radius_m: int = 20000, n: int = 5
) -> list[dict[str, Any]]:
    region = ee.Geometry.Point([lon0, lat0]).buffer(radius_m).bounds()
    kernel = ee.Kernel.square(8, "pixels")  # 8 x 30 m each way -> ~510 m square
    pure = None
    for y in YEARS:
        c = ee.Image(f"USDA/NASS/CDL/{y}").select("cropland").clip(region)
        mm = c.reduceNeighborhood(ee.Reducer.minMax(), kernel)
        ok = mm.select(0).eq(mm.select(1)).And(_crop_mask(c).reduceNeighborhood(ee.Reducer.min(), kernel).eq(1))
        pure = ok if pure is None else pure.And(ok)
    rows = (
        pure.selfMask()
        .rename("ok")
        .addBands(ee.Image.pixelLonLat())
        .sample(region=region, scale=30, numPixels=20000, seed=1, tileScale=16)
        .limit(5000)
        .getInfo()["features"]
    )
    pts = sorted(
        (
            _km(f["properties"]["longitude"], f["properties"]["latitude"], lon0, lat0),
            f["properties"]["longitude"],
            f["properties"]["latitude"],
        )
        for f in rows
    )
    naip = ee.ImageCollection("USDA/NAIP/DOQQ").filterDate("2019-01-01", "2025-01-01").sort("system:time_start", False)
    results = []
    for i, (dist, lon, lat) in enumerate(_distinct(pts, 0.8, n), 1):
        p = ee.Geometry.Point([lon, lat])
        box = p.buffer(1500).bounds()
        history, same = {}, None
        for y in YEARS:
            cy = ee.Image(f"USDA/NASS/CDL/{y}").select("cropland").clip(box)
            v = cy.sample(p, 30).first().get("cropland").getInfo()
            history[y] = CDL_NAMES.get(v, f"CDL class {v}")
            same = cy.eq(v) if same is None else same.And(cy.eq(v))
        opened = same.focalMin(2, "circle", "pixels").focalMax(2, "circle", "pixels").selfMask()
        comps = opened.connectedComponents(ee.Kernel.plus(1), 1024).select("labels")
        lab = comps.reduceRegion(ee.Reducer.first(), p, 30).get("labels")
        field = (
            comps.eq(ee.Number(lab))
            .selfMask()
            .reduceToVectors(geometry=box, scale=30, geometryType="polygon", maxPixels=1e8)
            .geometry()
            .dissolve(10)
        )
        local = naip.filterBounds(p)
        photo = out / f"kansas_field_{i}.png"
        _photo(local.mosaic().select(["R", "G", "B"]).visualize(min=0, max=255), p, field, photo)
        results.append(
            {
                "id": f"ks-field-{i}",
                "region": "Western Kansas, USA",
                "kind": "single field",
                "lon": round(lon, 5),
                "lat": round(lat, 5),
                "km_from_original_point": round(dist, 1),
                "area_ha_approx": round(field.area(1).divide(1e4).getInfo(), 1),
                "crop_history_cdl": history,
                **_ndvi_stats(p),
                "photo": photo.name,
                "photo_source": "USDA NAIP (~1 m), newest 2019-2024 image",
                "photo_date": ee.Date(local.first().get("system:time_start")).format("YYYY-MM-dd").getInfo(),
                "boundary": field.getInfo(),
            }
        )
        print(
            f"  {results[-1]['id']}: {dist:.1f} km, {results[-1]['area_ha_approx']} ha, {' > '.join(history.values())}"
        )
    return results


def sri_lanka(
    out: Path, lon0: float = 80.40, lat0: float = 8.31, radius_m: int = 50000, n: int = 5
) -> list[dict[str, Any]]:
    region = ee.Geometry.Point([lon0, lat0]).buffer(radius_m).bounds()
    crop = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map").clip(region).eq(40)
    block = crop.reduceNeighborhood(ee.Reducer.mean(), ee.Kernel.square(12, "pixels")).gte(0.9)  # ~250 m, >= 90 %
    rows = (
        block.selfMask()
        .rename("ok")
        .addBands(ee.Image.pixelLonLat())
        .sample(region=region, scale=50, numPixels=20000, seed=1, tileScale=16)
        .limit(5000)
        .getInfo()["features"]
    )
    pts = sorted(
        (
            _km(f["properties"]["longitude"], f["properties"]["latitude"], lon0, lat0),
            f["properties"]["longitude"],
            f["properties"]["latitude"],
        )
        for f in rows
    )
    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate("2024-01-01", "2024-04-30")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 15))
    )
    results = []
    for i, (dist, lon, lat) in enumerate(_distinct(pts, 1.5, n), 1):
        p = ee.Geometry.Point([lon, lat])
        outline = p.buffer(125).bounds()
        photo = out / f"srilanka_block_{i}.png"
        _photo(s2.filterBounds(p).median().select(["B4", "B3", "B2"]).visualize(min=0, max=2500), p, outline, photo)
        results.append(
            {
                "id": f"sl-block-{i}",
                "region": "Sri Lanka dry zone",
                "kind": "block of many small plots",
                "lon": round(lon, 5),
                "lat": round(lat, 5),
                "km_from_original_point": round(dist, 1),
                "area_ha_approx": 6.3,
                **_ndvi_stats(p),
                "photo": photo.name,
                "photo_source": "Copernicus Sentinel-2 L2A median, Jan-Apr 2024 (10 m)",
                "boundary": outline.getInfo(),
            }
        )
        print(f"  {results[-1]['id']}: {dist:.1f} km, NDVI amplitude {results[-1]['ndvi_amplitude']}")
    return results


def main() -> None:
    project = get_settings().ee_project
    if not project:
        raise SystemExit("EE_PROJECT is not set in .env")
    ee.Initialize(project=project)
    out = get_settings().results_dir / "site_search"
    out.mkdir(parents=True, exist_ok=True)
    print("Kansas (CDL single fields):")
    ks = kansas(out)
    print("Sri Lanka (WorldCover cropland blocks):")
    sl = sri_lanka(out)
    allc = ks + sl
    (out / "candidates.json").write_text(json.dumps(allc, indent=1), encoding="utf-8")
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": c["boundary"],
                "properties": {k: v for k, v in c.items() if k != "boundary"},
            }
            for c in allc
        ],
    }
    (out / "candidates.geojson").write_text(json.dumps(fc), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
