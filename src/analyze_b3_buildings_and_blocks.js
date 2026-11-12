/*
  Reproducible descriptive audit for B3 (walk + public transport).

  No routes are recalculated.  The script matches Urban API residential
  records to B3 origin_id by the exact export order documented in
  export_urban_residential_geojson.py, and aggregates the existing block CSV.
  It deliberately reports associations, not causal effects.
*/
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const RAW = path.join(ROOT, 'data', 'urban-api-spb-buildings-20261109');
const B3 = path.join(ROOT, 'results', 'blocksnet-b3-directions-citywide-20261112');
const BLOCKS = path.join(ROOT, 'results', 'age-profiles-blocks-b3-20261112', 'age_profiles_by_block.csv');
const OUT = path.join(ROOT, 'results', 'b3-built-form-and-block-profiles-20261113');
const num = x => x === '' || x == null ? NaN : Number(String(x).replace(',', '.'));
function csv(line) { // B3 CSVs contain quoted names only in the block input; this parser handles both.
  const a=[]; let q=false, s=''; for (let i=0;i<line.length;i++) { const c=line[i];
    if (c==='"') { if(q && line[i+1]==='"') {s+='"'; i++;} else q=!q; }
    else if(c===','&&!q){a.push(s);s='';} else s+=c;
  } a.push(s); return a;
}
function median(a){a=a.filter(Number.isFinite).sort((x,y)=>x-y); if(!a.length)return NaN; const m=a.length>>1; return a.length%2?a[m]:(a[m-1]+a[m])/2;}
function mean(a){a=a.filter(Number.isFinite);return a.length?a.reduce((x,y)=>x+y,0)/a.length:NaN;}
function quantile(a,p){a=a.filter(Number.isFinite).sort((x,y)=>x-y); if(!a.length)return NaN; return a[Math.round((a.length-1)*p)];}
function stat(a){return {n:a.filter(Number.isFinite).length,mean:+mean(a).toFixed(3),median:+median(a).toFixed(3),p25:+quantile(a,.25).toFixed(3),p75:+quantile(a,.75).toFixed(3)};}
function ranks(a){ const o=a.map((v,i)=>({v,i})).filter(x=>Number.isFinite(x.v)).sort((x,y)=>x.v-y.v); const r=Array(a.length).fill(NaN); for(let i=0;i<o.length;){let j=i+1;while(j<o.length&&o[j].v===o[i].v)j++; const z=(i+j+1)/2; for(let k=i;k<j;k++)r[o[k].i]=z;i=j;}return r; }
function corr(x,y){let n=0,sx=0,sy=0,sxx=0,syy=0,sxy=0;for(let i=0;i<x.length;i++)if(Number.isFinite(x[i])&&Number.isFinite(y[i])){n++;sx+=x[i];sy+=y[i];sxx+=x[i]*x[i];syy+=y[i]*y[i];sxy+=x[i]*y[i];}const d=Math.sqrt((n*sxx-sx*sx)*(n*syy-sy*sy));return {n,r:d?(n*sxy-sx*sy)/d:NaN};}
function spearman(items,feature,outcome,within=false){
  const clean=items.filter(x=>Number.isFinite(x[feature])&&Number.isFinite(x[outcome]));
  let x=ranks(clean.map(x=>x[feature])),y=ranks(clean.map(x=>x[outcome]));
  if(within){const g={};clean.forEach((v,i)=>(g[v.territory]??=[]).push(i)); for(const a of Object.values(g)){if(a.length<3)continue;const mx=mean(a.map(i=>x[i])),my=mean(a.map(i=>y[i]));a.forEach(i=>{x[i]-=mx;y[i]-=my;});}}
  const z=corr(x,y);return {n:z.n,rho:+z.r.toFixed(3)};
}
function group(v){ if(!Number.isFinite(v)) return 'missing'; if(v<1918)return 'до 1918'; if(v<1961)return '1918–1960'; if(v<1991)return '1961–1990'; return '1991+'; }
function floorGroup(v){ if(!Number.isFinite(v))return 'missing'; return v<=5?'1–5':v<=9?'6–9':'10+'; }

fs.mkdirSync(OUT,{recursive:true});
const manifest=JSON.parse(fs.readFileSync(path.join(RAW,'manifest.json'),'utf8'));
const homes=[];
for(const page of manifest.pages){
  const rows=JSON.parse(fs.readFileSync(path.join(RAW,page.file),'utf8')).results;
  for(const r of rows) if(r.physical_object_type?.physical_object_type_id===4){
    const b=r.building||{}, p=b.properties||{};
    homes.push({year:num(b.built_year??p.building_year),floors:num(b.floors??p.storeys_count),
      residents:num(p.resident_number??p.population_balanced),living:num(p.living_area_official??p.living_area),
      area:num(b.building_area_official??p.area_total),territory:r.territory?.name||'missing'});
  }
}
if(homes.length!==30611) throw Error(`Expected 30611 homes, got ${homes.length}`);
for(const h of homes) Object.assign(h,{n7:[],n13:[],t7:[],t13:[],covered:0});
const dirs=fs.readdirSync(B3,{withFileTypes:true}).filter(x=>x.isDirectory()&&x.name.startsWith('area_'));
for(const d of dirs){
 const lines=fs.readFileSync(path.join(B3,d.name,'b3-by-origin.csv'),'utf8').trim().split(/\r?\n/); const header=csv(lines[0]);
 const ix=Object.fromEntries(header.map((x,i)=>[x,i]));
 for(let k=1;k<lines.length;k++){const r=csv(lines[k]), h=homes[+r[ix.origin_id]]; if(r[ix.network_covered]!=='True')continue;
   h.covered++; h.n7.push(num(r[ix.age_7_N_venue_proxy_within_30min])); h.n13.push(num(r[ix.age_13_N_venue_proxy_within_30min]));
   h.t7.push(num(r[ix.age_7_nearest_minutes]));h.t13.push(num(r[ix.age_13_nearest_minutes]));
 }
}
for(const h of homes){h.mean_n7=mean(h.n7);h.mean_n13=mean(h.n13);h.mean_t7=mean(h.t7);h.mean_t13=mean(h.t13);h.delta_n=h.mean_n13-h.mean_n7;}
function summaryBy(label,fn){const groups={}; for(const h of homes){const k=fn(h);(groups[k]??=[]).push(h);} return Object.entries(groups).map(([k,a])=>({[label]:k,buildings:a.length,covered_all_directions:a.filter(x=>x.covered===dirs.length).length,mean_N7:+mean(a.map(x=>x.mean_n7)).toFixed(2),mean_N13:+mean(a.map(x=>x.mean_n13)).toFixed(2),mean_delta_N13_N7:+mean(a.map(x=>x.delta_n)).toFixed(2),median_nearest_7:+median(a.map(x=>x.mean_t7)).toFixed(2),median_nearest_13:+median(a.map(x=>x.mean_t13)).toFixed(2)})).sort((a,b)=>String(a[label]).localeCompare(String(b[label]),'ru'));}
const building={year:summaryBy('period',h=>group(h.year)),floors:summaryBy('floors_group',h=>floorGroup(h.floors))};
const associations=['year','floors','residents','living','area'].map(feature=>({feature,
  N7:spearman(homes,feature,'mean_n7'),N13:spearman(homes,feature,'mean_n13'),
  delta_N13_N7:spearman(homes,feature,'delta_n'),
  within_territory_N7:spearman(homes,feature,'mean_n7',true),within_territory_N13:spearman(homes,feature,'mean_n13',true)}));

const lines=fs.readFileSync(BLOCKS,'utf8').trim().split(/\r?\n/), head=csv(lines[0]), bi=Object.fromEntries(head.map((x,i)=>[x,i])), blocks=new Map();
for(let k=1;k<lines.length;k++){const r=csv(lines[k]),id=r[bi.blocksnet_block_id]; let b=blocks.get(id); if(!b){b={id,n:[],n7:[],n13:[],d:[],t:[]};blocks.set(id,b);} b.n.push(num(r[bi.n_valid]));b.n7.push(num(r[bi.median_N7]));b.n13.push(num(r[bi.median_N13]));b.d.push(num(r[bi.median_delta_N]));b.t.push(num(r[bi.median_delta_t]));}
const br=[...blocks.values()].map(b=>({id:b.id,origins:median(b.n),N7:mean(b.n7),N13:mean(b.n13),delta:mean(b.d),delta_t:mean(b.t)})).filter(b=>b.origins>=3);
const q7=quantile(br.map(x=>x.N7),.5), q13=quantile(br.map(x=>x.N13),.5), qd=quantile(br.map(x=>x.delta),.75);
for(const b of br) b.profile=b.N7>=q7&&b.N13>=q13?'широкое предложение':b.delta>=qd?'возрастное расширение':b.N7<q7&&b.N13<q13?'слабое предложение':'смешанный профиль';
const profiles={}; for(const b of br)(profiles[b.profile]??=[]).push(b);
const blockSummary=Object.entries(profiles).map(([profile,a])=>({profile,blocks:a.length,share_pct:+(100*a.length/br.length).toFixed(1),median_origins:+median(a.map(x=>x.origins)).toFixed(1),mean_N7:+mean(a.map(x=>x.N7)).toFixed(2),mean_N13:+mean(a.map(x=>x.N13)).toFixed(2),mean_delta_N13_N7:+mean(a.map(x=>x.delta)).toFixed(2)}));
const report={purpose:'Descriptive B3 audit: existing walk+public-transport results only; no route recalculation.',inputs:{residential_buildings:homes.length,b3_directions:dirs.length,network_covered_all_directions:homes.filter(x=>x.covered===dirs.length).length,blocks_total:blocks.size,blocks_with_3plus_residential_origins:br.length,attribute_missing:{year:homes.filter(x=>!Number.isFinite(x.year)).length,floors:homes.filter(x=>!Number.isFinite(x.floors)).length,residents:homes.filter(x=>!Number.isFinite(x.residents)).length,living_area:homes.filter(x=>!Number.isFinite(x.living)).length,building_area:homes.filter(x=>!Number.isFinite(x.area)).length}},building_associations:building,rank_associations:associations,candidate_block_profiles:blockSummary,decision_rule:{wide:'N7 and N13 at or above city medians',age_expansion:'upper quartile of N13−N7; assigned after wide',weak:'both below city medians',mixed:'remaining blocks'},interpretation_of_rank_associations:'Spearman rho is descriptive. “within_territory” demeans global ranks within the Urban API municipal-territory field; it reduces, but does not remove, spatial confounding and is not a causal model.',limitations:['Urban API supplies point locations, not entrances or footprints; missing building attributes are not imputed.','Building associations are origin-level descriptive comparisons; they are confounded by location and do not establish a causal effect of built form.','Block profiles aggregate 43 published directions equally; they measure observable offer proxies, not participation, capacity, price, timetable, safety or independent child mobility.','The public-transport scenario is a model assumption (including its waiting/transfer representation), not observed journeys.','Profiles are rule-based candidates, not validated clusters; they require sensitivity tests for time budgets, destination completeness and spatial aggregation before use as a definitive typology.']};
fs.writeFileSync(path.join(OUT,'summary.json'),JSON.stringify(report,null,2),'utf8');
fs.writeFileSync(path.join(OUT,'building_b3_associations.json'),JSON.stringify(building,null,2),'utf8');
fs.writeFileSync(path.join(OUT,'block_candidate_profiles.csv'),'blocksnet_block_id,profile,n_origins_median_across_directions,mean_N7,mean_N13,mean_delta_N13_N7,mean_delta_nearest_minutes\n'+br.map(x=>[x.id,x.profile,x.origins,x.N7,x.N13,x.delta,x.delta_t].join(',')).join('\n'),'utf8');
fs.writeFileSync(path.join(OUT,'README.md'),'# B3: здания и профили кварталов\n\nРезультат — описательный аудит уже рассчитанного сценария B3 (пешком + общественный транспорт) для 7 и 13 лет. Маршрутизация не повторялась. `summary.json` — таблицы связей признаков здания с доступностью; `block_candidate_profiles.csv` — кандидатная, правиловая группировка кварталов. Это не причинная модель и не валидированная типология; ограничения перечислены в `summary.json`.\n','utf8');
console.log(JSON.stringify(report,null,2));
