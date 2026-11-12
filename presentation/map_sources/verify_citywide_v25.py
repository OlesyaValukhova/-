#!/usr/bin/env python3
"""Audit common origins and citywide means used on slide 8.

Usage: python verify_citywide_v25.py b1-by-origin.csv b3-by-origin.csv
The CSVs are available under results/blocksnet-b1-citywide-20261111 and
results/blocksnet-b3-citywide-20261111, each in full_observable/.
"""
import sys
import pandas as pd

b1 = pd.read_csv(sys.argv[1])
b3 = pd.read_csv(sys.argv[2])
for name, data in (("B1", b1), ("B3", b3)):
    assert data.origin_id.is_unique, f"{name}: duplicate origin IDs"
joined = b1.merge(b3, on="origin_id", suffixes=("_b1", "_b3"), how="outer", indicator=True, validate="one_to_one")
assert len(joined) == 30611 and joined["_merge"].eq("both").all()
assert joined.network_covered_b1.eq(joined.network_covered_b3).all()
covered = joined[joined.network_covered_b1]
assert len(covered) == 30224 and len(joined) - len(covered) == 387
for age in (7, 13):
    base = f"age_{age}_N_venue_proxy_within_30min"
    for scenario in ("b1", "b3"):
        vals = covered[f"{base}_{scenario}"]
        assert vals.notna().all()
        print(f"{age=}, {scenario=}, mean={vals.mean():.6f}, zero_pct={vals.eq(0).mean()*100:.6f}")
print("Identical origins and coverage; 387 uncovered excluded.")
