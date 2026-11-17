#!/usr/bin/env node
// Build a numbered locator map from the committed OSM district GeoJSON.
// Pure Node.js; no routing, B1 calculation or aggregation is performed.
import fs from "node:fs";
import path from "node:path";
const here=path.dirname(new URL(import.meta.url).pathname);
const source=path.join(here,"spb_district_boundaries_v42.geojson");
const output=path.join(here,"..","assets_v44","district_locator_v44.svg");
const data=JSON.parse(fs.readFileSync(source,"utf8"));
const esc=s=>String(s).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
function ringStats(ring){let a2=0,cx=0,cy=0;for(let i=0;i<ring.length-1;i++){const [x1,y1]=ring[i],[x2,y2]=ring[i+1],cr=x1*y2-x2*y1;a2+=cr;cx+=(x1+x2)*cr;cy+=(y1+y2)*cr;}if(Math.abs(a2)<1e-6){const pts=ring.slice(0,-1);return{area:0,x:pts.reduce((s,p)=>s+p[0],0)/pts.length,y:pts.reduce((s,p)=>s+p[1],0)/pts.length};}return{area:Math.abs(a2/2),x:cx/(3*a2),y:cy/(3*a2)};}
function inRing(p,ring){let inside=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const [xi,yi]=ring[i],[xj,yj]=ring[j];const hit=((yi>p.y)!==(yj>p.y))&&(p.x<(xj-xi)*(p.y-yi)/(yj-yi+1e-20)+xi);if(hit)inside=!inside;}return inside;}
function inPolygon(p,poly){if(!inRing(p,poly[0]))return false;for(let i=1;i<poly.length;i++)if(inRing(p,poly[i]))return false;return true;}
function labelPoint(feature){const polys=feature.geometry.coordinates.map(poly=>({poly,stats:ringStats(poly[0])})).sort((a,b)=>b.stats.area-a.stats.area);for(const item of polys){const{poly,stats}=item;const p={x:stats.x,y:stats.y};if(inPolygon(p,poly))return p;const xs=poly[0].map(q=>q[0]),ys=poly[0].map(q=>q[1]);const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);let best=null,bestD=Infinity;for(let iy=1;iy<24;iy++)for(let ix=1;ix<24;ix++){const q={x:minX+(maxX-minX)*ix/24,y:minY+(maxY-minY)*iy/24};if(inPolygon(q,poly)){const d=(q.x-stats.x)**2+(q.y-stats.y)**2;if(d<bestD){best=q;bestD=d;}}}if(best)return best;}const p=polys[0].poly[0][0];return{x:p[0],y:p[1]};}
const features=data.features.slice().sort((a,b)=>a.properties.name.localeCompare(b.properties.name,"ru"));
if(features.length!==18||new Set(features.map(f=>f.properties.osm_id)).size!==18)throw new Error("Expected 18 unique district features");
const all=[];for(const f of features)for(const poly of f.geometry.coordinates)for(const ring of poly)for(const p of ring)all.push(p);
const minX=Math.min(...all.map(p=>p[0])),maxX=Math.max(...all.map(p=>p[0])),minY=Math.min(...all.map(p=>p[1])),maxY=Math.max(...all.map(p=>p[1]));
const W=760,H=660,M=28,scale=Math.min((W-2*M)/(maxX-minX),(H-2*M)/(maxY-minY)),ox=(W-(maxX-minX)*scale)/2,oy=(H-(maxY-minY)*scale)/2;
const xy=p=>[ox+(p[0]-minX)*scale,H-oy-(p[1]-minY)*scale];
const paths=features.map((f,i)=>{const d=f.geometry.coordinates.map(poly=>poly.map(ring=>ring.map((p,j)=>{const[x,y]=xy(p);return`${j?"L":"M"}${x.toFixed(1)},${y.toFixed(1)}`;}).join(" ")+" Z").join(" ")).join(" ");return`<path d="${d}" fill="${i%2?"#F2F5F5":"#E9EFF0"}" fill-rule="evenodd" stroke="#71838B" stroke-width="1.35" stroke-linejoin="round"/>`;}).join("\\n");
const labels=features.map((f,i)=>({i:i+1,name:f.properties.name,point:xy(labelPoint(f))})),placed=[],offsets=[[0,0],[0,-24],[24,0],[-24,0],[0,24],[24,-24],[-24,-24],[24,24],[-24,24],[0,-48],[48,0],[-48,0],[0,48],[36,-36],[-36,-36],[36,36],[-36,36]];
for(const l of labels){let best=null,bestScore=-Infinity;for(const off of offsets){const x=l.point[0]+off[0],y=l.point[1]+off[1];if(x<16||x>W-16||y<16||y>H-16)continue;const minD=placed.length?Math.min(...placed.map(p=>Math.hypot(p.x-x,p.y-y))):999,score=minD-Math.hypot(...off)*.05;if(score>bestScore){bestScore=score;best={x,y,off,minD};}if(minD>=31&&Math.hypot(...off)<=36)break;}if(!best)best={x:l.point[0],y:l.point[1],off:[0,0],minD:0};l.label=best;placed.push({x:best.x,y:best.y});}
const leader=labels.filter(l=>Math.hypot(...l.label.off)>5).map(l=>`<line x1="${l.point[0].toFixed(1)}" y1="${l.point[1].toFixed(1)}" x2="${l.label.x.toFixed(1)}" y2="${l.label.y.toFixed(1)}" stroke="#A94F3E" stroke-width="1.2"/>`).join("\\n");
const markers=labels.map(l=>`<g><circle cx="${l.label.x.toFixed(1)}" cy="${l.label.y.toFixed(1)}" r="14" fill="#315B78" stroke="#FFFFFF" stroke-width="2"/><text x="${l.label.x.toFixed(1)}" y="${(l.label.y+4.5).toFixed(1)}" text-anchor="middle" font-family="Arial,sans-serif" font-size="12" font-weight="700" fill="#FFFFFF">${l.i}</text></g>`).join("\\n");
const barLen=10000*scale,barX=34,barY=H-34;
const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="760" height="660" viewBox="0 0 760 660" role="img" aria-labelledby="title desc"><title id="title">Карта-указатель 18 административных районов Санкт-Петербурга</title><desc id="desc">Контекстная карта административных районов OpenStreetMap. Номера на карте соответствуют списку справа на слайде. Районы не являются единицами расчёта B1.</desc><rect width="760" height="660" fill="#FFFFFF"/><g>${paths}</g><g>${leader}</g><g>${markers}</g><g fill="#315B78" font-family="Arial,sans-serif"><text x="${barX}" y="${barY-10}" font-size="13">10 км</text><line x1="${barX}" y1="${barY}" x2="${barX+barLen}" y2="${barY}" stroke="#315B78" stroke-width="3"/></g><text x="34" y="646" font-family="Arial,sans-serif" font-size="10" fill="#66757C">EPSG:32636 · контекстный слой · OSM, 17.11.2026</text></svg>`;
fs.mkdirSync(path.dirname(output),{recursive:true});fs.writeFileSync(output,svg+"\\n","utf8");
console.log(JSON.stringify({output,features:features.length,crs:"EPSG:32636",labels:labels.map(l=>({number:l.i,name:l.name,leader:Math.hypot(...l.label.off)>5})),bytes:Buffer.byteLength(svg)}));
