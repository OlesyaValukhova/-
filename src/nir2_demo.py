"""Offline NIR-2 demonstration: real eligibility audit plus explicitly synthetic routing.

No GPS, diaries, requests or geographic route claims. Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import math
from datetime import date
from pathlib import Path


def age_eligible(age, lower, upper):
    """Three-valued interval: a known bound may rule out; missing bounds cannot confirm."""
    values = [age] + [v for v in (lower, upper) if v not in (None, '')]
    if any(isinstance(v, bool) or not math.isfinite(float(v)) or float(v) < 0 for v in values):
        raise ValueError('Invalid age value')
    age = float(age)
    lower = None if lower in (None, '') else float(lower)
    upper = None if upper in (None, '') else float(upper)
    if lower is not None and upper is not None and lower > upper:
        raise ValueError('Invalid age interval')
    if (lower is not None and age < lower) or (upper is not None and age > upper):
        return False
    return True if lower is not None and upper is not None else None


def shortest_times(edges, source):
    """Dijkstra on directed edge list (u, v, nonnegative minutes)."""
    adjacency = {}
    for u, v, minutes in edges:
        if not math.isfinite(minutes) or minutes < 0:
            raise ValueError('Edge times must be finite and nonnegative')
        adjacency.setdefault(u, []).append((v, minutes))
    result, queue = {source: 0}, [(0, source)]
    while queue:
        cost, node = heapq.heappop(queue)
        if cost != result[node]:
            continue
        for target, weight in adjacency.get(node, []):
            new = cost + weight
            if new < result.get(target, math.inf):
                result[target] = new
                heapq.heappush(queue, (new, target))
    return result


def program_profiles(program):
    values = program.get('profiles')
    if values is None:
        values = [program['profile']] if program.get('profile') else []
    if not isinstance(values, (list, tuple)) or any(not isinstance(k, str) or not k for k in values):
        raise ValueError('Profiles must be a list of nonempty labels')
    return set(values)


def indicators(programs, travel_times, age, threshold):
    if not math.isfinite(threshold) or threshold < 0:
        raise ValueError('Invalid travel budget')
    reached = []
    unknown_age_ids = set()
    possible_sites = set()
    for p in programs:
        program_profiles(p)
        cost = travel_times.get(p['site'], math.inf)
        if math.isnan(cost) or cost < 0:
            raise ValueError('Invalid travel time')
        eligible = age_eligible(age, p.get('min_age'), p.get('max_age'))
        if cost <= threshold:
            if eligible is True:
                reached.append(p)
            elif eligible is None:
                unknown_age_ids.add(p['id'])
            if eligible is not False:
                possible_sites.add(p['site'])
    all_eligible = [p for p in programs if age_eligible(age, p.get('min_age'), p.get('max_age')) is True]
    nearest = min((travel_times.get(p['site'], math.inf) for p in all_eligible), default=math.inf)
    per_profile = {}
    for p in all_eligible:
        for profile in program_profiles(p):
            per_profile[profile] = min(per_profile.get(profile, math.inf), travel_times.get(p['site'], math.inf))
    per_profile = {k: v if math.isfinite(v) else None for k, v in sorted(per_profile.items())}
    # Counts have distinct interpretations. Duplicate programmes at one site do not add sites.
    return {'programs': len({p['id'] for p in reached}),
            'sites': len({p['site'] for p in reached}),
            'profiles': len({k for p in reached for k in program_profiles(p)}),
            'reachable_known_age_programs_unknown_profile': sum(not program_profiles(p) for p in reached),
            'sites_possible_known_locations': len(possible_sites),
            'reachable_unknown_age_programs': len(unknown_age_ids),
            'nearest_by_profile_json': json.dumps(per_profile, ensure_ascii=False, sort_keys=True),
            'nearest_minutes': nearest if math.isfinite(nearest) else None,
            'nearest_status': ('computed_in_supplied_graph' if math.isfinite(nearest) else
                               'no_route_in_supplied_graph' if all_eligible else 'no_known_eligible_programs')}


def write_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def interval_union_eligible(age, intervals):
    """Three-valued union of explicit intervals, never an envelope across gaps."""
    states = [age_eligible(age, lower, upper) for lower, upper in intervals]
    if True in states:
        return True
    if not states or None in states:
        return None
    return False


def group_date_state(group, as_of):
    start = date.fromisoformat(group['lesson_start']) if group.get('lesson_start') else None
    end = date.fromisoformat(group['lesson_end']) if group.get('lesson_end') else None
    if start is not None and end is not None and start > end:
        raise ValueError('Reversed lesson date interval')
    if end is not None and end < as_of:
        return 'ended_before_snapshot'
    if start is not None and start > as_of:
        return 'starts_after_snapshot'
    if start is not None and end is not None:
        return 'date_interval_covers_snapshot'
    return 'incomplete_dates_unknown_activity'


def audit_groups(source, sample, output):
    groups_source = source.parent / 'sample-groups.csv'
    with groups_source.open(encoding='utf-8-sig', newline='') as stream:
        groups = list(csv.DictReader(stream))
    cards = {r['id']: r for r in sample}
    as_of = date(2026, 10, 20)  # Saved data snapshot, not an assumption of live status on run day.
    audited = []
    for group in groups:
        program = cards[group['program_id']]
        bounded = group['min_age'] != '' and group['max_age'] != ''
        match = None if not bounded else (float(program['min_age']) == float(group['min_age']) and
                                         float(program['max_age']) == float(group['max_age']))
        outside = None if not bounded else (float(group['min_age']) < float(program['min_age']) or
                                           float(group['max_age']) > float(program['max_age']))
        audited.append({**group, 'snapshot_date': as_of.isoformat(),
                        'date_state': group_date_state(group, as_of),
                        'has_explicit_age_bounds': bounded,
                        'group_bounds_equal_card': match,
                        'group_bounds_extend_outside_card': outside,
                        'negative_free_places': int(group['free_places_count']) < 0})
    write_csv(output / 'real_group_data_quality.csv', audited)
    summary = {'snapshot_date': as_of.isoformat(), 'groups': len(groups),
               'explicit_age_bounds': sum(r['has_explicit_age_bounds'] for r in audited),
               'bounds_extend_outside_card': sum(r['group_bounds_extend_outside_card'] is True for r in audited),
               'negative_free_places': sum(r['negative_free_places'] for r in audited),
               'date_states': {state: sum(r['date_state'] == state for r in audited)
                               for state in sorted({r['date_state'] for r in audited})}}
    (output / 'real_group_data_quality_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary


def run(output, source):
    output.mkdir(parents=True, exist_ok=True)
    with source.open(encoding='utf-8-sig', newline='') as stream:
        sample = list(csv.DictReader(stream))
    assert len(sample) == len({r['id'] for r in sample})
    real = []
    for age in range(7, 18):
        eligible = [r for r in sample if age_eligible(age, r['min_age'], r['max_age']) is True]
        real.append({'data_type': 'REAL_NONREPRESENTATIVE_SAMPLE_NO_ROUTING', 'age': age,
                     'sample_programs': len(sample), 'age_eligible_programs': len(eligible),
                     'eligible_with_coordinates': sum(bool(r['latitude']) and bool(r['longitude']) for r in eligible),
                     'eligible_with_reported_address': sum(bool(r['address']) for r in eligible)})
    write_csv(output / 'real_sample_age_eligibility.csv', real)
    group_summary = audit_groups(source, sample, output)
    # Entire graph, origins, sites and programme records below are invented for software verification.
    undirected = [('O1', 'J', 3), ('O2', 'J', 9), ('J', 'S1', 2), ('J', 'S2', 8), ('S2', 'S3', 6)]
    edges = [(u, v, t) for u, v, t in undirected] + [(v, u, t) for u, v, t in undirected]
    programs = [
        {'id': 'P1', 'site': 'S1', 'profile': 'music', 'min_age': 7, 'max_age': 10},
        {'id': 'P2', 'site': 'S1', 'profile': 'music', 'min_age': 7, 'max_age': 10},
        {'id': 'P3', 'site': 'S2', 'profile': 'sport', 'min_age': 7, 'max_age': 17},
        {'id': 'P4', 'site': 'S3', 'profile': 'science', 'min_age': 11, 'max_age': 17},
        {'id': 'P5', 'site': 'UNCONNECTED', 'profile': 'art', 'min_age': 7, 'max_age': 17},
        {'id': 'P6', 'site': 'S1', 'profile': 'art', 'min_age': None, 'max_age': None}]
    synthetic = []
    for origin in ['O1', 'O2']:
        times = shortest_times(edges, origin)
        for age in [8, 14]:
            for budget in [10, 20]:
                synthetic.append({'data_type': 'FULLY_SYNTHETIC_NOT_SAINT_PETERSBURG',
                                  'origin': origin, 'age': age, 'budget_minutes': budget,
                                  **indicators(programs, times, age, budget)})
    write_csv(output / 'synthetic_accessibility.csv', synthetic)
    (output / 'synthetic_inputs.json').write_text(json.dumps({'edges_minutes': edges, 'programs': programs}, indent=2), encoding='utf-8')
    groups_source = source.parent / 'sample-groups.csv'
    manifest = {'date': '2026-10-26', 'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'groups_source': str(groups_source),
                'groups_source_sha256': hashlib.sha256(groups_source.read_bytes()).hexdigest(),
                'real_sample_size': len(sample), 'real_spatial_accessibility_computed': False,
                'synthetic_graph_is_geographic': False, 'gps_or_diaries_used': False}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'real_sample_size': len(sample), 'real_age_rows': len(real), 'synthetic_rows': len(synthetic),
                      'group_audit': group_summary}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument('--source', type=Path, default=root/'results/navigator-pilot-20261020-checked/sample-programs.csv')
    parser.add_argument('--output', type=Path, default=root/'results/nir2-method-demo-20261026')
    args = parser.parse_args()
    run(args.output, args.source)
