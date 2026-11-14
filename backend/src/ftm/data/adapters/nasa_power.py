"""NASA POWER daily point API adapter. Owner: M3.

Docs: https://power.larc.nasa.gov/docs/services/api/temporal/daily/
Confirm parameter names, units, community and fill value in the docs before use.
"""

from datetime import date

from ftm.data.raw_cache import RawSnapshot


def fetch_daily(latitude: float, longitude: float, start: date, end: date, parameters: list[str]) -> RawSnapshot:
    """Download daily POWER data and store it as an immutable raw snapshot.

    TODO(M3): call the API with httpx, save the raw JSON via ``save_raw``, then register a Source row
    with provider, product/version, units, resolution, coverage, retrieval date, URL and license.
    """
    raise NotImplementedError("M3: implement NASA POWER adapter")
