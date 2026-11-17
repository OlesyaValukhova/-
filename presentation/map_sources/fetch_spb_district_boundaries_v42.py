#!/usr/bin/env python3
"""Fetch official-level district boundary relations from OpenStreetMap for map context.

The boundaries are cartographic context only. BlocksNet remains the analytical unit.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import osm2geojson
import requests
from pyproj import Transformer
from shapely.geometry import box, mapping, shape
from shapely.ops import transform, unary_union

HERE = Path(__file__).resolve().parent
RAW_PATH = HERE / "spb_districts_overpass_raw_v42.json"
OUTPUT = HERE / "spb_district_boundaries_v42.geojson"
AUDIT = HERE / "district_boundaries_audit_v42.json"
BLOCK_AUDIT = HERE / "paired_delta_map_audit_v40.json"

# The 18 city districts are listed in the OpenStreetMap Saint Petersburg boundary
# documentation; the wiki page states that source boundary information comes
# from the Saint Petersburg government website.
EXPECTED = {
    1114193: "Адмиралтейский",
    1114252: "Василеостровский",
    1114354: "Выборгский",
    1114806: "Калининский",
    1114809: "Кировский",
    337424: "Колпинский",
    1114895: "Красногвардейский",
    363103: "Красносельский",
    1115082: "Кронштадтский",
    1115366: "Курортный",
    338636: "Московский",
    368287: "Невский",
    1114905: "Петроградский",
    367375: "Петродворцовый",
    1115367: "Приморский",
    338635: "Пушкинский",
    369514: "Фрунзенский",
    1114902: "Центральный",
}
ENDPOINTS = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
)
TARGET_CRS = "EPSG:32636"


def overpass_query() -> str:
    relations = "\n".join(f"  relation({osm_id});" for osm_id in EXPECTED)
    return f"[out:json][timeout:180];\n(\n{relations}\n);\nout body geom;"


def fetch_raw() -> dict:
    query = overpass_query()
    headers = {
        "User-Agent": "IDU-NIR-B1-map-context/1.0 (research cartography; OpenStreetMap attribution)",
        "Accept": "application/json",
    }
    errors = []
    for endpoint in ENDPOINTS:
        for attempt in range(1):
            try:
                response = requests.post(
                    endpoint,
                    data={"data": query},
                    headers=headers,
                    timeout=(15, 90),
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("remark"):
                    raise RuntimeError(payload["remark"])
                RAW_PATH.write_text(
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8",
                )
                return payload
            except Exception as exc:  # noqa: BLE001 - preserve endpoint diagnostics
                errors.append(f"{endpoint} attempt {attempt + 1}: {type(exc).__name__}: {exc}")
                if attempt < 0:
                    time.sleep(2)
    raise RuntimeError("All Overpass endpoints failed:\n" + "\n".join(errors))


def get_tags(properties: dict) -> dict:
    tags = properties.get("tags")
    if isinstance(tags, dict):
        return tags
    # Some converter versions expose OSM tags at the feature-property level.
    return properties


def main() -> None:
    payload = fetch_raw()
    raw_elements = payload.get("elements", [])
    raw_relations = {
        int(element["id"])
        for element in raw_elements
        if element.get("type") == "relation"
    }
    missing_raw = sorted(set(EXPECTED) - raw_relations)
    if missing_raw:
        raise ValueError(f"Overpass response is missing relation IDs: {missing_raw}")

    converted = osm2geojson.json2geojson(payload, raise_on_failure=True)
    transformer = Transformer.from_crs("EPSG:4326", TARGET_CRS, always_xy=True)
    features_by_id = {}

    for feature in converted.get("features", []):
        properties = feature.get("properties", {})
        if properties.get("type") != "relation":
            continue
        osm_id = properties.get("id", properties.get("osm_id"))
        if osm_id is None:
            continue
        osm_id = int(osm_id)
        if osm_id not in EXPECTED:
            continue
        tags = get_tags(properties)
        name = tags.get("name:ru") or tags.get("name")
        admin_level = str(tags.get("admin_level", ""))
        boundary = tags.get("boundary", "")
        if not name or EXPECTED[osm_id].lower() not in name.lower():
            raise ValueError(f"Relation {osm_id}: unexpected/missing Russian name {name!r}")
        if admin_level != "5" or boundary != "administrative":
            raise ValueError(
                f"Relation {osm_id}: expected boundary=administrative, admin_level=5; "
                f"got {boundary!r}/{admin_level!r}"
            )
        geometry = shape(feature["geometry"])
        if geometry.geom_type not in ("Polygon", "MultiPolygon") or geometry.is_empty:
            raise ValueError(f"Relation {osm_id}: expected polygonal geometry, got {geometry.geom_type}")
        if not geometry.is_valid:
            raise ValueError(f"Relation {osm_id}: invalid source geometry: {geometry.is_valid}")
        projected = transform(transformer.transform, geometry)
        if projected.area <= 1_000_000:
            raise ValueError(f"Relation {osm_id}: implausibly small projected area")
        features_by_id[osm_id] = {
            "type": "Feature",
            "geometry": mapping(projected),
            "properties": {
                "osm_id": osm_id,
                "name": name,
                "admin_level": admin_level,
                "boundary": boundary,
                "source_url": f"https://www.openstreetmap.org/relation/{osm_id}",
                "source_license": "Open Database License (ODbL) 1.0",
            },
        }

    missing_converted = sorted(set(EXPECTED) - set(features_by_id))
    if missing_converted:
        raise ValueError(f"GeoJSON conversion is missing relation IDs: {missing_converted}")
    if len(features_by_id) != 18:
        raise ValueError(f"Expected 18 district polygons, got {len(features_by_id)}")

    features = [features_by_id[osm_id] for osm_id in EXPECTED]
    district_union = unary_union([shape(feature["geometry"]) for feature in features])
    block_audit = json.loads(BLOCK_AUDIT.read_text(encoding="utf-8"))
    block_bbox = block_audit["geometry_inventory"]["bbox_epsg32636"]
    block_box = box(block_bbox[0], block_bbox[1], block_bbox[2], block_bbox[3])
    overlap_ratio = district_union.intersection(block_box).area / block_box.area
    if overlap_ratio < 0.50:
        raise ValueError(f"District boundaries cover only {overlap_ratio:.1%} of BlocksNet bbox")

    output = {
        "type": "FeatureCollection",
        "name": "Saint Petersburg administrative districts (OSM context)",
        "crs": {"type": "name", "properties": {"name": TARGET_CRS}},
        "features": features,
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    audit = {
        "version": "v42",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "OpenStreetMap administrative boundary relations; relation IDs documented in OSM Wiki",
        "source_documentation": "https://wiki.openstreetmap.org/wiki/RU:%D0%A1%D0%B0%D0%BD%D0%BA%D1%82-%D0%9Fетербург/%D0%A0%D0%B0%D0%B9%D0%BE%D0%BD%D1%8B",
        "license": "ODbL 1.0; attribution: © OpenStreetMap contributors",
        "crs": TARGET_CRS,
        "feature_count": len(features),
        "relation_ids": sorted(features_by_id),
        "districts": [
            {
                "osm_id": feature["properties"]["osm_id"],
                "name": feature["properties"]["name"],
                "admin_level": feature["properties"]["admin_level"],
                "source_url": feature["properties"]["source_url"],
            }
            for feature in features
        ],
        "geometry_types": sorted({shape(feature["geometry"]).geom_type for feature in features}),
        "blocksnet_bbox_overlap_ratio": round(overlap_ratio, 6),
        "role": "cartographic orientation only; not an analytical unit and not used to aggregate B1 values",
        "validation": {
            "all_18_expected_relations_present": True,
            "all_admin_level_5": True,
            "all_administrative_boundaries": True,
            "all_geometries_valid": True,
            "all_geometries_projected_to_epsg_32636": True,
        },
        "output": OUTPUT.name,
        "output_bytes": OUTPUT.stat().st_size,
    }
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
