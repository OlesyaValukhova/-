#!/usr/bin/env python3
"""Validate B1 joint age-state shares and paired-difference counts for v34."""
from __future__ import annotations
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUMMARY = json.loads((HERE / "joint_states_b1_v34.json").read_text(encoding="utf-8"))
EXPECTED_N = 30222
EXPECTED_BLOCKS = 3330
EXPECTED_DELTA = {
    "programming": {"negative": 213, "zero": 971, "positive": 1062},
    "art": {"negative": 1413, "zero": 597, "positive": 236},
}
COLUMNS = {
    "both": "both_pct",
    "only_7": "only_7_pct",
    "only_13": "only_13_pct",
    "neither": "neither_pct",
}

def read_rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))

def validate(name: str, item: dict):
    rows = read_rows(HERE / Path(item["source"]).name)
    assert len(rows) == EXPECTED_BLOCKS, (name, len(rows))
    n_valid = sum(int(float(row["n_valid"] or 0)) for row in rows)
    assert n_valid == EXPECTED_N, (name, n_valid)

    totals = {key: 0.0 for key in COLUMNS}
    low_n = no_result = tie = 0
    delta = {"negative": 0, "zero": 0, "positive": 0}
    n_delta = 0
    for row in rows:
        n = int(float(row["n_valid"] or 0))
        if n == 0:
            no_result += 1
        elif n < 3:
            low_n += 1
        if n:
            for key, column in COLUMNS.items():
                totals[key] += float(row[column]) * n / 100
        if n >= 3:
            values = [float(row[COLUMNS[k]]) for k in COLUMNS]
            if sum(abs(v - max(values)) < 1e-7 for v in values) > 1:
                tie += 1
            value = float(row["median_delta_N"])
            n_delta += 1
            if value < 0:
                delta["negative"] += 1
            elif value == 0:
                delta["zero"] += 1
            else:
                delta["positive"] += 1

    counts = {key: round(value) for key, value in totals.items()}
    assert counts == item["counts"], (name, counts, item["counts"])
    assert sum(counts.values()) == EXPECTED_N
    shares = {key: round(value / EXPECTED_N * 100, 4) for key, value in totals.items()}
    assert shares == item["shares_pct"], (name, shares, item["shares_pct"])
    assert n_delta == 2246
    assert delta == EXPECTED_DELTA[name], (name, delta)
    assert low_n == item["class_counts"]["low_n_1_2"]
    assert no_result == item["class_counts"]["no_result"]
    assert tie == item["class_counts"]["tie_modal"]
    return {"blocks": len(rows), "n_valid": n_valid, "counts": counts,
            "shares_pct": shares, "low_n_1_2": low_n, "no_result": no_result,
            "tie_modal": tie, "delta": delta}

def main():
    result = {name: validate(name, SUMMARY["directions"][name])
              for name in ("programming", "art")}
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
