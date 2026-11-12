import json,math,pandas as pd,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.collections import PatchCollection
from make_research_maps import polygon_path,LABELS,FIELDS
COLORS=["#315B78", "#C67C27", "#3A7555", "#9EADB6", "#606A70", "#785F4E"]
j=json.load(open('blocks.json'))['features']; ds=[pd.read_csv('b1_38.csv',dtype={'blocksnet_block_id':str}).set_index('blocksnet_block_id'),pd.read_csv('b1_81.csv',dtype={'blocksnet_block_id':str}).set_index('blocksnet_block_id')]
coords=[p for f in j for poly in f['geometry']['coordinates'] for p in poly[0]];xs,ys=zip(*coords); bounds=(min(xs),max(xs),min(ys),max(ys))
def draw(i,delta,out):
 d=ds[i];colors=['#A54530','#D08372','#C2CACA','#80AABC','#315B78','#606A70'] if delta else COLORS
 labels=['Меньше −2','От −2 до < 0','0','Больше 0 до 2','Больше 2','Меньше 3 точек / нет данных'] if delta else ['Для обоих возрастов','Только для 7 лет','Только для 13 лет','Нет координат для обоих','Меньше 3 точек / нет данных','Равенство состояний']
 bucket=[[] for _ in colors]
 for f in j:
  k=f['properties']['blocksnet_block_id'];r=d.loc[k] if k in d.index else None
  if r is None or r.n_valid<3: ix=5 if delta else 4
  elif delta:
   v=r.median_delta_N;ix=5 if pd.isna(v) else 0 if v < -2 else 1 if v < 0 else 2 if v == 0 else 3 if v<=2 else 4
  else:
   v=[r[x] for x in FIELDS];mx=max(v); wins=[n for n,x in enumerate(v) if abs(x-mx)<1e-7];ix=wins[0] if len(wins)==1 else 5
  for poly in f['geometry']['coordinates']:bucket[ix].append(polygon_path(poly))
 fig=plt.figure(figsize=(16,6.25),facecolor='white'); ax=fig.add_axes([.00,.01,.70,.98])
 for n,patches in enumerate(bucket):ax.add_collection(PatchCollection(patches,facecolor=colors[n],edgecolor='white',linewidth=.12))
 ax.set_xlim(bounds[:2]);ax.set_ylim(bounds[2:]);ax.set_aspect('equal');ax.axis('off')
 fig.text(.72,.87,'Медиана N13 − N7' if delta else 'Преобладающее состояние',fontsize=16,color='#25313A');fig.text(.72,.81,'опубликованных координат' if delta else 'среди жилых точек квартала',fontsize=12,color='#566771')
 fig.legend(handles=[Patch(facecolor=colors[n],label=labels[n]) for n in range(6)],loc='upper left',frameon=False,fontsize=12,bbox_to_anchor=(.72,.76),labelspacing=.75,handlelength=1.3)
 if delta:
  fig.text(.72,.31,'B1 · пешком · 30 минут',fontsize=12,color='#25313A')
  fig.text(.72,.24,'N — число достижимых координат.\nНоль включает отсутствие координат.',fontsize=10,color='#566771',va='top')
 else:
  fig.text(.72,.33,'Доступна ≥1 координата · B1',fontsize=11,color='#25313A')
  n=d.n_valid.sum(); vals=[((d.both_pct+d.only_7_pct)*d.n_valid).sum()/n, ((d.both_pct+d.only_13_pct)*d.n_valid).sum()/n]; vals=[round(v,1) for v in vals]
  chart=fig.add_axes([.745,.065,.195,.20]);chart.barh([1,0],vals,color=['#315B78','#315B78'],height=.44);chart.set_xlim(0,112);chart.set_yticks([1,0],['7 лет','13 лет']);chart.set_xticks([]);chart.tick_params(axis='y',length=0,labelsize=11);chart.spines[['top','left','right','bottom']].set_visible(False)
  for rownum,v in enumerate(vals):chart.text(v+3,1-rownum,str(v).replace('.',',')+'%',va='center',fontsize=11,fontweight='bold',color='#25313A')

 x0=bounds[0]+(bounds[1]-bounds[0])*.05;y0=bounds[2]+(bounds[3]-bounds[2])*.04;ax.plot([x0,x0+10000],[y0,y0],color='#33454f',lw=2);ax.text(x0+5000,y0+(bounds[3]-bounds[2])*.012,'10 км',ha='center',fontsize=9,color='#33454f')
 fig.savefig(out,dpi=150,facecolor='white');plt.close(fig)
draw(1,False,'map19_program.png');draw(0,False,'map19_art.png');draw(1,True,'map19_delta.png')
