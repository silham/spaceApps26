"""Load and validate the committed DEMO fixtures (data/fixtures/demo.json)."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ftm.config import get_settings
from ftm.contracts.models import Result, SimulationRun, Site, Source, Strategy


class DemoBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    comment: str = Field(alias="_comment")
    sites: list[Site]
    sources: list[Source]
    strategies: list[Strategy]
    simulation_runs: list[SimulationRun]
    results: list[Result]


def load_demo(path: Path | None = None) -> DemoBundle:
    path = path or get_settings().fixtures_dir / "demo.json"
    return DemoBundle.model_validate(json.loads(path.read_text()))
