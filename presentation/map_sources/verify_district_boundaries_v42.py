#!/usr/bin/env python3
"""Validate the committed OSM district snapshot without network access."""
from __future__ import annotations

import base64
import gzip
import json
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
RAW = HERE / "spb_districts_overpass_raw_v42.json"
DISTRICTS = HERE / "spb_district_boundaries_v42.geojson"
AUDIT = HERE / "district_boundaries_audit_v42.json"
BLOCKS = HERE / "blocks_v22.json.gz.b64"

EXPECTED = {
    1114193: "Адмиралтейский район",
    1114252: "Василеостровский район",
    1114354: "Выборгский район",
    1114806: "Калининский район",
    1114809: "Кировский район",
    337424: "Колпинский район",
    1114895: "Красногвардейский район",
    363103: "Красносельский район",
    1115082: "Кронштадтский район",
    1115366: "Курортный район",
    338636: "Московский район",
    368287: "Невский район",
    1114905: "Петроградский район",
    367375: "Петродворцовый район",
    1115367: "Приморский район",
    338635: "Пушкинский район",
    369514: "Фрунзенский район",
    1114902: "Центральный район",
}


def main() -> None:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    data = json.loads(DISTRICTS.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    if data.get("type") != "FeatureCollection":
        raise ValueError("District snapshot is not a GeoJSON FeatureCollection")
    if data.get("crs", {}).get("properties", {}).get("name") != "EPSG:32636":
        raise ValueError("District snapshot CRS must be EPSG:32636")

    features = data.get("features", [])
    if len(features) != 18:
        raise ValueError(f"Expected 18 district features, got {len(features)}")
    ids = {int(f["properties"]["osm_id"]) for f in features}
    if ids != set(EXPECTED):
        raise ValueError("District relation IDs do not match the expected 18 districts")

    geometries = []
    for feature in features:
        props = feature["properties"]
        osm_id = int(props["osm_id"])
        if props.get("name") != EXPECTED[osm_id]:
            raise ValueError(f"Unexpected name for relation {osm_id}: {props.get('name')!r}")
        if props.get("admin_level") != "5" or props.get("boundary") != "administrative":
            raise ValueError(f"Unexpected administrative tags for relation {osm_id}")
        if feature["geometry"]["type"] != "MultiPolygon":
            raise ValueError(f"Expected MultiPolygon for relation {osm_id}")
        geom = shape(feature["geometry"])
        if geom.is_empty or not geom.is_valid or geom.area <= 1_000_000:
            raise ValueError(f"Invalid or implausible district geometry for relation {osm_id}")
        geometries.append(geom)

    raw_relations = {
        int(element["id"]): element
        for element in raw.get("elements", [])
        if element.get("type") == "relation" and int(element["id"]) in EXPECTED
    }
    if set(raw_relations) != set(EXPECTED):
        raise ValueError("Raw Overpass response does not contain all 18 target relations")
    nested_subarea_count = sum(
        1
        for element in raw_relations.values()
        for member in element.get("members", [])
        if member.get("type") == "relation" and member.get("role") == "subarea"
    )
    expected_nested = audit["conversion_preprocessing"]["removed_nested_subarea_relation_members"]
    if nested_subarea_count != expected_nested:
        raise ValueError(
            f"Raw nested subarea count {nested_subarea_count} != audit count {expected_nested}"
        )

    block_raw = base64.b64decode(BLOCKS.read_text(encoding="ascii").strip(), validate=True)
    blocks = json.loads(gzip.decompress(block_raw).decode("utf-8"))
    if blocks.get("crs", {}).get("properties", {}).get("name") != "urn:ogc:def:crs:EPSG::32636":
        raise ValueError("BlocksNet geometry CRS changed")
    block_features = blocks.get("features", [])
    if len(block_features) != 3330:
        raise ValueError(f"Expected 3,330 BlocksNet polygons, got {len(block_features)}")
    block_union = unary_union([shape(f["geometry"]) for f in block_features])
    district_union = unary_union(geometries)
    coverage_ratio = district_union.intersection(block_union).area / block_union.area
    recorded = audit["blocksnet_polygon_area_overlap_ratio"]
    if abs(coverage_ratio - recorded) > 1e-5:
        raise ValueError(
            f"Recomputed BlocksNet area coverage {coverage_ratio:.6f} != audit {recorded:.6f}"
        )
    if coverage_ratio < 0.80:
        raise ValueError(f"District context covers only {coverage_ratio:.1%} of BlocksNet polygon area")
    if audit["license"] != "ODbL 1.0; attribution: © OpenStreetMap contributors":
        raise ValueError("ODbL attribution is missing")
    if audit["feature_count"] != 18 or not audit["validation"]["all_geometries_valid"]:
        raise ValueError("District audit does not confirm all 18 valid geometries")

    print(json.dumps({
        "status": "passed",
        "districts": len(features),
        "relation_ids": sorted(ids),
        "crs": "EPSG:32636",
        "geometry_type": "MultiPolygon",
        "raw_overpass_bytes": RAW.stat().st_size,
        "nested_subarea_members_preserved_in_raw": nested_subarea_count,
        "blocksnet_polygons": len(block_features),
        "blocksnet_area_coverage": round(coverage_ratio, 6),
        "license": audit["license"],
        "role": audit["role"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
