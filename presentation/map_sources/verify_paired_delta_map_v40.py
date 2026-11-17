#!/usr/bin/env python3
"""Validate the rebuilt paired B1 map and its audit using only the standard library."""
from __future__ import annotations
import json
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRESENTATION = HERE.parent
ASSETS = PRESENTATION / "assets_v40"
SVG = ASSETS / "paired_delta_programming_art_b1.svg"
PNG = ASSETS / "paired_delta_programming_art_b1_preview.png"
AUDIT = HERE / "paired_delta_map_audit_v40.json"

EXPECTED = {
    "programming": {"lt_minus2": 6, "minus2_to_zero": 207, "zero": 971,
                    "zero_to_2": 709, "gt2": 353, "low": 1020, "nocover": 64},
    "art": {"lt_minus2": 864, "minus2_to_zero": 549, "zero": 597,
            "zero_to_2": 229, "gt2": 7, "low": 1020, "nocover": 64},
}

def main() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    if audit.get("version") != "v40" or audit.get("feature_count") != 3330:
        raise ValueError("Unexpected audit version or BlocksNet feature count")
    for direction, expected in EXPECTED.items():
        actual = audit["directions"][direction]["class_counts"]
        if actual != expected:
            raise ValueError(f"{direction}: class counts differ: {actual}")
        if sum(actual.values()) != 3330:
            raise ValueError(f"{direction}: classes do not sum to 3,330")
        if audit["directions"][direction]["origin_totals"] != {
            "n_origins": 30609, "n_valid": 30222, "n_uncovered": 387
        }:
            raise ValueError(f"{direction}: origin accounting differs")
    if not SVG.is_file() or SVG.stat().st_size < 100_000:
        raise ValueError("SVG is missing or unexpectedly small")
    if not PNG.is_file() or PNG.stat().st_size < 50_000:
        raise ValueError("PNG preview is missing or unexpectedly small")
    root = ET.parse(SVG).getroot()
    text = " ".join((node.text or "") for node in root.iter() if node.tag.endswith("text"))
    for label in ("Программирование", "Изобразительное искусство",
                  "Меньше −2", "От −2 до <0", "Больше 0 до 2",
                  "Больше 2", "1–2 валидные точки", "Нет сетевого покрытия"):
        if label not in text:
            raise ValueError(f"SVG legend/title is missing: {label}")
    if "Нет результата" in text:
        raise ValueError("SVG contains an empty 'Нет результата' legend class")
    if audit["directions"]["programming"]["delta_sign"] != {
        "negative": 213, "zero": 971, "positive": 1062
    }:
        raise ValueError("Programming delta-sign counts differ")
    if audit["directions"]["art"]["delta_sign"] != {
        "negative": 1413, "zero": 597, "positive": 236
    }:
        raise ValueError("Art delta-sign counts differ")
    print(json.dumps({
        "status": "passed",
        "svg_bytes": SVG.stat().st_size,
        "png_bytes": PNG.stat().st_size,
        "svg_text_nodes": sum(1 for node in root.iter() if node.tag.endswith("text")),
        "legend_empty_class_absent": True,
        "feature_count": 3330,
        "class_counts": audit["directions"],
        "geometry_inventory": audit.get("geometry_inventory", {}),
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
