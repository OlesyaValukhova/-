"""One-pass tiled B1 for the full observable Navigator subset and optional cases.

Builds exactly one buffered OSM graph per core tile, then calculates all named
offer layers and both ages in that same graph. Main full-catalogue results use
N_venue (unique published coordinates); N_offer_card is supplementary.
"""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
import geopandas as gpd
import pandas as pd
from shapely.geometry import box
from calculate_tiled_b1_from_pbf import (WALK_SPEED_M_PER_MIN, calculate_tile, make_tiles, uncovered_tile, sha)

def load_case(name, offers_path, venues_path, crs):
    offers=pd.read_csv(offers_path,encoding='utf-8-sig',dtype={'program_id':str,'coordinate_id':str})
    venues=gpd.read_file(venues_path).to_crs(crs); venues['coordinate_id']=venues.coordinate_id.astype(str)
    if not offers.program_id.is_unique or not venues.coordinate_id.is_unique: raise ValueError(f'{name}: non-unique IDs')
    return {'name':name,'offers':offers,'venues':venues,'sources':{str(offers_path):sha(offers_path),str(venues_path):sha(venues_path)},'rows':[],'audit':[]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pbf',type=Path,required=True); p.add_argument('--origins',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--case',nargs=3,action='append',metavar=('NAME','OFFERS_CSV','VENUES_GEOJSON'),required=True)
    p.add_argument('--ages',type=float,nargs='+',default=[7,13]); p.add_argument('--thresholds',type=float,nargs='+',default=[10,15,20,30]); p.add_argument('--tile-size-m',type=float,default=8000); p.add_argument('--crs',type=int,default=32636)
    a=p.parse_args()
    if a.output.exists(): p.error('Output must be new')
    a.output.mkdir(parents=True); buffer_m=max(a.thresholds)*WALK_SPEED_M_PER_MIN
    origins=gpd.read_file(a.origins).to_crs(a.crs); origins['origin_id']=origins.get('origin_id',pd.Series(origins.index,index=origins.index)).astype(str)
    cases=[load_case(n,Path(o),Path(v),a.crs) for n,o,v in a.case]
    manifest={'status':'running','started_utc':datetime.now(timezone.utc).isoformat(),'scenario':'B1 buffered sequential tiles; one PBF graph per tile for all cases','ages':a.ages,'thresholds_minutes':a.thresholds,'tile_size_m':a.tile_size_m,'buffer_m':buffer_m,'origins':len(origins),'main_case':cases[0]['name'],'metric_units':{'N_venue':'unique published-coordinate venue proxies (primary)','N_offer_card':'age-eligible programme-card-coordinate offer proxies (supplementary)'},'deduplication':'exact published longitude/latitude formatted to 12 decimals and hashed to coordinate_id','sources':{str(a.pbf):sha(a.pbf),str(a.origins):sha(a.origins)},'cases':{c['name']:c['sources'] for c in cases},'tile_audit':[]}
    mp=a.output/'manifest.json'; mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    try:
      from build_walk_graph_from_osm_pbf import WalkGraphHandler
      for ordinal,(ix,iy,tile_origins,bounds) in enumerate(make_tiles(origins,a.tile_size_m),1):
        area=box(*bounds).buffer(buffer_m); h=WalkGraphHandler(a.crs,tuple(area.bounds)); h.apply_file(str(a.pbf),locations=True); graph=h.graph
        tile={'tile':ordinal,'tile_x':ix,'tile_y':iy,'origins':len(tile_origins),'graph_nodes':graph.number_of_nodes(),'graph_edges':graph.number_of_edges(),'status':'computed' if graph.number_of_edges() else 'uncovered_no_usable_pbf_network'}
        for c in cases:
          localv=c['venues'][c['venues'].geometry.intersects(area)].copy(); localo=c['offers'][c['offers'].coordinate_id.isin(set(localv.coordinate_id))].copy()
          if graph.number_of_edges():
            values,audit=calculate_tile(graph,tile_origins,localv,localo,a.ages,a.thresholds); values.insert(1,'network_covered',True)
          else: values=uncovered_tile(tile_origins,a.ages,a.thresholds); audit=[]
          c['rows'].append(values); c['audit'] += [{**x,'tile':ordinal} for x in audit]; tile[c['name']+'_venues_in_buffer']=len(localv)
        manifest['tile_audit'].append(tile); (a.output/'tile-progress.json').write_text(json.dumps(manifest['tile_audit'],ensure_ascii=False,indent=2),encoding='utf8'); del graph,h
      for c in cases:
        out=pd.concat(c['rows'],ignore_index=True)
        if len(out)!=len(origins) or not out.origin_id.is_unique: raise RuntimeError(f"{c['name']}: origin merge failed")
        folder=a.output/c['name']; folder.mkdir(); out.to_csv(folder/'b1-by-origin.csv',index=False,encoding='utf-8-sig')
        geo=origins[['origin_id','geometry']].merge(out,on='origin_id',validate='one_to_one'); geo.to_crs(4326).to_file(folder/'b1-by-origin.geojson',driver='GeoJSON')
        manifest.setdefault('case_summary',{})[c['name']]={'offer_cards':len(c['offers']),'unique_coordinate_venues':len(c['venues']),'age_eligible_offer_cards':{str(int(age)):int(((c['offers'].min_age<=age)&(c['offers'].max_age>=age)).sum()) for age in a.ages},'origins_without_network':int((~out.network_covered).sum()),'age_tile_audit':c['audit']}
      manifest['status']='computed_with_uncovered_origins' if any(x['status']!='computed' for x in manifest['tile_audit']) else 'computed'
    except Exception as e: manifest.update(status='failed',error=f'{type(e).__name__}: {e}')
    manifest['finished_utc']=datetime.now(timezone.utc).isoformat(); mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8'); print(json.dumps({'status':manifest['status'],'tiles':len(manifest['tile_audit'])},ensure_ascii=False))
    return 0 if manifest['status'].startswith('computed') else 1
if __name__=='__main__': raise SystemExit(main())
