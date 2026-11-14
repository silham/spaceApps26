import json

from ftm.config import REPO_ROOT
from ftm.contracts.models import ALL_CONTRACTS, RANGE_LABEL, Result
from ftm.fixtures import load_demo


def test_demo_fixtures_validate_and_are_flagged_demo() -> None:
    demo = load_demo()
    records = [*demo.sites, *demo.sources, *demo.strategies, *demo.simulation_runs, *demo.results]
    assert records
    assert all(r.is_demo for r in records), "every fixture record must carry is_demo=true"


def test_demo_results_reference_known_entities() -> None:
    demo = load_demo()
    strategy_ids = {s.id for s in demo.strategies}
    source_ids = {s.id for s in demo.sources}
    for r in demo.results:
        assert r.strategy_id in strategy_ids
        assert set(r.source_ids) <= source_ids, "results must cite sources that exist"


def test_range_label_is_not_a_prediction_interval() -> None:
    assert "prediction" not in RANGE_LABEL.lower()
    assert "confidence" not in RANGE_LABEL.lower()
    assert Result.model_fields["range_label"].default == RANGE_LABEL


def test_generated_schemas_are_up_to_date() -> None:
    out = REPO_ROOT / "contracts" / "schemas"
    for model in ALL_CONTRACTS:
        path = out / f"{model.__name__}.json"
        assert path.exists(), f"missing {path.name}; run `make contracts`"
        assert json.loads(path.read_text(encoding="utf-8")) == model.model_json_schema(mode="serialization"), (
            f"{path.name} is stale; run `make contracts`"
        )
