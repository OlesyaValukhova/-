"""Audit Navigator study-area labels against the completed observable offer layer."""
from __future__ import annotations
import argparse, concurrent.futures, csv, hashlib, json, math
from collections import Counter, defaultdict
from pathlib import Path

def num(x):
    try: x=float(x)
    except (TypeError,ValueError): return None
    return x if math.isfinite(x) else None
def coord_id(lon,lat): return 'coordinate-'+hashlib.sha256(f'{lon:.12f},{lat:.12f}'.encode()).hexdigest()[:16]
def read(path):
    try:
        d=json.loads(path.read_bytes()); return d
    except Exception: return None
def main():
    p=argparse.ArgumentParser(); p.add_argument('--details',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    if a.output.exists(): p.error('output must be new')
    files=sorted(a.details.glob('*-detail.json')); stats=Counter(); cats=defaultdict(lambda: {'labelled_cards':0,'with_coordinate':0,'with_age':0,'cards':0,'coords':set(),'age7_cards':0,'age7_coords':set(),'age13_cards':0,'age13_coords':set(),'examples':[]}); pair_rows=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
      for d in ex.map(read,files):
        if d is None: stats['unreadable']+=1; continue
        stats['cards']+=1
        areas=d.get('study_areas') or []; profiles=d.get('profiles') or []; subjects=d.get('subjects') or []
        stats['cards_with_study_area']+=bool(areas); stats['cards_with_profile']+=bool(profiles); stats['cards_with_subject']+=bool(subjects)
        stats['cards_multi_study_area']+=len(areas)>1
        lon,lat,lo,hi=num(d.get('longitude')),num(d.get('latitude')),num(d.get('min_age')),num(d.get('max_age'))
        has_coordinate=lon is not None and lat is not None and -180<=lon<=180 and -90<=lat<=90
        has_age=lo is not None and hi is not None and lo<=hi
        for item in areas:
          ident=item.get('id'); name=str(item.get('display_name') or '').strip()
          if ident is None or not name: stats['malformed_study_area_items']+=1; continue
          key=f'{ident} | {name}'; x=cats[key]; x['labelled_cards']+=1; x['with_coordinate']+=has_coordinate; x['with_age']+=has_age
          if len(x['examples'])<3: x['examples'].append({'program_id':str(d.get('id')),'program_name':str(d.get('name') or ''),'min_age':lo,'max_age':hi,'published_address':str(d.get('address') or '')})
        ok=has_coordinate and has_age
        if not ok: continue
        stats['observable_age_coordinate_cards']+=1; stats['observable_cards_with_study_area']+=bool(areas); stats['observable_cards_multi_study_area']+=len(areas)>1
        cid=coord_id(lon,lat)
        for item in areas:
          ident=item.get('id'); name=str(item.get('display_name') or '').strip()
          if ident is None or not name: stats['malformed_study_area_items']+=1; continue
          key=f'{ident} | {name}'; x=cats[key]; x['cards']+=1; x['coords'].add(cid)
          if lo<=7<=hi: x['age7_cards']+=1; x['age7_coords'].add(cid)
          if lo<=13<=hi: x['age13_cards']+=1; x['age13_coords'].add(cid)
          pair_rows.append({'program_id':str(d.get('id')),'coordinate_id':cid,'study_area_id':ident,'study_area_name':name,'min_age':lo,'max_age':hi})
    a.output.mkdir(parents=True)
    rows=[]
    for key,x in cats.items():
      ident,name=key.split(' | ',1); rows.append({'study_area_id':ident,'study_area_name':name,'labelled_cards_total':x['labelled_cards'],'labelled_cards_with_coordinate':x['with_coordinate'],'labelled_cards_with_age_interval':x['with_age'],'cards':x['cards'],'labelled_cards_missing_coordinate_or_age':x['labelled_cards']-x['cards'],'unique_coordinates':len(x['coords']),'age7_cards':x['age7_cards'],'age7_unique_coordinates':len(x['age7_coords']),'age13_cards':x['age13_cards'],'age13_unique_coordinates':len(x['age13_coords']),'examples':json.dumps(x['examples'],ensure_ascii=False)})
    rows.sort(key=lambda x:(-x['unique_coordinates'],x['study_area_name']))
    for name,fields,data in [('study-area-coverage.csv',list(rows[0]) if rows else [],rows),('observable-card-study-area-pairs.csv',['program_id','coordinate_id','study_area_id','study_area_name','min_age','max_age'],pair_rows)]:
      with (a.output/name).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader();w.writerows(data)
    summary=dict(stats); summary.update({'detail_files_found':len(files),'study_area_categories':len(rows),'categories_with_at_least_10_unique_coordinates':sum(x['unique_coordinates']>=10 for x in rows),'categories_with_at_least_10_age7_coordinates':sum(x['age7_unique_coordinates']>=10 for x in rows),'categories_with_at_least_10_age13_coordinates':sum(x['age13_unique_coordinates']>=10 for x in rows)})
    (a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__': main()
