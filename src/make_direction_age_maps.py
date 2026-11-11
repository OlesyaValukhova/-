import json
from pathlib import Path
import geopandas as gpd
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT=Path('results/blocksnet-b1-study-areas-citywide-20261111')
OUT=Path('results/direction-age-maps-b1-20261111')
ORIG=Path('data/urban-api-spb-residential-20261110/residential.geojson')
AREAS={'81':'Программирование','38':'Изобразительное искусство'}
COLORS={'both':'#2c7fb8','only_7':'#41ab5d','only_13':'#fdae61','neither':'#d9d9d9','uncovered':'#54278f','unknown':'#252525'}
LABELS={'both':'есть для обоих','only_7':'только 7 лет','only_13':'только 13 лет','neither':'не найдено для обоих','uncovered':'нет сетевого покрытия','unknown':'неизвестно'}
def main():
 OUT.mkdir(exist_ok=True)
 o=gpd.read_file(ORIG)[['geometry']].reset_index(drop=True); o['origin_id']=o.index.astype(str)
 allrows=[]; stats=[]
 for aid,name in AREAS.items():
  d=pd.read_csv(ROOT/f'area_{aid}'/'b1-by-origin.csv',dtype={'origin_id':str})
  x=o.merge(d,on='origin_id',how='left',validate='one_to_one')
  a=x['age_7_N_venue_proxy_within_30min']; b=x['age_13_N_venue_proxy_within_30min']
  x['category']='unknown'; x.loc[x.network_covered.eq(False),'category']='uncovered'
  valid=x.network_covered.eq(True)&a.notna()&b.notna()
  x.loc[valid&(a>0)&(b>0),'category']='both'; x.loc[valid&(a>0)&(b==0),'category']='only_7';x.loc[valid&(a==0)&(b>0),'category']='only_13';x.loc[valid&(a==0)&(b==0),'category']='neither'
  x['study_area_id']=aid;x['study_area_name']=name
  for cat in LABELS:
   n=int((x.category==cat).sum()); stats.append({'study_area_id':aid,'study_area_name':name,'category':cat,'n_origins':n,'share_all_pct':round(n/len(x)*100,2),'share_valid_pct':round(n/valid.sum()*100,2) if cat not in ('uncovered','unknown') else None})
  fig,ax=plt.subplots(figsize=(9,9)); x=x.to_crs(3857)
  for cat in ['neither','only_13','only_7','both','uncovered','unknown']:
   s=x[x.category==cat]; ax.scatter(s.geometry.x,s.geometry.y,s=1.4,c=COLORS[cat],linewidths=0,rasterized=True)
  ax.set_axis_off();ax.set_title(f'{name}: доступность опубликованной координаты\nB1, пешком, 30 минут; 7/13 лет')
  ax.legend([Line2D([0],[0],marker='o',color='w',markerfacecolor=COLORS[c],markersize=6) for c in LABELS],[LABELS[c] for c in LABELS],loc='lower left',fontsize=8,frameon=True)
  fig.text(.01,.01,'Navigator: сохранённая выгрузка 09.11.2026; жилые точки Urban API. 30 224/30 611 подключены к сети.',fontsize=6)
  fig.savefig(OUT/f'B1-30min-{aid}.png',dpi=220,bbox_inches='tight');plt.close(fig)
  allrows.append(x[['origin_id','study_area_id','study_area_name','network_covered','age_7_N_venue_proxy_within_30min','age_13_N_venue_proxy_within_30min','category','geometry']])
 gpd.GeoDataFrame(pd.concat(allrows,ignore_index=True),crs=3857).to_crs(4326).to_file(OUT/'direction_age_categories.gpkg',layer='direction_age_30min',driver='GPKG')
 pd.DataFrame(stats).to_csv(OUT/'category-summary.csv',index=False,encoding='utf-8-sig')
 (OUT/'README.md').write_text('# B1: возрастные категории направлений\n\nСм. исходное ТЗ и методические ограничения в `results/conference-direction-comparison-20261111/REPORT.md`. Категории рассчитаны по числу уникальных координат внутри направления; непокрытые точки не входят в доли четырёх содержательных классов.\n',encoding='utf8')
if __name__=='__main__':main()
