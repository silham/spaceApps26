"""Paired historical-weather ensemble. Owner: M4.

Season-aligned block bootstrap + actual consecutive-year replay; identical weather and paired parameter
draws across strategies; seeded via numpy.random.default_rng(seed). Report p10/p50/p90 as a
'central 80% simulation range', not a prediction interval.
"""
