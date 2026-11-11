"""Citywide B1 (walk) and B3 (intermodal) accessibility using BlocksNet graph.

Uses batched SciPy shortest paths; resumes from per-batch checkpoints.
"""
import argparse
import json
import pickle
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

WALK_M_PER_MIN = 5000 / 60


def build_matrix(G, nodes, index, scenario, wait_min):
    rr, cc, ww = [], [], []
    counts = {}
    for u, v, data in G.edges(data=True):
        typ = data.get('type', '')
        counts[typ] = counts.get(typ, 0) + 1
        if scenario == 'B1' and typ != 'walk':
            continue
        t = data.get('time_min')
        try:
            t = float(t)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(t) or t < 0:
            continue
        if scenario == 'B3' and typ == 'boarding':
            t += wait_min
        # SciPy sparse shortest paths treats explicit zero weights as absent arcs.
        # Preserve zero-time transfer edges with a negligible positive weight.
        if t == 0:
            t = 1e-6
        rr.append(index[u]); cc.append(index[v]); ww.append(t)
    # CSR sums duplicate edges; instead retain the minimum weight per (u,v).
    edge = pd.DataFrame({'r': rr, 'c': cc, 'w': ww})
    edge = edge.groupby(['r', 'c'], sort=False, as_index=False)['w'].min()
    matrix = coo_matrix((edge.w.to_numpy(dtype=np.float32),
                         (edge.r.to_numpy(), edge.c.to_numpy())),
                        shape=(len(nodes), len(nodes))).tocsr()
    del edge, rr, cc, ww
    return matrix, counts


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--graph', type=Path, required=True)
    p.add_argument('--origins', type=Path, required=True)
    p.add_argument('--case', nargs=3, action='append', required=True,
                   metavar=('NAME', 'OFFERS_CSV', 'VENUES_GEOJSON'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--scenario', choices=['B1', 'B3'], required=True)
    p.add_argument('--ages', nargs='+', type=float, default=[7, 13])
    p.add_argument('--thresholds', nargs='+', type=float, default=[10, 15, 20, 30])
    p.add_argument('--snap-m', type=float, default=250)
    p.add_argument('--wait-min', type=float, default=5,
                   help='Added per boarding edge in B3, not per ride edge')
    p.add_argument('--batch-size', type=int, default=32)
    p.add_argument('--no-geojson', action='store_true',
                   help='Write CSV outputs only (useful when many cases are compared).')
    p.add_argument('--exclude-edge-ids', type=Path,
                   help='CSV with directed edge_id values u:v:key for a diagnostic sensitivity scenario.')
    a = p.parse_args()
    if a.batch_size < 1 or a.snap_m <= 0 or a.wait_min < 0:
        p.error('Invalid batch-size, snap-m or wait-min')
    if len(set(x[0] for x in a.case)) != len(a.case):
        p.error('Case names must be unique')
    if a.output.exists() and not (a.output / 'settings.json').exists():
        p.error('Output folder exists without a compatible checkpoint')
    a.output.mkdir(parents=True, exist_ok=True)
    settings = dict(graph=str(a.graph.resolve()), origins=str(a.origins.resolve()),
                    case=[[n,str(Path(o).resolve()),str(Path(v).resolve())] for n,o,v in a.case],
                    scenario=a.scenario, ages=a.ages, thresholds=a.thresholds,
                    snap_m=a.snap_m, wait_min=a.wait_min if a.scenario=='B3' else 0,
                    batch_size=a.batch_size,
                    exclude_edge_ids=str(a.exclude_edge_ids.resolve()) if a.exclude_edge_ids else None)
    settings_file = a.output/'settings.json'
    if settings_file.exists():
        if json.loads(settings_file.read_text(encoding='utf8')) != settings:
            p.error('Settings differ from saved run; choose another output folder')
    else:
        settings_file.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf8')
    print('Loading graph...', flush=True)
    with a.graph.open('rb') as f:
        G = pickle.load(f)  # Load only from trusted source.
    excluded_edges = 0
    if a.exclude_edge_ids:
        exclusions = pd.read_csv(a.exclude_edge_ids, dtype={'edge_id': str})
        if 'edge_id' not in exclusions:
            raise ValueError('exclude-edge-ids CSV must contain edge_id')
        for value in exclusions.edge_id.dropna().unique():
            parts = str(value).split(':')
            if len(parts) != 3:
                continue
            u, v, key = map(int, parts)
            if G.has_edge(u, v, key):
                G.remove_edge(u, v, key)
                excluded_edges += 1
        print(f'Diagnostic exclusions applied: {excluded_edges}', flush=True)
    crs = G.graph.get('crs', 32636)
    if isinstance(crs, int):
        crs = f'EPSG:{crs}'
    nodes = list(G.nodes())
    index = {node:i for i,node in enumerate(nodes)}
    coords = np.array([(G.nodes[n].get('x', np.nan),G.nodes[n].get('y',np.nan)) for n in nodes])
    walk_nodes = set()
    for u,v,d in G.edges(data=True):
        if d.get('type') == 'walk':
            walk_nodes.add(u); walk_nodes.add(v)
    walk_idx = np.array([index[n] for n in walk_nodes if np.isfinite(coords[index[n]]).all()], dtype=np.int64)
    if not len(walk_idx):
        raise RuntimeError('No walking nodes')
    tree = cKDTree(coords[walk_idx])
    print('Building sparse graph...', flush=True)
    matrix, edge_counts = build_matrix(G, nodes, index, a.scenario, a.wait_min)
    print(f'{len(nodes)} nodes, {matrix.nnz} arcs; scenario {a.scenario}', flush=True)
    del G, index, nodes, coords

    origins = gpd.read_file(a.origins).to_crs(crs)
    origins['origin_id'] = origins.get('origin_id',pd.Series(origins.index,index=origins.index)).astype(str)
    if not origins.origin_id.is_unique:
        raise ValueError('Nonunique origin_id')
    if not (origins.geometry.geom_type == 'Point').all():
        raise ValueError('Origins must be points')
    origins = origins.reset_index(drop=True)
    od, oi = tree.query(np.column_stack([origins.geometry.x, origins.geometry.y]))
    oidx = walk_idx[oi]
    ovalid = od <= a.snap_m
    print(f'Origin snap <= {a.snap_m:g}m: {int(ovalid.sum())}/{len(origins)}', flush=True)

    cases = []
    for name, offers_path, venues_path in a.case:
        offers = pd.read_csv(offers_path, encoding='utf-8-sig',
                             dtype={'program_id':str,'coordinate_id':str})
        venues = gpd.read_file(venues_path).to_crs(crs)
        venues['coordinate_id'] = venues.coordinate_id.astype(str)
        if not venues.coordinate_id.is_unique or not offers.program_id.is_unique:
            raise ValueError(f'{name}: duplicate IDs')
        if not set(offers.coordinate_id.astype(str)).issubset(set(venues.coordinate_id)):
            raise ValueError(f'{name}: offers reference unknown venue')
        if not (venues.geometry.geom_type == 'Point').all():
            raise ValueError(f'{name}: venue geometry must be points')
        vd, vi = tree.query(np.column_stack([venues.geometry.x, venues.geometry.y]))
        venue_nodes = walk_idx[vi]
        venue_valid = vd <= a.snap_m
        venue_ids = venues.coordinate_id.to_numpy()
        venue_lookup = {v:i for i,v in enumerate(venue_ids)}
        age_data = {}
        for age in a.ages:
            eligible = offers[(pd.to_numeric(offers.min_age, errors='coerce') <= age) &
                              (pd.to_numeric(offers.max_age, errors='coerce') >= age)]
            weights = eligible.groupby('coordinate_id').size()
            ids = [venue_lookup[x] for x in weights.index if x in venue_lookup and venue_valid[venue_lookup[x]]]
            ids = np.array(ids, dtype=np.int64)
            age_data[age] = dict(nodes=venue_nodes[ids], snap=vd[ids]/WALK_M_PER_MIN,
                                 weights=np.array([weights.loc[venue_ids[i]] for i in ids], dtype=np.int64))
        cases.append((name, age_data, int(venue_valid.sum()), len(venues), len(offers)))
        print(f'{name}: {int(venue_valid.sum())}/{len(venues)} venues snapped', flush=True)

    checkpoints = a.output/'batches'
    checkpoints.mkdir(exist_ok=True)
    n = len(origins)
    max_t = max(a.thresholds)
    n_batches = (n + a.batch_size - 1)//a.batch_size
    for batch in range(n_batches):
        start = batch*a.batch_size
        stop = min(start+a.batch_size, n)
        target = checkpoints/f'batch-{batch:05d}.pkl'
        if target.exists():
            continue
        t0 = time.time()
        valid_rows = np.flatnonzero(ovalid[start:stop])
        if len(valid_rows):
            # A route cannot be within the threshold if its network segment exceeds it.
            dist = dijkstra(matrix, directed=True, indices=oidx[start:stop][valid_rows],
                            limit=max_t, return_predecessors=False)
            dist = np.atleast_2d(dist)
        else:
            dist = None
        results = {}
        for name, ages, _, _, _ in cases:
            frame = pd.DataFrame({'origin_id': origins.origin_id.iloc[start:stop].to_numpy(),
                                  'network_covered': ovalid[start:stop]})
            frame['network_snap_m'] = od[start:stop]
            for age in a.ages:
                prefix = f'age_{age:g}'
                dat = ages[age]
                nearest = np.full(stop-start, np.nan)
                venue_counts = {t:np.full(stop-start, np.nan) for t in a.thresholds}
                card_counts = {t:np.full(stop-start, np.nan) for t in a.thresholds}
                if len(valid_rows):
                    for t in a.thresholds:
                        venue_counts[t][valid_rows] = 0
                        card_counts[t][valid_rows] = 0
                    if len(dat['nodes']):
                        travel = dist[:,dat['nodes']].astype(np.float32,copy=True)
                        travel += (od[start:stop][valid_rows]/WALK_M_PER_MIN)[:,None]
                        travel += dat['snap'][None,:]
                        best = travel.min(axis=1)
                        nearest[valid_rows] = np.where(best<=max_t,best,np.nan)
                        for t in a.thresholds:
                            reached = travel <= t
                            venue_counts[t][valid_rows] = reached.sum(axis=1)
                            card_counts[t][valid_rows] = reached @ dat['weights']
                frame[f'{prefix}_nearest_minutes'] = nearest
                for t in a.thresholds:
                    frame[f'{prefix}_N_venue_proxy_within_{t:g}min'] = venue_counts[t]
                    frame[f'{prefix}_N_program_card_proxy_within_{t:g}min'] = card_counts[t]
            results[name] = frame
        tmp = target.with_suffix('.tmp')
        with tmp.open('wb') as f:
            pickle.dump(results,f,protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(target)
        print(f'{a.scenario} batch {batch+1}/{n_batches}: origins {start}-{stop-1}, {time.time()-t0:.1f}s', flush=True)

    summary = {'scenario':a.scenario,'status':'computed','origins':n,
               'excluded_directed_edges':excluded_edges,
               'origin_snap_covered':int(ovalid.sum()),'origin_uncovered':int((~ovalid).sum()),
               'snap_limit_m':a.snap_m,'wait_per_boarding_min':a.wait_min if a.scenario=='B3' else 0,
               'edge_type_counts':edge_counts,'cases':{}}
    for name, ages, nv, total_v, total_o in cases:
        frames=[]
        for batch in range(n_batches):
            with (checkpoints/f'batch-{batch:05d}.pkl').open('rb') as f:
                frames.append(pickle.load(f)[name])
        out=pd.concat(frames,ignore_index=True)
        folder=a.output/name
        folder.mkdir(exist_ok=True)
        out.to_csv(folder/f'{a.scenario.lower()}-by-origin.csv',index=False,encoding='utf-8-sig')
        if not a.no_geojson:
            geo=origins[['origin_id','geometry']].merge(out,on='origin_id',validate='one_to_one')
            geo.to_crs(4326).to_file(folder/f'{a.scenario.lower()}-by-origin.geojson',driver='GeoJSON')
        summary['cases'][name]={'venues_total':total_v,'venues_snapped':nv,'offer_cards':total_o,
                                'eligible_snapped_venues':{str(age):len(ages[age]['nodes']) for age in a.ages}}
    (a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    print('DONE:',a.output,flush=True)

if __name__=='__main__':
    main()
