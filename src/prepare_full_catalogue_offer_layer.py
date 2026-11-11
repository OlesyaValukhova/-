"""Quick offline field audit and spatial-age offer layer for all saved Navigator cards.

The output is the *observable analytical subset*: programme cards with a
non-empty identifier/name, valid published coordinate and complete numeric age
interval.  A card coordinate remains a published-coordinate proxy, not a
verified group venue or entrance.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import geopandas as gpd
from shapely.geometry import Point

def numeric(x):
    try: x=float(x)
    except (TypeError, ValueError): return None
    return x if math.isfinite(x) else None

def cid(lon, lat):
    return 'coordinate-'+hashlib.sha256(f'{lon:.12f},{lat:.12f}'.encode()).hexdigest()[:16]

def read_card(path):
    try: return path, json.loads(path.read_bytes())
    except (OSError,json.JSONDecodeError): return path, None

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--details',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    if a.output.exists(): p.error('Output directory must be new')
    files=sorted(a.details.glob('*-detail.json'))
    if not files: p.error('No card files found')
    counts=Counter(); rows=[]; venues={}; bad_json=0
    # Files are individual OneDrive objects; bounded concurrent reads avoid
    # spending most of the audit waiting on 43k sequential open operations.
    with ThreadPoolExecutor(max_workers=16) as pool:
      records = pool.map(read_card, files)
      for path, card in records:
        if card is None: bad_json+=1; continue
        counts['saved_card_files']+=1
        ident=card.get('id'); name=str(card.get('name') or '').strip(); address=str(card.get('address') or '').strip()
        lon,lat=numeric(card.get('longitude')),numeric(card.get('latitude'))
        lo,hi=numeric(card.get('min_age')),numeric(card.get('max_age'))
        has_id=ident not in (None,''); has_name=bool(name); has_address=bool(address)
        coordinate=lon is not None and lat is not None and -180<=lon<=180 and -90<=lat<=90
        age=lo is not None and hi is not None and lo<=hi
        counts['with_id']+=has_id; counts['with_name']+=has_name; counts['with_published_address']+=has_address; counts['with_valid_coordinate']+=coordinate; counts['with_valid_age_interval']+=age
        if coordinate and age: counts['with_coordinate_and_age']+=1
        if has_id and has_name and coordinate and age:
            counts['observable_spatial_age_offer']+=1
            coordinate_id=cid(lon,lat)
            row={'program_id':str(ident),'program_name':name,'offer_unit':'program_card_coordinate_offer_proxy','coordinate_id':coordinate_id,'longitude':lon,'latitude':lat,'min_age':lo,'max_age':hi,'published_address':address,'published_address_present':has_address,'card_file':str(path)}
            rows.append(row)
            venues.setdefault(coordinate_id,{'coordinate_id':coordinate_id,'geometry':Point(lon,lat),'cards_at_coordinate':0})['cards_at_coordinate']+=1
    if len({r['program_id'] for r in rows}) != len(rows): raise RuntimeError('Duplicate programme IDs in saved cards')
    a.output.mkdir(parents=True)
    with (a.output/'all-observable-program-card-coordinate-offers.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['program_id']); w.writeheader(); w.writerows(rows)
    gpd.GeoDataFrame(list(venues.values()),crs=4326).to_file(a.output/'all-observable-coordinate-venue-proxy.geojson',driver='GeoJSON')
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'saved_card_files_found':len(files),'unreadable_or_invalid_json_files':bad_json,'field_counts':dict(counts),'shares_of_saved_cards':{k:v/len(files) for k,v in counts.items()},'unique_published_coordinate_venue_proxies':len(venues),'age_7_eligible_card_coordinate_offers':sum(r['min_age']<=7<=r['max_age'] for r in rows),'age_13_eligible_card_coordinate_offers':sum(r['min_age']<=13<=r['max_age'] for r in rows),'unit':'program_card_coordinate_offer_proxy','limits':['The analytical layer is the observed subset with valid published coordinate and programme-card age interval; omitted cards are not evidence of absent provision.','A coordinate is published on the programme card, not a verified venue of each group.','No schedules, capacity, vacancies, price, actual attendance, accompaniment or travel behaviour are represented.']}
    (a.output/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__': main()
