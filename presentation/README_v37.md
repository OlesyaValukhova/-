# Презентация НИР v37

**Ветка:** `codex/presentation-b1-denominator-v37`  
**Основа:** v36; предыдущие версии и работа агента сохранены.  
**Сценарий:** B1, пешком, 30 минут; возрастные срезы 7 и 13 лет.  
**Объём:** 20 слайдов; карты и речь v10 сохранены.

## Исправление знаменателя на слайде 9

В v36 скрытая заметка слайда 9 ошибочно указывала 30 224 как знаменатель четырёх взвешенных долей программирования и ИЗО. Эти четыре значения воспроизводятся из квартальных CSV и рассчитаны по 30 222 точкам, одновременно:
- покрытым пешеходной сетью;
- присоединённым к кварталам BlocksNet.

Квартальные доли взвешены по `n_valid`. На слайде 9 уточнены подпись графика, нижняя строка, заметка докладчика и раскрываемое пояснение.

**30 224** остаётся правильным знаменателем для сравнения 43 направлений: этот расчёт выполняется на всех сетево-покрытых жилых точках и не требует квартальной привязки. Две точки, не присоединённые к BlocksNet, исключаются только из квартальной агрегации.

## Что не менялось

- четыре значения на слайде 9;
- квартальные CSV и их исходные показатели;
- пять карт SVG v35 и геометрия BlocksNet;
- 43-направленный график и медианы по порогам 15/20/30 минут;
- методика B1, возрастные срезы и исследовательские выводы;
- 20-слайдовая структура и речь v10.

Добавлен `coverage_audit_v37.json` с явным словарём двух знаменателей и `verify_presentation_v37.py`, который проверяет их соответствие слайдам и значениям исходных CSV.

## Проверка

Из корня репозитория:

```bash
python presentation/map_sources/verify_presentation_v37.py
```

Скрипт использует стандартную библиотеку Python и существующие CSV; он не запускает маршрутизацию и не перестраивает карты.

## Ограничения

- Полный просмотр HTML в браузере и на проекторном разрешении не выполнен.
- Генератор карт v24 повторно не запускался; SVG v35 оставлены без изменений.
- Географические подписи районов, водных объектов и улиц не добавлены: проверенный слой ориентиров не подключён.
- N — число уникальных опубликованных координат Navigator, а не число групп, свободных мест, детей или участников.

## Alignment with the current research brief

The latest methodological instruction in `second_brain_for_nir` is commit [70b96cb, 12 November 2026](https://github.com/OlesyaValukhova/second_brain_for_nir/commit/70b96cb98885949ab678cf38051336b9ac675da8). It defines the residential origin as the calculation unit and existing BlocksNet blocks as the territorial aggregation unit. Point-level pairing must precede block aggregation; centroids and a new 500 × 500 m grid are out of scope.

The repository currently exposes the block-level B1 tables and 43-direction summary used here, but not the raw point-level B1 results and their residential-point geometry. The B1 report also states that exact geometries and point-level values remain local and are not published. Therefore v37 does not attempt to reconstruct point-level maps from block aggregates. The existing maps are explicitly block summaries; producing point-level maps requires the original point-level outputs and geometry.
