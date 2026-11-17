#!/usr/bin/env python3
"""Validate B1 maps with OSM administrative-district context; no GIS recomputation."""
from __future__ import annotations

import gzip
import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRESENTATION = HERE.parent
ASSETS = PRESENTATION / "assets_v42"
DISTRICTS = HERE / "spb_district_boundaries_v42.geojson"
DISTRICT_AUDIT = HERE / "district_boundaries_audit_v42.json"
COVERAGE_AUDIT = HERE / "coverage_audit_v42.json"
PAIRED_AUDIT = HERE / "paired_delta_map_audit_v42.json"

EXPECTED_IDS = {
    1114193, 1114252, 1114354, 1114806, 1114809, 337424,
    1114895, 363103, 1115082, 1115366, 338636, 368287,
    1114905, 367375, 1115367, 338635, 369514, 1114902,
}
MAPS = (
    "programming_states_b1",
    "art_states_b1",
    "programming_delta_b1",
    "art_delta_b1",
    "network_coverage_b1",
    "paired_delta_programming_art_b1",
)


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as image:
        header = image.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path.name}: invalid PNG signature")
    return struct.unpack(">II", header[16:24])


def main() -> None:
    district_audit = json.loads(DISTRICT_AUDIT.read_text(encoding="utf-8"))
    districts = json.loads(DISTRICTS.read_text(encoding="utf-8"))
    if district_audit["feature_count"] != 18 or len(districts["features"]) != 18:
        raise ValueError("Expected 18 district polygons")
    if districts["crs"]["properties"]["name"] != "EPSG:32636":
        raise ValueError("District GeoJSON is not EPSG:32636")
    actual_ids = {int(f["properties"]["osm_id"]) for f in districts["features"]}
    if actual_ids != EXPECTED_IDS or set(district_audit["relation_ids"]) != EXPECTED_IDS:
        raise ValueError("OSM district relation IDs do not match the documented 18 districts")
    if district_audit["license"] != "ODbL 1.0; attribution: © OpenStreetMap contributors":
        raise ValueError("OSM attribution/license is missing or changed")
    if not district_audit["validation"]["all_geometries_valid"]:
        raise ValueError("District geometry validation did not pass")
    if "only" not in district_audit["role"]:
        raise ValueError("District layer role is not documented as contextual only")

    coverage = json.loads(COVERAGE_AUDIT.read_text(encoding="utf-8"))
    paired = json.loads(PAIRED_AUDIT.read_text(encoding="utf-8"))
    if coverage.get("version") != "v42" or paired.get("version") != "v42":
        raise ValueError("Map audits are not v42")
    if coverage["geometry"]["feature_count"] != 3330 or paired["feature_count"] != 3330:
        raise ValueError("BlocksNet feature count changed")
    for audit in (coverage, paired):
        context = audit.get("district_context", {})
        if context.get("feature_count") != 18 or context.get("crs") != "EPSG:32636":
            raise ValueError("Map audit does not include the 18-district context layer")
        if "not an analytical unit" not in context.get("role", ""):
            raise ValueError("Map audit does not state that districts are context only")

    expected_classes = {
        "programming": {
            "both": 975, "only7": 55, "only13": 459, "neither": 749,
            "tie": 8, "low": 1020, "nocover": 64,
        },
        "art": {
            "both": 1818, "only7": 113, "only13": 26, "neither": 283,
            "tie": 6, "low": 1020, "nocover": 64,
        },
    }
    for direction, expected in expected_classes.items():
        actual = coverage["directions"][direction]["state_counts"]
        if actual != expected or sum(actual.values()) != 3330:
            raise ValueError(f"{direction}: modal-state counts changed: {actual}")

    checked = []
    for slug in MAPS:
        svgz = ASSETS / f"{slug}.svgz"
        png = ASSETS / (f"{slug}_preview.png" if slug == "paired_delta_programming_art_b1" else f"{slug}.png")
        if not svgz.is_file() or svgz.stat().st_size < 100_000:
            raise ValueError(f"Missing/undersized SVGZ: {svgz.name}")
        if not png.is_file() or png.stat().st_size < 50_000:
            raise ValueError(f"Missing/undersized PNG: {png.name}")
        if png_size(png) != (2880, 1620):
            raise ValueError(f"Unexpected PNG dimensions: {png.name}")
        root = ET.fromstring(gzip.decompress(svgz.read_bytes()))
        svg_text = " ".join(node.text or "" for node in root.iter() if node.tag.endswith("text"))
        for required in ("OpenStreetMap", "ODbL 1.0", "границы 18 районов"):
            if required not in svg_text:
                raise ValueError(f"{svgz.name}: missing map-context attribution text {required!r}")
        checked.append({
            "map": slug,
            "svgz_bytes": svgz.stat().st_size,
            "png_bytes": png.stat().st_size,
            "dimensions": png_size(png),
            "osm_context": True,
        })

    print(json.dumps({
        "status": "passed",
        "blocksnet_features": 3330,
        "district_features": 18,
        "district_crs": "EPSG:32636",
        "district_layer_role": district_audit["role"],
        "maps": checked,
        "origin_accounting": coverage["origin_accounting"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
