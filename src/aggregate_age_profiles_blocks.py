"""Aggregate completed B1 origin results to ready-made BlocksNet blocks; no routing."""
from pathlib import Path
import json
import geopandas as gpd
import pandas as pd

BLOCKS=Path(r'C:\Users\olesy\PycharmProjects\blocksnet-data\cities\saint_petersburg\data\blocks_cleaned.geojson')
ORIGINS=Path('data/urban-api-spb-residential-20261110/residential.geojson')
ROOT=Path('results/blocksnet-b1-study-areas-citywide-20261111')
CASES=Path('data/navigator-study-area-cases-ascii-20261111/manifest.json')
OUT=Path('results/age-profiles-blocks-b1-20261112')

def main():
 OUT.mkdir(exist_ok=True)
 blocks=gpd.read_file(BLOCKS).to_crs(32636).reset_index(drop=True);blocks['blocksnet_block_id']=blocks.index.astype(str)
 origins=gpd.read_file(ORIGINS)[['geometry']].reset_index(drop=True).to_crs(32636);origins['origin_id']=origins.index.astype(str)
 joined=gpd.sjoin(origins,blocks[['blocksnet_block_id','geometry']],predicate='within',how='left').drop(columns='index_right')
 if joined.origin_id.duplicated().any():raise RuntimeError('Origin matched multiple blocks')
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
 pd.concat(summary,ignore_index=True).to_csv(OUT/'age_profiles_by_block.csv',index=False,encoding='utf-8-sig')
 gpd.GeoDataFrame(pd.concat(layers,ignore_index=True),crs=32636).to_crs(4326).to_file(OUT/'age_profiles_blocks.gpkg',layer='profiles',driver='GPKG')
 (OUT/'manifest.json').write_text(json.dumps({'scenario':'B1','unit':'ready-made BlocksNet block','directions':len(cases),'routing_repeated':False,'block_source':str(BLOCKS)},ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':main()
