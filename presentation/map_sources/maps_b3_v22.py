import json, math
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.collections import PatchCollection
from make_research_maps import polygon_path

features=json.load(open('blocks.json'))['features']
frames={name:pd.read_csv(path,dtype={'blocksnet_block_id':str}).set_index('blocksnet_block_id',verify_integrity=True) for name,path in [('program','data1.csv'),('art','data0.csv')]}
fields=['both_pct','only_7_pct','only_13_pct','neither_pct']
xy=[p for f in features for poly in f['geometry']['coordinates'] for p in poly[0]]; xs,ys=zip(*xy);bounds=(min(xs),max(xs),min(ys),max(ys))
statecolors=['#315b78','#c0802c','#148543','#a6b7be','#735d4e','#707a80','#404a52']
statelabels=['Оба возраста','Только 7 лет','Только 13 лет','Ни один возраст','Равные доли состояний','1–2 валидные точки','Нет результата / совпадения']
deltacolors=['#a54530','#ce8979','#c0cbcb','#81aabc','#315b78','#707a80','#404a52']
deltalabels=['Меньше −2','От −2 до меньше 0','0','Больше 0 до 2','Больше 2','1–2 валидные точки','Нет результата / совпадения']

def draw(name, delta=False):
 d=frames[name]; buckets=[[] for i in range(7)]; classes=[0]*7
 for f in features:
  k=str(f['properties']['blocksnet_block_id']);r=d.loc[k] if k in d.index else None
  if r is None or pd.isna(r.n_valid) or r.n_valid==0: ix=6
  elif r.n_valid<3: ix=5
  elif delta:
   v=r.median_delta_N
   ix=6 if pd.isna(v) else 0 if v < -2 else 1 if v < 0 else 2 if v == 0 else 3 if v<=2 else 4
  else:
   vals=[r[k] for k in fields]
   if any(pd.isna(v) for v in vals): ix=6
   else:
    mx=max(vals); winners=[i for i,v in enumerate(vals) if abs(v-mx)<1e-7];ix=winners[0] if len(winners)==1 else 4
  classes[ix]+=1
  for poly in f['geometry']['coordinates']: buckets[ix].append(polygon_path(poly))
 colors=deltacolors if delta else statecolors;labels=deltalabels if delta else statelabels
 fig=plt.figure(figsize=(16,6.25),facecolor='white');ax=fig.add_axes([.0,.01,.69,.98]);
 for i,paths in enumerate(buckets): ax.add_collection(PatchCollection(paths,facecolor=colors[i],edgecolor='white',linewidth=.14))
 ax.set_xlim(bounds[:2]);ax.set_ylim(bounds[2:]);ax.set_aspect('equal');ax.axis('off')
 fig.text(.71,.91,'Медиана N13 − N7' if delta else 'Преобладающее состояние',fontsize=16,color='#25313a')
 fig.text(.71,.855,'парная разница по точкам квартала' if delta else 'среди жилых точек квартала',fontsize=11,color='#566771')
 fig.legend(handles=[Patch(facecolor=colors[i],label=labels[i]) for i in range(7)],loc='upper left',frameon=False,fontsize=11,bbox_to_anchor=(.71,.82),labelspacing=.53,handlelength=1.2)
 if delta:
  n=sum(classes[:5]); shares=[sum(classes[:2])/n,classes[2]/n,sum(classes[3:5])/n]
  fig.text(.71,.255,f'Кварталы с ≥3 точками · n = {n}',fontsize=11,color='#25313a')
  bar=fig.add_axes([.715,.19,.245,.035]); left=0
  for share,color in zip(shares,['#a54530','#a6b7b7','#315b78']):
   bar.barh([0],[share],left=left,color=color,height=1);left+=share
  bar.set_xlim(0,1);bar.axis('off')
  fig.text(.71,.14,'7% меньше · 36% равно · 57% больше',fontsize=10,color='#25313a')
  fig.text(.71,.09,'Ноль включает отсутствие координат для обоих.',fontsize=9,color='#566771')
 else:
  good=d[d.n_valid>0]; n=good.n_valid.sum(); vals=[((good.both_pct+good.only_7_pct)*good.n_valid).sum()/n,((good.both_pct+good.only_13_pct)*good.n_valid).sum()/n]
  fig.text(.71,.29,'Доля жилых точек с ≥1 координатой',fontsize=11,color='#25313a')
  chart=fig.add_axes([.74,.065,.20,.19]);chart.barh([1,0],vals,color='#315b78',height=.42);chart.set_xlim(0,112);chart.set_yticks([1,0],['7 лет','13 лет']);chart.set_xticks([]);chart.tick_params(axis='y',length=0,labelsize=10);chart.spines[['top','left','right','bottom']].set_visible(False)
  for j,v in enumerate(vals): chart.text(v+3,1-j,f'{v:.1f}'.replace('.',',')+'%',va='center',fontsize=11,fontweight='bold',color='#25313a')
 x0=bounds[0]+(bounds[1]-bounds[0])*.05;y0=bounds[2]+(bounds[3]-bounds[2])*.04;ax.plot([x0,x0+10000],[y0,y0],color='#33454f',lw=2);ax.text(x0+5000,y0+(bounds[3]-bounds[2])*.012,'10 км',ha='center',fontsize=9,color='#33454f')
 output=f'map22_{name}'+('_delta' if delta else '')+'.png';fig.savefig(output,dpi=150,facecolor='white');plt.close(fig);print(output,classes)
for direction in ['program','art']:draw(direction)
draw('program',True)
