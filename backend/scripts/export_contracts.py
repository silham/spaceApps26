"""Export JSON Schema for every contract to contracts/schemas/. Run via `make contracts`.

The frontend generates TypeScript types from contracts/schemas/bundle.json.
"""

import json

from pydantic.json_schema import models_json_schema

from ftm.config import REPO_ROOT
from ftm.contracts.models import ALL_CONTRACTS, SCHEMA_VERSION

OUT = REPO_ROOT / "contracts" / "schemas"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for model in ALL_CONTRACTS:
        schema = model.model_json_schema(mode="serialization")
        # Explicit UTF-8: the default is cp1252 on Windows, which mangles "–" in RANGE_LABEL.
        (OUT / f"{model.__name__}.json").write_text(
            json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    _, bundle = models_json_schema(
        [(m, "serialization") for m in ALL_CONTRACTS],
        title="FarmTimeMachineContracts",
        description=f"Schema version {SCHEMA_VERSION}. Generated - do not edit.",
    )
    # Make every definition reachable from the root so TS generators emit all types.
    bundle["type"] = "object"
    bundle["properties"] = {m.__name__: {"$ref": f"#/$defs/{m.__name__}"} for m in ALL_CONTRACTS}
    (OUT / "bundle.json").write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(ALL_CONTRACTS)} schemas + bundle.json to {OUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
