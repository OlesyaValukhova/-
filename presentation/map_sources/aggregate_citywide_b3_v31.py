#!/usr/bin/env python3
"""Aggregate existing citywide B3 point results to the original BlocksNet polygons.

No routing, sum of directions, or imputation. Requires pandas, geopandas,
shapely >=2 and a spatial-index backend. See README_citywide_b3_v31.md.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd

N7 = 'age_7_N_venue_proxy_within_30min'
N13 = 'age_13_N_venue_proxy_within_30min'
KEY = 'blocksnet_block_id'


def summarize(joined: pd.DataFrame) -> pd.DataFrame:
    """Pair at each covered origin first; unknowns and uncovered are not zero."""
    x = joined.copy()
    coverage = x.network_covered.astype('string').str.lower().str.strip()
    if not coverage.isin(['true', 'false']).all():
        raise ValueError('network_covered must be an explicit true/false at every origin')
    x['covered'] = coverage.eq('true')
    x[N7] = pd.to_numeric(x[N7], errors='raise')
    x[N13] = pd.to_numeric(x[N13], errors='raise')
    x['valid'] = x.covered & x[N7].notna() & x[N13].notna()
    if ((x.loc[x.valid, [N7, N13]] < 0).any().any()):
        raise ValueError('Negative reachable-coordinate count')
    x['delta'] = (x[N13] - x[N7]).where(x.valid)
    x['n_uncovered'] = (~x.covered).astype(int)
    x['n_unknown'] = (x.covered & ~x.valid).astype(int)
    g = x[x[KEY].notna()].groupby(KEY, sort=True, dropna=True)
    result = g.agg(n_origins=('origin_id','size'), n_valid=('valid','sum'),
                   n_uncovered=('n_uncovered','sum'), n_unknown=('n_unknown','sum'),
                   median_delta_N=('delta','median')).reset_index()
    assert (result.n_origins == result.n_valid + result.n_uncovered + result.n_unknown).all()
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--origin-geojson', type=Path, required=True, help='full_observable/b3-by-origin.geojson')
    p.add_argument('--blocks', type=Path, required=True, help='original blocks_cleaned.geojson')
    p.add_argument('--reference-b3', type=Path, required=True, help='area_38_art_blocks_b3.csv')
    p.add_argument('--reference-origins', type=Path, required=True, help='full_observable/b3-by-origin.csv')
    p.add_argument('--out', type=Path, required=True, help='new output directory')
    a=p.parse_args()
    if a.out.exists() and any(a.out.iterdir()):
        raise FileExistsError(f'Output directory is not empty: {a.out}')
    import geopandas as gpd

    pts=gpd.read_file(a.origin_geojson)
    required={'origin_id','network_covered',N7,N13,'geometry'}
    missing=required-set(pts.columns)
    if missing: raise ValueError(f'Missing origin fields: {sorted(missing)}')
    if pts.crs is None: raise ValueError('Origins have no CRS')
    pts['origin_id']=pts.origin_id.astype(str)
    if len(pts)!=30611 or not pts.origin_id.is_unique:
        raise ValueError('Expected 30,611 unique origin IDs')
    if pts.geometry.isna().any() or not pts.geom_type.eq('Point').all():
        raise ValueError('Every origin must have a point geometry')
    # Avoid accepting a geometry from a different run, scenario or age slice.
    reference=pd.read_csv(a.reference_origins,dtype={'origin_id':str})
    if not {'origin_id','network_covered',N7,N13}.issubset(reference.columns):
        raise ValueError('Reference origin CSV lacks required fields')
    check=pts[['origin_id','network_covered',N7,N13]].merge(
        reference[['origin_id','network_covered',N7,N13]],on='origin_id',how='outer',
        suffixes=('_geo','_csv'),indicator=True,validate='one_to_one')
    if not check['_merge'].eq('both').all(): raise ValueError('Origin ID sets differ')
    left=check.network_covered_geo.astype('string').str.lower().str.strip()
    right=check.network_covered_csv.astype('string').str.lower().str.strip()
    if not left.eq(right).all(): raise ValueError('Origin coverage differs from CSV')
    for col in [N7,N13]:
        left=pd.to_numeric(check[col+'_geo'],errors='raise')
        right=pd.to_numeric(check[col+'_csv'],errors='raise')
        if not (left.eq(right) | (left.isna() & right.isna())).all():
            raise ValueError(f'Origin values for {col} differ from CSV')
    blocks=gpd.read_file(a.blocks)
    if blocks.crs is None: raise ValueError('Blocks have no CRS')
    blocks=blocks.to_crs(32636)
    blocks[KEY]=blocks.geometry.map(lambda geom: hashlib.sha256(geom.normalize().wkb).hexdigest()[:16])
    blocks=blocks.drop_duplicates(KEY).copy()
    if len(blocks)!=9567:
        raise ValueError(f'Expected 9,567 deduplicated original blocks, got {len(blocks)}')
    x=gpd.sjoin(pts.to_crs(32636),blocks[[KEY,'geometry']],how='left',predicate='within').drop(columns='index_right')
    if x.origin_id.duplicated().any(): raise ValueError('An origin matches multiple blocks')
    assigned=int(x[KEY].notna().sum())
    coverage=x.network_covered.astype('string').str.lower().str.strip()
    if assigned!=30609 or int(coverage.eq('true').sum())!=30224:
        raise ValueError(f'Unexpected join/coverage: assigned={assigned}, covered={coverage.eq("true").sum()}')
    result=summarize(x)
    ref=pd.read_csv(a.reference_b3,dtype={KEY:'string'})
    if ref[KEY].duplicated().any(): raise ValueError('Duplicate IDs in reference B3 table')
    cmp=result.merge(ref[[KEY,'n_origins','n_valid','n_uncovered']],on=KEY,how='outer',suffixes=('_ours','_ref'),indicator=True,validate='one_to_one')
    for col in ['n_origins','n_valid','n_uncovered']:
        if not cmp[f'{col}_ours'].eq(cmp[f'{col}_ref']).all():
            raise ValueError(f'B3 reference mismatch for {col}; no output was saved')
    if len(cmp)!=3330 or not cmp['_merge'].eq('both').all() or result.n_unknown.sum()!=0:
        raise ValueError('Reference IDs or unknown counts do not match; no output was saved')
    if result.n_valid.sum()!=30222 or result.n_origins.sum()!=30609:
        raise ValueError('Unexpected aggregate denominator; no output was saved')
    qa={'scenario':'B3','threshold_minutes':30,'age_difference':'N13 - N7 per valid origin, then median per block',
        'directions':'all observed unique coordinate proxies; directions are not summed',
        'origins_total':len(pts),'assigned':assigned,'unassigned':len(pts)-assigned,
        'covered_total':int(coverage.eq('true').sum()),'valid_assigned':int(result.n_valid.sum()),
        'blocks_with_origins':len(result),'reference_origin_values_match':True,'reference_block_rows':len(cmp),'reference_counts_match':True,
        'unknown_assigned':int(result.n_unknown.sum()),'join_predicate':'within',
        'block_id':'sha256(normalized EPSG:32636 geometry WKB) first 16 hex characters',
        'limitations':'modelled access, not capacity, actual attendance, safety or independent travel'}
    a.out.mkdir(parents=True,exist_ok=True)
    result.to_csv(a.out/'b3_citywide_age_delta_by_block.csv',index=False)
    geo=blocks[[KEY,'geometry']].merge(result,on=KEY,how='inner',validate='one_to_one').to_crs(4326)
    geo.to_file(a.out/'b3_citywide_age_delta_by_block.geojson',driver='GeoJSON')
    (a.out/'manifest.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(qa,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
