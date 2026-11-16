#!/usr/bin/env python3
"""Verify v36 slide assets and weighted B1 accessibility shares from source CSVs.

Uses only the Python standard library. No routing or map generation is performed.
Run from any directory:
    python presentation/map_sources/verify_presentation_v36.py
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRESENTATION = HERE.parent
HTML = PRESENTATION / "age_accessibility_b1_v36.html"
AUDIT = HERE / "coverage_audit_v36.json"

CSV_FILES = {
    "programming": HERE / "b1_81.csv",
    "art": HERE / "b1_38.csv",
}
EXPECTED_ACCESS = {
    "programming": (46.4132, 63.2486),
    "art": (85.4047, 80.9841),
}
EXPECTED_ROWS = 3330
EXPECTED_TOTALS = (30609, 30222, 387)
REQUIRED_MAPS = {
    11: "directions_chart_b1.svg",
    12: "programming_states_b1.svg",
    13: "art_states_b1.svg",
    15: "programming_delta_b1.svg",
    19: "network_coverage_b1.svg",
}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def summarize(path: Path) -> dict:
    rows = read_rows(path)
    if len(rows) != EXPECTED_ROWS:
        raise ValueError(f"{path.name}: expected {EXPECTED_ROWS} rows, got {len(rows)}")
    ids = [r["blocksnet_block_id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path.name}: duplicate block IDs")

    state = Counter()
    delta = Counter()
    coverage = Counter()
    n_origins = n_valid = n_uncovered = 0
    weighted7 = weighted13 = 0.0

    for row in rows:
        origins = int(row["n_origins"])
        valid = int(row["n_valid"])
        uncovered = int(row["n_uncovered"])
        if origins != valid + uncovered:
            raise ValueError(f"{path.name}: origin accounting mismatch at {row['blocksnet_block_id']}")
        n_origins += origins
        n_valid += valid
        n_uncovered += uncovered

        if valid:
            both = float(row["both_pct"])
            only7 = float(row["only_7_pct"])
            only13 = float(row["only_13_pct"])
            weighted7 += (both + only7) * valid / 100
            weighted13 += (both + only13) * valid / 100

        if origins == 0:
            coverage["noresult"] += 1
        elif uncovered == 0:
            coverage["full"] += 1
        elif uncovered == origins:
            coverage["none"] += 1
        else:
            coverage["partial"] += 1

        if valid == 0:
            state["no_network_covered"] += 1
        elif valid < 3:
            state["low"] += 1
        else:
            values = [float(row[k]) for k in
                      ("both_pct", "only_7_pct", "only_13_pct", "neither_pct")]
            maximum = max(values)
            winners = [i for i, value in enumerate(values) if abs(value - maximum) < 1e-7]
            key = "tie" if len(winners) > 1 else (
                "both", "only7", "only13", "neither"
            )[winners[0]]
            state[key] += 1

            difference = float(row["median_delta_N"])
            if difference < -2:
                delta["lt_minus2"] += 1
            elif difference < 0:
                delta["minus2_to_zero"] += 1
            elif difference == 0:
                delta["zero"] += 1
            elif difference <= 2:
                delta["zero_to_2"] += 1
            else:
                delta["gt2"] += 1

    if (n_origins, n_valid, n_uncovered) != EXPECTED_TOTALS:
        raise ValueError(f"{path.name}: unexpected totals {(n_origins, n_valid, n_uncovered)}")
    return {
        "rows": len(rows),
        "n_origins": n_origins,
        "n_valid": n_valid,
        "n_uncovered": n_uncovered,
        "weighted_access_pct": {
            "age7": round(weighted7 / n_valid * 100, 4),
            "age13": round(weighted13 / n_valid * 100, 4),
        },
        "state_counts": dict(state),
        "delta_bins": dict(delta),
        "delta_sign": {
            "negative": delta["lt_minus2"] + delta["minus2_to_zero"],
            "zero": delta["zero"],
            "positive": delta["zero_to_2"] + delta["gt2"],
        },
        "coverage_classes": {
            "no_uncovered_origins": coverage["full"],
            "partial": coverage["partial"],
            "all_origins_uncovered": coverage["none"],
            "no_origins": coverage["noresult"],
        },
    }


def load_slides() -> tuple[str, list[dict]]:
    source = HTML.read_text(encoding="utf-8")
    match = re.search(r"const slides=(\[.*?\]);\s*let current=", source, re.S)
    if not match:
        raise ValueError("Cannot locate serialized slides in HTML")
    return source, json.loads(match.group(1))


def verify_slides() -> dict:
    source, slides = load_slides()
    if len(slides) != 20:
        raise ValueError(f"Expected 20 slides, got {len(slides)}")
    for number, slide in enumerate(slides, 1):
        if not slide.get("title") or not slide.get("note") or not str(slide.get("body", "")).strip():
            raise ValueError(f"Slide {number}: missing title, note or body")
        for src in re.findall(r'<img[^>]+src="([^"]+)"', slide.get("body", "")):
            if not (PRESENTATION / src).is_file():
                raise ValueError(f"Slide {number}: missing image {src}")
    for number, filename in REQUIRED_MAPS.items():
        body = slides[number - 1]["body"]
        if filename not in body or not re.search(r'<img[^>]+alt="[^"]+"', body):
            raise ValueError(f"Slide {number}: missing required map or alt text")
        if not (PRESENTATION / "assets_v35" / filename).is_file():
            raise ValueError(f"Missing required map asset: {filename}")
    if "assets_v35/art_delta_b1.svg" not in source or "current!==12" not in source:
        raise ValueError("Slide 13 art-delta toggle is missing")
    return {"slides": len(slides), "required_map_slides": list(REQUIRED_MAPS)}


def main() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    report = {"presentation": verify_slides(), "directions": {}}
    for name, path in CSV_FILES.items():
        actual = summarize(path)
        expected = audit["directions"][name]
        for key in ("rows", "n_origins", "n_valid", "n_uncovered",
                    "state_counts", "delta_bins", "delta_sign"):
            if actual[key] != expected[key]:
                raise ValueError(f"{name}: manifest mismatch in {key}")
        for age in ("age7", "age13"):
            value = actual["weighted_access_pct"][age]
            target = EXPECTED_ACCESS[name][0 if age == "age7" else 1]
            if abs(value - target) > 0.01:
                raise ValueError(f"{name} {age}: {value} does not match B1 control {target}")
            if abs(value - expected["weighted_access_pct"][age]) > 0.0001:
                raise ValueError(f"{name} {age}: corrected manifest does not match CSV")
        if actual["coverage_classes"] != expected["coverage_classes"]:
            raise ValueError(f"{name}: manifest mismatch in coverage_classes")
        report["directions"][name] = actual

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
