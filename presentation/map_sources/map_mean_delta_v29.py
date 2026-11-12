import json, gzip, base64
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.patches import Patch
from make_research_maps import polygon_path

P=Path('blocks.json')
features=json.loads(P.read_text(encoding='utf-8') if P.exists() else gzip.decompress(base64.b64decode(Path('blocks_v22.json.gz.b64').read_bytes())))['features']
D=pd.read_csv('block_candidate_profiles.csv',dtype={'blocksnet_block_id':str}).set_index('blocksnet_block_id',verify_integrity=True)
F=pd.read_csv('data0.csv',dtype={'blocksnet_block_id':str}).set_index('blocksnet_block_id',verify_integrity=True)
xy=[p for f in features for poly in f['geometry']['coordinates'] for p in poly[0]];xs,ys=zip(*xy);bounds=(min(xs),max(xs),min(ys),max(ys))
colors=['#a54530','#a6b7b7','#315b78','#707a80','#404a52']; labels=['Меньше для 13 лет','Разница равна нулю','Больше для 13 лет','1–2 валидные точки','Нет результата / совпадения']
buckets=[[] for i in range(5)];counts=[0]*5
for f in features:
 k=f['properties']['blocksnet_block_id']; base=F.loc[k] if k in F.index else None;r=D.loc[k] if k in D.index else None
 if r is not None and pd.notna(r.mean_delta_N13_N7):
  v=r.mean_delta_N13_N7; ix=0 if v < -1e-9 else 2 if v > 1e-9 else 1
 elif base is not None and 0<base.n_valid<3:ix=3
 else:ix=4
 counts[ix]+=1
 for poly in f['geometry']['coordinates']:buckets[ix].append(polygon_path(poly))
fig=plt.figure(figsize=(16,6.25),facecolor='white');ax=fig.add_axes([0,.01,.69,.98]);
for i,paths in enumerate(buckets):ax.add_collection(PatchCollection(paths,facecolor=colors[i],edgecolor='white',linewidth=.14))
ax.set_xlim(bounds[:2]);ax.set_ylim(bounds[2:]);ax.set_aspect('equal');ax.axis('off')
fig.text(.71,.91,'Возрастная разница',fontsize=16,color='#25313a')
fig.text(.71,.855,'среднее медиан парной разницы по 43 направлениям',fontsize=10.8,color='#566771')
fig.text(.71,.815,'N13 − N7 · B3 · 30 минут',fontsize=11,color='#566771')
fig.legend(handles=[Patch(facecolor=colors[i],label=labels[i]) for i in range(5)],loc='upper left',frameon=False,fontsize=11,bbox_to_anchor=(.71,.77),labelspacing=.65)
n=sum(counts[:3]);shares=[x/n for x in counts[:3]]
fig.text(.71,.39,f'Кварталы с результатом · n = {n}',fontsize=11,color='#25313a')
bar=fig.add_axes([.715,.32,.245,.035]);left=0
for share,color in zip(shares,colors):bar.barh([0],[share],left=left,color=color,height=1);left+=share
bar.set_xlim(0,1);bar.axis('off')
fig.text(.71,.27,' · '.join(f'{v*100:.1f}% {lab}'.replace('.',',') for v,lab in zip(shares,['меньше','равно','больше'])),fontsize=10,color='#25313a')
fig.text(.71,.19,'Среднее по направлениям — не число\nуникальных адресов по всему каталогу.\nНоль не исключает отсутствия предложений.',fontsize=10,color='#566771',va='top')
x0=bounds[0]+(bounds[1]-bounds[0])*.05;y0=bounds[2]+(bounds[3]-bounds[2])*.04;ax.plot([x0,x0+10000],[y0,y0],color='#33454f',lw=2);ax.text(x0+5000,y0+(bounds[3]-bounds[2])*.012,'10 км',ha='center',fontsize=9,color='#33454f')
fig.savefig('map29_mean_delta.png',dpi=150,facecolor='white');print('counts',counts,'n',n,'shares',shares)
