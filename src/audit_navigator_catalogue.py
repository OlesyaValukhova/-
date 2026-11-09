"""Describe catalogue concentration and missingness; does not estimate accessibility."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--details', type=Path, help='Optional folder of diagnostic detail/group responses')
    args = parser.parse_args()
    bundle = json.loads(args.input.read_text(encoding='utf-8'))
    rows = [r for p in bundle['pages'] for r in p['response']['results']]
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate IDs: inspect collection before audit')
    args.output.mkdir(parents=True, exist_ok=False)
    organizations = Counter(r.get('organization') for r in rows)
    coordinates = Counter()
    org_points = defaultdict(set)
    directions = Counter()
    profile_points = defaultdict(set)
    geo_count = 0
    for r in rows:
        point = None
        if r.get('latitude') is not None and r.get('longitude') is not None:
            point = (float(r['latitude']), float(r['longitude']))
            if not (-90 <= point[0] <= 90 and -180 <= point[1] <= 180):
                raise ValueError('Invalid coordinates')
            coordinates[point] += 1
            org_points[r.get('organization')].add(point)
            geo_count += 1
        for direction in set(r.get('profiles') or []):
            directions[direction] += 1
            if point is not None:
                profile_points[direction].add(point)
    summary = {
        'programs': len(rows), 'distinct_organization_labels': len(organizations),
        'programs_with_coordinates': geo_count, 'programs_without_coordinates': len(rows)-geo_count,
        'distinct_coordinate_pairs': len(coordinates),
        'organizations_with_any_coordinates': len(org_points),
        'top_three_organization_programs': sum(v for _, v in organizations.most_common(3)),
        'programs_with_profiles': sum(bool(r.get('profiles')) for r in rows),
        'programs_with_study_areas': sum(bool(r.get('study_areas')) for r in rows),
        'fields': sorted({k for r in rows for k in r}),
        'source': str(args.input), 'accessibility_computed': False,
    }
    (args.output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    tables = {
        'organizations.csv': (['organization', 'programs', 'distinct_reported_coordinates'],
                              [(k, v, len(org_points[k])) for k, v in organizations.most_common()]),
        'coordinates.csv': (['latitude', 'longitude', 'programs'],
                            [(*k, v) for k, v in coordinates.most_common()]),
        'profiles.csv': (['profile', 'programs', 'distinct_reported_coordinates'],
                         [(k, v, len(profile_points[k])) for k, v in directions.most_common()]),
    }
    for name, (headers, records) in tables.items():
        with (args.output/name).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(headers)
            writer.writerows(records)
    lines = ['# Проверка предположения о высокой доступности', '',
             'Это аудит каталога, а не расчёт транспортной доступности или готовая типология.', '',
             '| Проверка | Результат |', '|---|---:|',
             f'| Программы | {len(rows)} |',
             f'| Разные названия организаций | {len(organizations)} |',
             f'| Программы с координатами | {geo_count} ({geo_count/len(rows):.1%}) |',
             f'| Программы без координат | {len(rows)-geo_count} |',
             f'| Разные пары координат | {len(coordinates)} |',
             f'| Программы у трёх наиболее представленных названий организаций | {summary["top_three_organization_programs"]} |',
             f'| Программы с непустым profiles | {summary["programs_with_profiles"]} |',
             f'| Программы с непустым study_areas | {summary["programs_with_study_areas"]} |', '',
             '## Что это означает', '',
             'Количество программ нельзя интерпретировать как количество независимых площадок. '
             'Совпадение координат не доказывает совпадение места конкретной группы. '
             'Разные названия организаций не обязательно соответствуют разным юридическим лицам. '
             'Программы без координат нельзя считать отсутствующими или недоступными.', '',
             'Поля profiles и study_areas подсчитаны как опубликованные метки; '
             'пустая метка означает неизвестное направление, а не отсутствие направленности.', '',
             '## Чего пока нельзя проверить', '',
             'В списке нет явных полей нижнего/верхнего возраста и адреса занятий. '
             'Не получены подтверждённые адреса групп, жилые точки отправления и времена поездок. '
             'Поэтому ни высокая доступность, ни её различия по возрастам пока не установлены. '
             '94 пары координат — характеристика заполненной части каталога, не итоговое число площадок района.', '',
             'Следующий этап: проверить карточки/группы, связать программу с возрастом и местами занятий, '
             'затем сравнить достижимое предложение из жилых территорий. '
             'Не выбирать пороги или направления специально для получения различий.', '',
             f'Источник: `{args.input}`. Отдельные таблицы сохранены рядом с этой запиской.']
    if args.details:
        sample = []
        group_rows = []
        for file in sorted(args.details.glob('*-detail.json')):
            d = json.loads(file.read_text(encoding='utf-8'))
            groups_file = args.details / f"{d['id']}-groups.json"
            groups = json.loads(groups_file.read_text(encoding='utf-8')) if groups_file.exists() else None
            if groups is not None and not isinstance(groups, list):
                raise ValueError('Unrecognized group response; do not assume an empty list')
            sample.append({'id': d['id'], 'name': d.get('name'),
                           'organization_id': (d.get('organization') or {}).get('id'),
                           'min_age': d.get('min_age'), 'max_age': d.get('max_age'),
                           'address': d.get('address'), 'district': d.get('district'),
                           'latitude': d.get('latitude'), 'longitude': d.get('longitude'),
                           'groups_returned': len(groups) if groups is not None else None,
                           'source_url': f"https://dopobr.petersburgedu.ru/api/program/{d['id']}/"})
            for g in groups or []:
                group_rows.append({'program_id': d['id'], **{k: g.get(k) for k in
                    ['id', 'min_age', 'max_age', 'is_age_limit', 'lesson_start', 'lesson_end',
                     'members_limit', 'free_places_count']}, 'status': (g.get('status') or {}).get('id')})
        for name, records in [('sample-programs.csv', sample), ('sample-groups.csv', group_rows)]:
            if records:
                with (args.output/name).open('w', encoding='utf-8-sig', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(records[0]))
                    writer.writeheader()
                    writer.writerows(records)
        known_ages = sum(r['min_age'] is not None and r['max_age'] is not None for r in sample)
        addresses = sum(bool(r['address']) for r in sample)
        geo = sum(r['latitude'] is not None and r['longitude'] is not None for r in sample)
        stats = {'sample_programs': len(sample), 'with_age_bounds': known_ages,
                 'with_program_address': addresses, 'with_program_coordinates': geo,
                 'group_records_returned': len(group_rows),
                 'group_records_with_explicit_address': 0,
                 'selection': '12 distinct organization labels, first listed programs, including 13702; diagnostic, not representative',
                 'source_folder': str(args.details)}
        # Check all actual keys rather than infer address availability from the normalized table.
        for file in args.details.glob('*-groups.json'):
            for g in json.loads(file.read_text(encoding='utf-8')):
                if any(g.get(k) for k in ['address', 'addresses', 'venue', 'location']):
                    stats['group_records_with_explicit_address'] += 1
        (args.output/'detail-summary.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
        lines += ['', '## Проверка карточек и групп: фактическое дополнение', '',
                  f'Получены {len(sample)} карточек программ от разных названий организаций. '
                  'Это целевая проверка схемы: первые программы разных организаций, включая 13702. '
                  'Выборка не случайная, не репрезентативная; по ней нельзя оценивать доли возрастных предложений в районе.', '',
                  f'Возрастные границы заполнены в {known_ages}/{len(sample)}, '
                  f'адрес программы — в {addresses}/{len(sample)}, '
                  f'координаты программы — в {geo}/{len(sample)}. '
                  f'В ответах групп получено {len(group_rows)} записей. '
                  f'Явные адреса/места в проверенных полях групп: {stats["group_records_with_explicit_address"]}.', '',
                  'Возраст и адрес программы обнаружены в карточке, хотя отсутствуют в исходном списке. '
                  'UI показывает адрес программы как место проведения; отдельный адрес конкретной группы '
                  'по этим ответам не подтверждён. Адреса организации не подставлялись вместо адресов программ. '
                  'Все возвращённые группы сохранены с датами и статусом; они не объявляются действующими автоматически. '
                  'Ответ групп — массив без next/count: полноту групп по этому признаку не сертифицируем.', '',
                  '| Программа | Возраст по карточке |', '|---|---|']
        for r in sample:
            lines.append(f'| {r["name"].replace("|", "/")} | {r["min_age"]}–{r["max_age"]} |')
        lines += ['', '## Итог проверки', '',
                  'Большое число строк не доказывает насыщение пространственного показателя. '
                  'Данные пригоднее для следующего этапа, чем казалось по списку: возраст и адреса можно получать из карточек. '
                  'Высокая/низкая доступность и различия между жилыми территориями ещё не рассчитаны. '
                  'Нужны полная привязка программ к местам, возрастам и актуальности, '
                  'точки отправления и сеть для времени пути. Имеющиеся результаты не подтверждают и не опровергают '
                  'предположение об одинаково высокой доступности по району.']
    (args.output/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
