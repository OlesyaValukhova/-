#!/usr/bin/env python3
"""Validate the five rebuilt B1 SVG maps in assets_v40."""
from __future__ import annotations
import gzip
import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRESENTATION = HERE.parent
ASSETS = PRESENTATION / "assets_v40"
AUDIT = HERE / "coverage_audit_v40.json"
EXPECTED = {
    "programming_states_b1.svgz": ("Возрастные состояния по кварталам", "Программирование"),
    "art_states_b1.svgz": ("Возрастные состояния по кварталам", "Изобразительное искусство"),
    "programming_delta_b1.svgz": ("Медиана парной разницы N13 − N7", "Программирование"),
    "art_delta_b1.svgz": ("Медиана парной разницы N13 − N7", "Изобразительное искусство"),
    "network_coverage_b1.svgz": ("Сетевое покрытие жилых точек", "Доля непокрытых точек"),
}

def main() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    if audit["geometry"]["feature_count"] != 3330 or audit["geometry"]["crs"] != "EPSG:32636":
        raise ValueError("Unexpected BlocksNet geometry metadata")
    accounting = audit["origin_accounting"]
    if accounting != {
        "input_origins": 30611,
        "network_covered": 30224,
        "network_uncovered": 387,
        "assigned_to_blocks": 30609,
        "unassigned_to_blocks": 2,
        "covered_and_assigned": 30222,
    }:
        raise ValueError(f"Unexpected origin accounting: {accounting}")
    outputs = set(audit["outputs"])
    if outputs != set(EXPECTED):
        raise ValueError(f"Unexpected compressed map outputs: {outputs}")
    expected_pngs = {name.replace(".svgz", ".png") for name in EXPECTED}
    if set(audit.get("png_outputs", [])) != expected_pngs:
        raise ValueError("PNG map inventory differs from SVGZ inventory")
    checked = []
    for filename, required_text in EXPECTED.items():
        path = ASSETS / filename
        if not path.is_file() or path.stat().st_size < 100_000:
            raise ValueError(f"Missing or unexpectedly small SVGZ: {filename}")
        root = ET.fromstring(gzip.decompress(path.read_bytes()))
        png_path = path.with_suffix(".png")
        if not png_path.is_file() or png_path.stat().st_size < 50_000:
            raise ValueError(f"Missing or unexpectedly small PNG: {png_path.name}")
        with png_path.open("rb") as image:
            header = image.read(24)
        width, height = struct.unpack(">II", header[16:24])
        if (width, height) != (2880, 1620):
            raise ValueError(f"{png_path.name}: unexpected dimensions {width}x{height}")
        text = " ".join(node.text or "" for node in root.iter() if node.tag.endswith("text"))
        for term in required_text:
            if term not in text:
                raise ValueError(f"{filename}: missing text {term!r}")
        checked.append({"file": filename, "svgz_bytes": path.stat().st_size, "png_bytes": png_path.stat().st_size, "text_nodes": sum(1 for node in root.iter() if node.tag.endswith("text"))})
    print(json.dumps({"status":"passed","maps":checked,"geometry":audit["geometry"],"origin_accounting":accounting},ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
