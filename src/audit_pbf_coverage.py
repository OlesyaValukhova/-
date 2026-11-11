"""Audit whether a local OSM PBF covers the supplied origin points."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import geopandas as gpd
import osmium
from pyproj import Transformer

class Bounds(osmium.SimpleHandler):
    def __init__(self):
        super().__init__(); self.minlon=self.minlat=float('inf'); self.maxlon=self.maxlat=float('-inf'); self.nodes=0
    def node(self,n):
        self.nodes += 1; self.minlon=min(self.minlon,n.location.lon); self.maxlon=max(self.maxlon,n.location.lon); self.minlat=min(self.minlat,n.location.lat); self.maxlat=max(self.maxlat,n.location.lat)

def main():
    p=argparse.ArgumentParser(); p.add_argument('--pbf',type=Path,required=True); p.add_argument('--origins',type=Path,required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--crs',type=int,default=32636); a=p.parse_args()
    h=Bounds(); h.apply_file(str(a.pbf),locations=False)
    g=gpd.read_file(a.origins).to_crs(a.crs); tr=Transformer.from_crs(4326,a.crs,always_xy=True); minx,miny=tr.transform(h.minlon,h.minlat); maxx,maxy=tr.transform(h.maxlon,h.maxlat)
    inside=(g.geometry.x.between(minx,maxx)&g.geometry.y.between(miny,maxy)); out={'pbf_nodes':h.nodes,'bounds_wgs84':[h.minlon,h.minlat,h.maxlon,h.maxlat],'bounds_projected':[minx,miny,maxx,maxy],'origins':len(g),'origins_inside_bbox':int(inside.sum()),'origins_outside_bbox':int((~inside).sum())}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8'); print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__': main()
