#!/usr/bin/env node
// Rebuild a numbered locator map from the committed OSM district GeoJSON.
// The map is context only; it does not calculate or aggregate B1 indicators.
import fs from "node:fs";
import path from "node:path";
const here=path.dirname(new URL(import.meta.url).pathname);
const source=path.join(here,"spb_district_boundaries_v42.geojson");
const output=path.join(here,"..","assets_v44","district_locator_v44.svg");
const data=JSON.parse(fs.readFileSync(source,"utf8"));
if(data.crs?.properties?.name!=="EPSG:32636")throw new Error("District source must use EPSG:32636");
function ringStats(ring){let a2=0,cx=0,cy=0;for(let i=0;i<ring.length-1;i++){const [x1,y1]=ring[i],[x2,y2]=ring[i+1],cr=x1*y2-x2*y1;a2+=cr;cx+=(x1+x2)*cr;cy+=(y1+y2)*cr;}if(Math.abs(a2)<1e-6){const pts=ring.slice(0,-1);return{area:0,x:pts.reduce((s,p)=>s+p[0],0)/pts.length,y:pts.reduce((s,p)=>s+p[1],0)/pts.length};}return{area:Math.abs(a2/2),x:cx/(3*a2),y:cy/(3*a2)};}
function inRing(p,ring){let inside=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const [xi,yi]=ring[i],[xj,yj]=ring[j];if(((yi>p.y)!==(yj>p.y))&&(p.x<(xj-xi)*(p.y-yi)/(yj-yi+1e-20)+xi))inside=!inside;}return inside;}
function inPolygon(p,poly){if(!inRing(p,poly[0]))return false;for(let i=1;i<poly.length;i++)if(inRing(p,poly[i]))return false;return true;}
function labelPoint(feature){const polys=feature.geometry.coordinates.map(poly=>({poly,stats:ringStats(poly[0])})).sort((a,b)=>b.stats.area-a.stats.area);for(const item of polys){const{poly,stats}=item,p={x:stats.x,y:stats.y};if(inPolygon(p,poly))return p;const xs=poly[0].map(q=>q[0]),ys=poly[0].map(q=>q[1]),minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);let best=null,bestD=Infinity;for(let iy=1;iy<30;iy++)for(let ix=1;ix<30;ix++){const q={x:minX+(maxX-minX)*ix/30,y:minY+(maxY-minY)*iy/30};if(inPolygon(q,poly)){const d=(q.x-stats.x)**2+(q.y-stats.y)**2;if(d<bestD){best=q;bestD=d;}}}if(best)return best;}const p=polys[0].poly[0][0];return{x:p[0],y:p[1]};}
const features=data.features.slice().sort((a,b)=>a.properties.name.localeCompare(b.properties.name,"ru"));
if(features.length!==18||new Set(features.map(f=>f.properties.osm_id)).size!==18)throw new Error("Expected 18 unique districts");
const coords=[];for(const f of features)for(const poly of f.geometry.coordinates)for(const ring of poly)for(const p of ring)coords.push(p);
const minX=Math.min(...coords.map(p=>p[0])),maxX=Math.max(...coords.map(p=>p[0])),minY=Math.min(...coords.map(p=>p[1])),maxY=Math.max(...coords.map(p=>p[1]));
const W=760,H=660,M=28,scale=Math.min((W-2*M)/(maxX-minX),(H-2*M)/(maxY-minY)),ox=(W-(maxX-minX)*scale)/2,oy=(H-(maxY-minY)*scale)/2;
const xy=p=>[ox+(p[0]-minX)*scale,H-oy-(p[1]-minY)*scale];
const pathMarkup=features.map((f,i)=>{const d=f.geometry.coordinates.map(poly=>poly.map(ring=>ring.map((p,j)=>{const[x,y]=xy(p);return`${j?"L":"M"}${x.toFixed(1)},${y.toFixed(1)}`;}).join(" ")+" Z").join(" ")).join(" ");return`<path d="${d}" fill="${i%2?"#F2F5F5":"#E9EFF0"}" fill-rule="evenodd" stroke="#71838B" stroke-width="1.35" stroke-linejoin="round"/>`;}).join("");
const labels=features.map((f,i)=>{const p=labelPoint(f);return{i:i+1,name:f.properties.name,point:xy([p.x,p.y])};});
const placed=[],offsets=[[0,0]];for(let r=22;r<=210;r+=18)for(let a=0;a<360;a+=15){const rad=a*Math.PI/180;offsets.push([Math.cos(rad)*r,Math.sin(rad)*r]);}
for(const l of labels){let chosen=null,best=null,bestDistance=-1,bestCost=Infinity;for(const off of offsets){const x=l.point[0]+off[0],y=l.point[1]+off[1];if(x<18||x>W-18||y<18||y>H-18)continue;const d=placed.length?Math.min(...placed.map(p=>Math.hypot(p.x-x,p.y-y))):999,cost=Math.hypot(...off);if(d>bestDistance||(d===bestDistance&&cost<bestCost)){best={x,y,off,d};bestDistance=d;bestCost=cost;}if(d>=34){chosen={x,y,off,d};break;}}l.label=chosen||best||{x:l.point[0],y:l.point[1],off:[0,0],d:0};placed.push({x:l.label.x,y:l.label.y});}
const leaders=labels.filter(l=>Math.hypot(...l.label.off)>5).map(l=>`<line x1="${l.point[0].toFixed(1)}" y1="${l.point[1].toFixed(1)}" x2="${l.label.x.toFixed(1)}" y2="${l.label.y.toFixed(1)}" stroke="#A94F3E" stroke-width="1.2"/>`).join("");
const markers=labels.map(l=>`<g><circle cx="${l.label.x.toFixed(1)}" cy="${l.label.y.toFixed(1)}" r="14" fill="#315B78" stroke="#FFFFFF" stroke-width="2"/><text x="${l.label.x.toFixed(1)}" y="${(l.label.y+4.5).toFixed(1)}" text-anchor="middle" font-family="Arial,sans-serif" font-size="12" font-weight="700" fill="#FFFFFF">${l.i}</text></g>`).join("");
const barLen=10000*scale,barX=34,barY=H-34;
const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="760" height="660" viewBox="0 0 760 660" role="img" aria-labelledby="title desc">
<title id="title">Карта-указатель 18 административных районов Санкт-Петербурга</title>
<desc id="desc">Контекстная карта административных районов OpenStreetMap. Номера на карте соответствуют списку районов справа на слайде. Районы не являются единицами расчёта B1.</desc>
<rect width="760" height="660" fill="#FFFFFF"/>
<g>${pathMarkup}</g>
<g>${leaders}</g>
<g>${markers}</g>
<g fill="#315B78" font-family="Arial,sans-serif">
<text x="${barX}" y="${barY-10}" font-size="13">10 км</text>
<line x1="${barX}" y1="${barY}" x2="${barX+barLen}" y2="${barY}" stroke="#315B78" stroke-width="3"/>
</g>
<text x="34" y="646" font-family="Arial,sans-serif" font-size="10" fill="#66757C">EPSG:32636 · контекстный слой · OSM, 17.11.2026</text>
</svg>`;
const distances=labels.flatMap((a,i)=>labels.slice(i+1).map(b=>Math.hypot(a.label.x-b.label.x,a.label.y-b.label.y)));
const minLabelSpacing=distances.length?Math.min(...distances):0;
if(!Number.isFinite(minLabelSpacing)||minLabelSpacing<30)throw new Error("District number markers overlap: minimum spacing "+minLabelSpacing);
const audit={
  version:"v44",
  source:"presentation/map_sources/spb_district_boundaries_v42.geojson",
  source_date:"2026-11-17",
  crs:"EPSG:32636",
  license:"ODbL 1.0; attribution: © OpenStreetMap contributors",
  role:"geographic orientation only; not an analytical unit and not used to aggregate B1 values",
  map:{width:W,height:H,scale_bar_m:10000,bbox_epsg32636:[minX,minY,maxX,maxY]},
  label_order:"alphabetical by Russian district name",
  label_count:labels.length,
  minimum_marker_spacing_px:Number(minLabelSpacing.toFixed(2)),
  districts:labels.map(l=>({number:l.i,name:l.name,osm_id:features[l.i-1].properties.osm_id,anchor:[Number(l.point[0].toFixed(1)),Number(l.point[1].toFixed(1))],label:[Number(l.label.x.toFixed(1)),Number(l.label.y.toFixed(1))],leader_line:Math.hypot(...l.label.off)>5}))
};
const auditPath=path.join(here,"district_locator_audit_v44.json");
fs.mkdirSync(path.dirname(output),{recursive:true});
fs.writeFileSync(output,svg,"utf8");
fs.writeFileSync(auditPath,JSON.stringify(audit,null,2)+"\\n","utf8");
console.log(JSON.stringify({output,auditPath,feature_count:features.length,label_count:labels.length,minLabelSpacing:Number(minLabelSpacing.toFixed(2))}));
