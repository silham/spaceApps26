"""Register a loaded site's strategies and the literature sources results cite. Idempotent.

    uv run python scripts/seed_site.py --site-id ks-field-2

Needs the site's weather and soil in the DB (scripts/load_site.py). Strategies come from
``ftm.engine.scenarios`` (D5) with planting dates from the site's own weather record; each is stored with
its feasibility (hard constraints, ``ftm.engine.rotation.check_feasibility``) so the API can show the
reasons before any run. FAO-56 and TR-55 are registered as LITERATURE sources so every source ID a
result carries resolves (rule 2).
"""

from __future__ import annotations

import argparse

from sqlalchemy.orm import Session

from ftm.data.engine_inputs import build_site_scenario, load_site_engine_inputs
from ftm.data.store import upsert_source
from ftm.db.models import StrategyRow
from ftm.db.session import get_engine
from ftm.engine.params import LITERATURE_SOURCES
from ftm.engine.rotation import check_feasibility
from ftm.engine.scenarios import SCENARIO_HORIZON


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-id", required=True)
    args = ap.parse_args()

    with Session(get_engine()) as s, s.begin():
        for src in LITERATURE_SOURCES:
            upsert_source(s, src)
        inputs = load_site_engine_inputs(s, args.site_id)
        scen = build_site_scenario(inputs)
        for st in scen.strategies:
            feas = check_feasibility(st, scen.crops, horizon=SCENARIO_HORIZON, soil=inputs.soil)
            row = st.model_copy(update={"feasibility": feas})
            s.merge(StrategyRow(**row.model_dump(mode="json")))
            print(f"{st.id}: {'feasible' if feas.feasible else 'NOT feasible: ' + '; '.join(feas.reasons)}")
    n_lit = len(LITERATURE_SOURCES)
    print(f"Seeded {len(scen.strategies)} strategies for {args.site_id} and {n_lit} literature sources")


if __name__ == "__main__":
    main()
