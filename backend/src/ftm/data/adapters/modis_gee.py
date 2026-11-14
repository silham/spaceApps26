"""MODIS MOD13Q1 (061) vegetation index extraction via Google Earth Engine. Owner: M3.

Catalog: https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1
Apply the scale factor and QA (SummaryQA / DetailedQA) before handing the series to M5.
Requires the ``earthengine-api`` package and credentials (not committed).
"""


def extract_vi_series(site_id: str) -> None:
    raise NotImplementedError("M3: implement MOD13Q1 extraction")
