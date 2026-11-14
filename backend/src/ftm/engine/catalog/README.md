# Crop & soil catalog (owner: M4)

One JSON file per crop, validated against the `CropProfile` contract.
Every parameter needs `value`, `unit`, `reference`, `region_relevance` and `uncertainty`.
Unknown values stay `null`; the claim that depends on them is blocked. Never fill them with a guess.
