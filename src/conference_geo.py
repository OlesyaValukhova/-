"""Reproducible OSM walking graph and residential-origin audit; no behavioural claims.

Fetch once, keep raw response and query. Rebuild offline with --offline.
Walking network is a model from OSM tags, not a safety/independence assessment.
"""
import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import requests
import networkx as nx
from shapely.geometry import Polygon, mapping
from scipy.spatial import cKDTree

DEFAULT_BBOX = (59.925, 30.18, 59.98, 30.31)  # S,W,N,E: island plus a boundary buffer
RESIDENTIAL = {'apartments', 'residential', 'house', 'detached', 'terrace', 'dormitory', 'semidetached_house'}
WALK = {'footway','pedestrian','path','steps','living_street','residential','service','unclassified','tertiary','secondary','primary','tertiary_link','secondary_link','primary_link','track','road'}

def haversine(a,b):
    p1,p2=map(math.radians,(a[1],b[1])); dp=p2-p1; dl=math.radians(b[0]-a[0])
    return 6371008.8*2*math.asin(min(1,math.sqrt(math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2)))

def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def build(raw, output):
    elements=raw['elements']; nodes={e['id']:e for e in elements if e['type']=='node'}
    graph=nx.Graph(); features=[]; excluded={}; buildings=[]
    for w in elements:
        if w['type']!='way': continue
        t=w.get('tags',{}); refs=w.get('nodes',[])
        if t.get('building') in RESIDENTIAL and len(refs)>3 and all(n in nodes for n in refs):
            poly=Polygon([(nodes[n]['lon'],nodes[n]['lat']) for n in refs])
            if poly.is_valid and not poly.is_empty:
                pt=poly.representative_point()
                buildings.append((w,poly,pt))
        h=t.get('highway')
        if not h: continue
        reason=None
        if h not in WALK: reason='excluded_highway'
        elif t.get('foot') in {'no','private'}: reason='foot_restriction'
        elif t.get('access') in {'no','private'} and t.get('foot') not in {'yes','designated','permissive'}: reason='access_restriction'
        elif t.get('area')=='yes': reason='area_not_linear_route'
        if reason:
            excluded[reason]=excluded.get(reason,0)+1; continue
        for u,v in zip(refs,refs[1:]):
            if u not in nodes or v not in nodes: raise ValueError('Incomplete OSM way geometry')
            a=(nodes[u]['lon'],nodes[u]['lat']); b=(nodes[v]['lon'],nodes[v]['lat']); length=haversine(a,b)
            if u==v or length==0: continue
            # Foot oneway is rare but must not be silently modelled as bidirectional.
            if t.get('oneway:foot') in {'yes','1','-1'}:
                excluded['oneway_foot_segments']=excluded.get('oneway_foot_segments',0)+1; continue
            graph.add_node(u,lon=a[0],lat=a[1]); graph.add_node(v,lon=b[0],lat=b[1])
            if not graph.has_edge(u,v) or graph[u][v]['length_m']>length:
                graph.add_edge(u,v,length_m=length,way_id=w['id'],highway=h)
            features.append({'type':'Feature','geometry':{'type':'LineString','coordinates':[a,b]},'properties':{'way_id':w['id'],'u':u,'v':v,'length_m':length,'highway':h,'name':t.get('name'),'access':t.get('access'),'foot':t.get('foot')}})
    if not graph: raise ValueError('No usable walking graph')
    components=sorted(nx.connected_components(graph),key=len,reverse=True); component_id={n:i for i,c in enumerate(components) for n in c}
    dump(output/'network.geojson',{'type':'FeatureCollection','features':features})
    with (output/'edges.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=['u','v','length_m','way_id','highway']); writer.writeheader()
        for u,v,d in graph.edges(data=True): writer.writerow({'u':u,'v':v,**d})
    with (output/'nodes.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=['node_id','lon','lat','component']); writer.writeheader()
        for n,d in graph.nodes(data=True):writer.writerow({'node_id':n,**d,'component':component_id[n]})
    origins=[]; building_features=[]
    # Nearest graph NODE, not a fabricated access route. Offsets retained explicitly.
    coordinates=[(n,(d['lon'],d['lat'])) for n,d in graph.nodes(data=True)]
    # Local equirectangular nearest-node search, refined by haversine among 8 candidates.
    scale=math.cos(math.radians(59.95))
    tree=cKDTree([(xy[0]*scale,xy[1]) for _,xy in coordinates])
    for w,poly,pt in buildings:
        t=w['tags']; entrance=[nodes[n] for n in w['nodes'] if nodes[n].get('tags',{}).get('entrance') not in (None,'no','emergency')]
        for e in (entrance or [None]):
            lon,lat=(e['lon'],e['lat']) if e else (pt.x,pt.y)
            _,indices=tree.query((lon*scale,lat),k=min(8,len(coordinates)))
            nearest,offset=min(((coordinates[int(i)][0],haversine((lon,lat),coordinates[int(i)][1])) for i in __import__('numpy').atleast_1d(indices)),key=lambda p:p[1])
            row={'origin_id':f"way/{w['id']}"+(f"/entrance/{e['id']}" if e else '/proxy'), 'building_osm_id':w['id'],'building':t['building'],'lon':lon,'lat':lat,'point_type':'osm_entrance' if e else 'inside_building_proxy','street':t.get('addr:street',''),'housenumber':t.get('addr:housenumber',''),'nearest_node':nearest,'snap_distance_m':round(offset,2),'component':component_id[nearest],'access_verified':False}
            origins.append(row)
        building_features.append({'type':'Feature','geometry':mapping(poly),'properties':{'osm_id':w['id'],**t}})
    with (output/'origins.csv').open('w',newline='',encoding='utf-8-sig') as f:
        if origins:
            writer=csv.DictWriter(f,fieldnames=list(origins[0]));writer.writeheader();writer.writerows(origins)
    dump(output/'residential-buildings.geojson',{'type':'FeatureCollection','features':building_features})
    summary={'nodes':len(graph),'edges':graph.number_of_edges(),'components':len(components),'largest_component_nodes':len(components[0]),'component_sizes_first_15':[len(c) for c in components[:15]],'residential_buildings':len(buildings),'origin_points':len(origins),'entrance_origins':sum(o['point_type']=='osm_entrance' for o in origins),'origins_snap_gt_50m':sum(o['snap_distance_m']>50 for o in origins),'excluded':excluded,'osm_base_timestamp':raw.get('osm3s',{}).get('timestamp_osm_base'),'limitations':['No school/home chains or parent time inferred.','Origins are OSM entrances when available; otherwise representative points inside residential-tagged buildings.','Snapping distance is NOT a real walking access path. Entrance/access audit needed before OD claims.','Graph models tag-permitted walking, not safety or independent child mobility.','No public transport, crossing delays or completeness guarantee.','BBox is acquisition window, not an administrative island boundary; mainland/border features must be filtered for analysis.','Disconnected components preserved, no synthetic bridge edges.']}
    dump(output/'summary.json',summary)
    return summary

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('data/conference-20261109/geo'));p.add_argument('--offline',action='store_true');p.add_argument('--map-api',action='store_true',help='Official OSM map API for compact windows only');p.add_argument('--endpoint',default='https://overpass-api.de/api/interpreter');p.add_argument('--bbox',nargs=4,type=float,default=DEFAULT_BBOX);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    bbox=','.join(str(v) for v in a.bbox)
    query=f'[out:json][timeout:90];(way[highway]({bbox});way[building~"^(apartments|residential|house|detached|terrace|dormitory|semidetached_house)$"]({bbox}););(._;>;);out body;'
    (a.output/'query.overpassql').write_text(query,encoding='utf-8')
    rawpath=a.output/'osm-raw.json'
    manifest={'acquisition_window_s_w_n_e':a.bbox,'source':'OpenStreetMap contributors / Overpass API','license':'ODbL 1.0','license_url':'https://www.openstreetmap.org/copyright','endpoint':a.endpoint,'requested_at_utc':datetime.now(timezone.utc).isoformat()}
    if not a.offline:
        try:
            if a.map_api:
                s,w,n,e=a.bbox
                url=f'https://api.openstreetmap.org/api/0.6/map.json?bbox={w},{s},{e},{n}'
                manifest['endpoint']=url
                response=requests.get(url,timeout=(15,50),headers={'User-Agent':'NIR-walking-accessibility-pilot/0.1'})
            else:
                response=requests.post(a.endpoint,data={'data':query},timeout=(15,110),headers={'User-Agent':'NIR-walking-accessibility-pilot/0.1'})
            response.raise_for_status();raw=response.json()
            if raw.get('remark'):raise ValueError('Overpass incomplete response: '+raw['remark'])
            if not isinstance(raw.get('elements'),list) or not raw['elements']:raise ValueError('No OSM elements returned')
            rawpath.write_bytes(response.content);manifest['status']='downloaded';manifest['bytes']=len(response.content);manifest['sha256']=hashlib.sha256(response.content).hexdigest()
        except Exception as e:
            manifest.update(status='failed_not_empty_dataset',error=f'{type(e).__name__}: {e}');dump(a.output/'fetch-manifest.json',manifest);raise
        dump(a.output/'fetch-manifest.json',manifest)
    raw=json.loads(rawpath.read_text(encoding='utf-8'));print(json.dumps(build(raw,a.output),ensure_ascii=False))

if __name__=='__main__':main()
