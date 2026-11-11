"""Build a reproducible ordinary-walking network from a local OSM PBF file.

This is a data-preparation step for Transport Frames, not a routing engine.
It deliberately reads a downloaded PBF and never contacts Overpass.  The
output retains only OSM ways that plausibly permit ordinary walking according
to explicit OSM access tags; it does not represent safety, crossings, child
independent mobility or a verified entrance network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
import osmium
import osmnx as ox
from pyproj import Geod, Transformer


WALK_HIGHWAYS = {
    "footway", "pedestrian", "path", "steps", "living_street", "residential",
    "service", "unclassified", "tertiary", "secondary", "primary",
    "tertiary_link", "secondary_link", "primary_link", "track", "road",
}
WALK_SPEED_M_PER_MIN = 5_000 / 60
GEOD = Geod(ellps="WGS84")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class WalkGraphHandler(osmium.SimpleHandler):
    def __init__(self, target_crs: int, bounds: tuple[float, float, float, float] | None = None):
        super().__init__()
        # A simple directed graph deliberately retains only the shortest OSM
        # segment between a pair of nodes.  Parallel carriageway/footway
        # variants are not needed by the B1 time matrix and keeping their
        # textual tags makes a city graph exceed ordinary laptop memory.
        self.graph = nx.DiGraph(crs=target_crs, walk_speed=WALK_SPEED_M_PER_MIN)
        self.transformer = Transformer.from_crs(4326, target_crs, always_xy=True)
        self.bounds = bounds  # minx, miny, maxx, maxy in target_crs; None means full PBF
        self.excluded = Counter()
        self.accepted_ways = 0
        self.accepted_segments = 0
        self.min_lon = self.min_lat = float("inf")
        self.max_lon = self.max_lat = float("-inf")

    @staticmethod
    def _reason(tags: dict[str, str]) -> str | None:
        highway = tags.get("highway")
        if not highway:
            return "no_highway"
        if highway not in WALK_HIGHWAYS:
            return "excluded_highway"
        if tags.get("foot") in {"no", "private"}:
            return "foot_restriction"
        if tags.get("access") in {"no", "private"} and tags.get("foot") not in {
            "yes", "designated", "permissive",
        }:
            return "access_restriction"
        if tags.get("area") == "yes":
            return "area_not_linear_route"
        return None

    def _node(self, osm_node) -> tuple[int, float, float, float, float]:
        lon, lat = osm_node.location.lon, osm_node.location.lat
        x, y = self.transformer.transform(lon, lat)
        node_id = int(osm_node.ref)
        if node_id not in self.graph:
            self.graph.add_node(node_id, x=x, y=y)
            self.min_lon, self.max_lon = min(self.min_lon, lon), max(self.max_lon, lon)
            self.min_lat, self.max_lat = min(self.min_lat, lat), max(self.max_lat, lat)
        return node_id, lon, lat, x, y

    def _add(self, u: int, v: int, length: float) -> None:
        existing = self.graph.get_edge_data(u, v)
        if existing is None or length < existing["length_meter"]:
            self.graph.add_edge(u, v, length_meter=length,
                                time_min=length / WALK_SPEED_M_PER_MIN)

    def _intersects_bounds(self, x1: float, y1: float, x2: float, y2: float) -> bool:
        if self.bounds is None:
            return True
        minx, miny, maxx, maxy = self.bounds
        # Segment bounding-box filter. A subsequent route whose total length
        # is <= buffer cannot leave the buffered tile; retaining endpoints at
        # the boundary avoids cutting a traversable segment in half.
        return not (max(x1, x2) < minx or min(x1, x2) > maxx or
                    max(y1, y2) < miny or min(y1, y2) > maxy)

    def way(self, way):
        tags = {tag.k: tag.v for tag in way.tags}
        reason = self._reason(tags)
        if reason:
            self.excluded[reason] += 1
            return
        refs = list(way.nodes)
        if len(refs) < 2:
            self.excluded["way_too_short"] += 1
            return
        one_way = tags.get("oneway:foot", "").lower()
        direction = -1 if one_way == "-1" else 1
        bidirectional = one_way not in {"yes", "1", "-1"}
        added = False
        for index, (a, b) in enumerate(zip(refs, refs[1:])):
            try:
                lon1, lat1 = a.location.lon, a.location.lat
                lon2, lat2 = b.location.lon, b.location.lat
            except osmium.InvalidLocationError:
                self.excluded["missing_node_location"] += 1
                continue
            x1, y1 = self.transformer.transform(lon1, lat1)
            x2, y2 = self.transformer.transform(lon2, lat2)
            if not self._intersects_bounds(x1, y1, x2, y2):
                continue
            u, _, _, _, _ = self._node(a)
            v, _, _, _, _ = self._node(b)
            if u == v:
                continue
            _, _, length = GEOD.inv(lon1, lat1, lon2, lat2)
            if not math.isfinite(length) or length <= 0:
                self.excluded["invalid_segment_length"] += 1
                continue
            if direction == 1:
                self._add(u, v, length)
                if bidirectional:
                    self._add(v, u, length)
            else:
                self._add(v, u, length)
            self.accepted_segments += 1
            added = True
        if added:
            self.accepted_ways += 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pbf", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--crs", type=int, default=32636, help="Projected CRS used by Transport Frames")
    p.add_argument("--source-url", default="https://data.bbbike.org/osm/bbbike/SanktPetersburg/SanktPetersburg.osm.pbf")
    args = p.parse_args()
    if not args.pbf.is_file():
        p.error(f"PBF was not found: {args.pbf}")
    if args.output.exists():
        p.error("Output directory must be new, to keep the build auditable")
    args.output.mkdir(parents=True)
    started = datetime.now(timezone.utc)
    handler = WalkGraphHandler(args.crs)
    handler.apply_file(str(args.pbf), locations=True)
    graph = handler.graph
    if not graph:
        raise RuntimeError("No walkable edges were built from the PBF")
    # OSMnx GraphML is used only as its robust, established graph interchange.
    ox.save_graphml(graph, args.output / "walk.graphml", gephi=False)
    xs = [d["x"] for _, d in graph.nodes(data=True)]
    ys = [d["y"] for _, d in graph.nodes(data=True)]
    manifest = {
        "status": "built",
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
        "source": {"kind": "local_prebuilt_osm_pbf", "url": args.source_url,
                   "path": str(args.pbf), "bytes": args.pbf.stat().st_size, "sha256": digest(args.pbf)},
        "network": {"crs": args.crs, "walk_speed_m_per_min": WALK_SPEED_M_PER_MIN,
                    "nodes": graph.number_of_nodes(), "directed_edges": graph.number_of_edges(),
                    "accepted_ways": handler.accepted_ways, "source_way_segments": handler.accepted_segments,
                    "bounds_projected": [min(xs), min(ys), max(xs), max(ys)],
                    "bounds_wgs84": [handler.min_lon, handler.min_lat, handler.max_lon, handler.max_lat]},
        "excluded_way_counts": dict(handler.excluded),
        "rules": {"included_highways": sorted(WALK_HIGHWAYS),
                  "excluded": ["foot=no/private", "access=no/private unless explicit foot permission", "area=yes"],
                  "direction": "Bidirectional except explicit oneway:foot values."},
        "limitations": [
            "The graph models OSM tag-permitted ordinary walking; it is not a safety, crossing-delay, accessibility or child-independent-mobility model.",
            "No building entrances, schedules, programme capacity, actual attendance, accompaniment or car travel are represented.",
            "PBF spatial coverage must be audited against the selected origins and published-coordinate venue proxies before city-level interpretation.",
        ],
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
