"""Aggregate completed B1 origin results to ready-made BlocksNet blocks; no routing.

The script deliberately reads already calculated B1 tables.  It does not alter
the network, routing rules, thresholds, or Navigator catalogue.
"""
from pathlib import Path
import json
import argparse
import hashlib
import geopandas as gpd
import pandas as pd

BLOCKS=Path(r'C:\Users\olesy\PycharmProjects\blocksnet-data\cities\saint_petersburg\data\blocks_cleaned.geojson')
ORIGINS=Path('data/urban-api-spb-residential-20261110/residential.geojson')
ROOT=Path('results/blocksnet-b1-study-areas-citywide-20261111')
CASES=Path('data/navigator-study-area-cases-ascii-20261111/manifest.json')
DEFAULT_OUT=Path('results/age-profiles-blocks-b1-20261112-r2')


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def main(out: Path):
 out.mkdir(parents=True, exist_ok=True)
 blocks=gpd.read_file(BLOCKS).to_crs(32636)
 source_block_records=int(len(blocks))
 # The published file has an almost entirely empty/non-unique ``fid``.  A hash
 # of the source geometry is invariant to dataframe ordering and is therefore
 # safer for a reproducible spatial join.  Exact duplicate polygons are not
 # distinct territorial units and are removed before joining.
 blocks['blocksnet_block_id']=blocks.geometry.map(
  lambda geom: hashlib.sha256(geom.normalize().wkb).hexdigest()[:16]
 )
 blocks=blocks.drop_duplicates('blocksnet_block_id',keep='first').copy()
 duplicate_records_removed=source_block_records-int(len(blocks))
 origins=gpd.read_file(ORIGINS)[['geometry']].reset_index(drop=True).to_crs(32636);origins['origin_id']=origins.index.astype(str)
 joined=gpd.sjoin(origins,blocks[['blocksnet_block_id','geometry']],predicate='within',how='left').drop(columns='index_right')
 if joined.origin_id.duplicated().any():raise RuntimeError('Origin matched multiple blocks')
 spatial_qa={
  'n_origins_input': int(len(origins)),
  'n_origins_assigned_to_block': int(joined.blocksnet_block_id.notna().sum()),
  'n_origins_unassigned_to_block': int(joined.blocksnet_block_id.isna().sum()),
  'join_predicate': 'within',
  'block_id_field': 'SHA-256(normalized source geometry), first 16 hex characters',
  'source_block_records': source_block_records,
  'blocks_after_exact_geometry_deduplication': int(len(blocks)),
  'source_duplicate_geometry_records_removed': duplicate_records_removed,
 }
 cases=json.loads(CASES.read_text(encoding='utf8'))['included_cases']; summary=[]; layers=[]
 for c in cases:
  d=pd.read_csv(ROOT/c['case_id']/'b1-by-origin.csv',dtype={'origin_id':str})
  x=joined[['origin_id','blocksnet_block_id']].merge(d,on='origin_id',how='left',validate='one_to_one')
  a=x.age_7_N_venue_proxy_within_30min;b=x.age_13_N_venue_proxy_within_30min;v=x.network_covered.eq(True)&a.notna()&b.notna()
  x['category']='unknown';x.loc[~x.network_covered.eq(True),'category']='uncovered';x.loc[v&(a>0)&(b>0),'category']='both';x.loc[v&(a>0)&(b==0),'category']='only_7';x.loc[v&(a==0)&(b>0),'category']='only_13';x.loc[v&(a==0)&(b==0),'category']='neither';x['delta_N']=b-a;x['delta_t']=x.age_13_nearest_minutes-x.age_7_nearest_minutes
  rows=[]
  for bid,q in x.groupby('blocksnet_block_id',dropna=True):
   z=q[q.network_covered.eq(True)&q.delta_N.notna()];r={'blocksnet_block_id':bid,'study_area_id':c['study_area_id'],'study_area_name':c['study_area_name'],'n_origins':len(q),'n_valid':len(z),'n_uncovered':int((~q.network_covered.eq(True)).sum()),'median_N7':z.age_7_N_venue_proxy_within_30min.median(),'median_N13':z.age_13_N_venue_proxy_within_30min.median(),'median_delta_N':z.delta_N.median(),'median_delta_t':z.delta_t.dropna().median()}
   for k in ['both','only_7','only_13','neither']:r[k+'_pct']=((z.category==k).mean()*100) if len(z) else None
   rows.append(r)
  frame=pd.DataFrame(rows);summary.append(frame);layers.append(blocks[['blocksnet_block_id','geometry']].merge(frame,on='blocksnet_block_id',how='inner'))
 result=pd.concat(summary,ignore_index=True)
 result.to_csv(out/'age_profiles_by_block.csv',index=False,encoding='utf-8-sig')
 gpd.GeoDataFrame(pd.concat(layers,ignore_index=True),crs=32636).to_crs(4326).to_file(out/'age_profiles_blocks.gpkg',layer='profiles',driver='GPKG')
 # A per-direction QA makes the denominator and every spatial loss auditable.
 for c in cases:
  d=pd.read_csv(ROOT/c['case_id']/'b1-by-origin.csv',dtype={'origin_id':str})
  x=joined[['origin_id','blocksnet_block_id']].merge(d,on='origin_id',how='left',validate='one_to_one')
  valid=x.network_covered.eq(True) & x.age_7_N_venue_proxy_within_30min.notna() & x.age_13_N_venue_proxy_within_30min.notna()
  spatial_qa.setdefault('by_direction',[]).append({
   'study_area_id':c['study_area_id'], 'study_area_name':c['study_area_name'],
   'n_result_rows':int(len(x)), 'n_network_covered':int(x.network_covered.eq(True).sum()),
   'n_network_uncovered':int((~x.network_covered.eq(True)).sum()),
   'n_valid_for_age_comparison':int(valid.sum()),
   'n_valid_unassigned_to_block':int((valid & x.blocksnet_block_id.isna()).sum())
  })
 manifest={'scenario':'B1','unit':'ready-made BlocksNet block','directions':len(cases),'routing_repeated':False,'block_source':str(BLOCKS),'block_id_field':'SHA-256(normalized source geometry), first 16 hex characters','spatial_join':spatial_qa}
 (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')

if __name__=='__main__':
 main(parse_args().out)
