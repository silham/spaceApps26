"""Helpers to read PostGIS geometries back as GeoJSON dicts."""

import json
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session


def as_geojson(session: Session, geom: Any) -> dict[str, Any] | None:
    if geom is None:
        return None
    text = session.scalar(func.ST_AsGeoJSON(geom))
    return json.loads(text) if text else None
