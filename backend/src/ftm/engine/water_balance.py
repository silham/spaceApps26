"""Daily root-zone water balance (FAO-56). Owner: M4.

Use pyfao56 (https://github.com/kthorp/pyfao56) where it fits rather than re-implementing FAO-56.
Accounting: storage change = infiltrated rain + irrigation - actual ET - drainage, with runoff handled
separately and storage bounded to [0, TAW]. Hargreaves fallback: Ra in MJ m-2 day-1 must be converted to
mm day-1 equivalent evaporation (x 0.408, FAO-56 eq. 20).

Required tests (tests/engine/): mass balance, bounds, units, carry-over, determinism.
"""
