import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
J=json.load(open('building_b3_associations.json',encoding='utf-8'))['year']; d={r['period']:r for r in J}
periods=['до 1918','1918–1960','1961–1990','1991+','missing'];labels=['До 1918','1918–1960','1961–1990','1991 и позже','Год неизвестен']
assert sum(x['buildings'] for x in J)==30611
assert sum(x['covered_all_directions'] for x in J)==30224
fig,ax=plt.subplots(figsize=(16,6.25),facecolor='white');fig.subplots_adjust(left=.22,right=.86,top=.81,bottom=.21)
y=np.arange(len(periods));v7=[d[x]['mean_N7'] for x in periods];v13=[d[x]['mean_N13'] for x in periods]
ax.barh(y-.18,v7,height=.32,color='#315b78',label='7 лет');ax.barh(y+.18,v13,height=.32,color='#b5793d',label='13 лет');ax.invert_yaxis();ax.set_xlim(0,7);ax.xaxis.set_major_locator(MultipleLocator(1));ax.set_axisbelow(True);ax.grid(axis='x',color='#dfe6e6',linewidth=.8);ax.set_yticks(y,labels,fontsize=14,color='#25313a');ax.tick_params(axis='y',length=0,pad=12);ax.tick_params(axis='x',labelsize=11,colors='#526775');ax.spines[['top','right','left']].set_visible(False);ax.spines['bottom'].set_color('#aab8bc')
for i,p in enumerate(periods):
 for val,yy in [(v7[i],i-.18),(v13[i],i+.18)]:ax.text(val+.08,yy,f'{val:.2f}'.replace('.',','),va='center',fontsize=11,color='#25313a')
 ax.text(7.15,i,'n = '+f"{d[p]['covered_all_directions']:,}".replace(',',' '),va='center',fontsize=10,color='#526775',clip_on=False)
fig.text(.05,.93,'Различия по периоду постройки',fontsize=18,color='#25313a')
fig.text(.05,.875,'Среднее число достижимых координат на направление · B3 · 30 минут',fontsize=13,color='#526775')
ax.legend(loc='lower right',bbox_to_anchor=(1.0,1.01),ncol=2,frameon=False,fontsize=12)
fig.text(.05,.09,'Год неизвестен у 9 209 из 30 611 зданий (30,1%); n — здания с сетевым покрытием.',fontsize=11,color='#526775')
fig.text(.05,.045,'Связь описательная: расположение, транспорт и полнота данных смешаны; причинность не установлена.',fontsize=11,color='#526775')
fig.savefig('built_form_v30.png',dpi=150,facecolor='white');print([(p,d[p]['covered_all_directions'],d[p]['mean_N7'],d[p]['mean_N13']) for p in periods])
