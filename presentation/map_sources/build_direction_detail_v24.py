import pandas as pd, html
D=pd.read_csv('direction_summary.csv',dtype={'study_area_id':str});assert len(D)==43 and D.study_area_id.is_unique
D['delta']=D.age7_zero_pct_30min-D.age13_zero_pct_30min;D=D.sort_values('delta').reset_index(drop=True)
assert D.origins_network_covered.nunique()==1 and D.origins_network_covered.iloc[0]==30224
f=lambda v:format(v,'.2f').replace('.',',')
rows=[]
for i,r in D.iterrows():
 a=100-r.age7_zero_pct_30min;b=100-r.age13_zero_pct_30min;delta=r.delta
 sign='+' if delta>0 else '−' if delta<0 else ''
 cls="up" if delta>0 else "down"
 rows.append(f'<tr><td>{i+1}</td><th scope="row">{html.escape(r.study_area_name)}</th><td>{f(a)}%</td><td>{f(b)}%</td><td class="{cls}">{sign}{f(abs(delta))} п.п.</td></tr>')
head='''<details id="direction-detail" class="direction-detail" hidden><summary>Расшифровать 43 столбца графика</summary><p>Каждая строка соответствует столбцу графика слева направо. B1: 30 минут пешком; доля среди 30 224 жилых точек с сетевым покрытием, для которых найдена хотя бы одна опубликованная координата. Разница = доля для 13 лет минус доля для 7 лет. Значения округлены до сотых; п.п. — процентные пункты.</p><div class="table-scroll"><table><thead><tr><th scope="col">№</th><th scope="col">Направление</th><th scope="col">7 лет</th><th scope="col">13 лет</th><th scope="col">Разница</th></tr></thead><tbody>'''
foot='''</tbody></table></div><p>Срез опубликованных координат и возрастных допусков, не доля детей и не наличие свободных мест. Источник: <a href="https://github.com/OlesyaValukhova/-/blob/master/results/conference-direction-comparison-20261111/b1-direction-summary.csv">расчёт B1 по направлениям</a>.</p></details>'''
open('direction_detail_v24.html','w').write(head+''.join(rows)+foot)
print('rows',len(rows),'negative',sum(D.delta<0),'positive',sum(D.delta>0),'range',D.delta.min(),D.delta.max())
