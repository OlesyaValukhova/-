"""Build a 20×20 PechaKucha deck from completed B1 results.

The deck deliberately describes published, age-eligible spatial offer, not
actual journeys, independent mobility or parental escorting.
"""
from __future__ import annotations

from pathlib import Path
from textwrap import wrap

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'conference-pechakucha-20261112'
MAPS = ROOT / 'results' / 'age-profiles-blocks-b1-20261112-r2' / 'maps'
SENS = ROOT / 'results' / 'age-profiles-blocks-b1-20261112-r2' / 'threshold_sensitivity_by_direction.csv'

W, H = 13.333, 7.5
NAVY = '#102A43'; BLUE = '#277DA1'; TEAL = '#2A9D8F'; YELLOW = '#E9C46A'; ORANGE = '#F4A261'; RED = '#E76F51'; PALE = '#F4F7F9'; GREY = '#6B7C85'


def font(size, bold=False):
    return ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf', size)


def fig_path(name):
    OUT.mkdir(parents=True, exist_ok=True)
    return OUT / name


def make_charts():
    x = pd.read_csv(SENS)
    med = x.groupby(['age', 'threshold_minutes']).share_origins_with_venue_pct.median().unstack(0)
    fig, ax = plt.subplots(figsize=(9, 5), facecolor='white')
    for age, color, label in [(7, TEAL, '7 лет'), (13, ORANGE, '13 лет')]:
        ax.plot(med.index, med[age], color=color, marker='o', lw=4, ms=10, label=label)
        for xx, yy in zip(med.index, med[age]): ax.text(xx, yy + 2.4, f'{yy:.0f}%', ha='center', color=color, weight='bold', fontsize=13)
    ax.set(xlim=(14,31), ylim=(0,75), xlabel='пешеходный порог, минут', ylabel='медианная доля жилых точек')
    ax.spines[['top','right']].set_visible(False); ax.grid(axis='y', alpha=.2); ax.legend(frameon=False, loc='upper left')
    fig.tight_layout(); fig.savefig(fig_path('thresholds.png'), dpi=200, bbox_inches='tight'); plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5), facecolor='white')
    ax.barh(['выше у 7 лет','выше у 13 лет'], [19,24], color=[TEAL, ORANGE], height=.55)
    for y,v in enumerate([19,24]): ax.text(v+.35,y,str(v),va='center',weight='bold',fontsize=17,color=NAVY)
    ax.set(xlim=(0,30), xlabel='число направлений из 43'); ax.spines[['top','right','left']].set_visible(False); ax.tick_params(axis='y',length=0); ax.grid(axis='x',alpha=.2)
    fig.tight_layout(); fig.savefig(fig_path('directions_age.png'),dpi=200,bbox_inches='tight'); plt.close(fig)

    fig, ax = plt.subplots(figsize=(9,5),facecolor='white')
    vals = [43250, 16067, 1743, 43]
    labels = ['карточек\nкаталога', 'карточек\nс координатой', 'уникальных\nкоординат', 'направления\nв сравнении']
    ax.bar(range(4), vals, color=[NAVY, BLUE, TEAL, ORANGE], width=.65)
    for i,(v,l) in enumerate(zip(vals,labels)):
        ax.text(i,v*1.06,f'{v:,}'.replace(',',' '),ha='center',weight='bold',fontsize=16,color=NAVY)
        ax.text(i,-vals[0]*.15,l,ha='center',va='top',fontsize=12,color=NAVY)
    ax.set(ylim=(-vals[0]*.22,vals[0]*1.23)); ax.axis('off')
    fig.tight_layout(); fig.savefig(fig_path('catalogue_funnel.png'),dpi=200,bbox_inches='tight'); plt.close(fig)


def add_textbox(slide, x,y,w,h,text,size=20,color=NAVY,bold=False,align=PP_ALIGN.LEFT):
    box=slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf=box.text_frame; tf.clear(); tf.word_wrap=True; tf.vertical_anchor=MSO_ANCHOR.MIDDLE
    p=tf.paragraphs[0]; p.alignment=align; r=p.add_run(); r.text=text; r.font.name='Arial'; r.font.size=Pt(size); r.font.bold=bold; r.font.color.rgb=RGBColor.from_string(color.replace('#',''))
    return box


def rect(slide,x,y,w,h,fill, radius=False):
    shape=slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, Inches(x),Inches(y),Inches(w),Inches(h))
    shape.fill.solid(); shape.fill.fore_color.rgb=RGBColor.from_string(fill.replace('#','')); shape.line.fill.background(); return shape


def base_slide(prs, n, kicker='ВОЗРАСТНОЙ ПРОФИЛЬ ПЕШЕЙ ДОСТУПНОСТИ'):
    slide=prs.slides.add_slide(prs.slide_layouts[6]); rect(slide,0,0,W,H,'#FFFFFF'); rect(slide,0,0,.18,H,TEAL)
    add_textbox(slide,.55,.28,9,.25,kicker,8,GREY,True)
    add_textbox(slide,12.18,.28,.6,.25,f'{n:02d}',9,GREY,True,PP_ALIGN.RIGHT)
    return slide


def title(slide,text,sub=None):
    add_textbox(slide,.7,.82,11.8,1.0,text,29,NAVY,True)
    if sub: add_textbox(slide,.72,1.86,11,0.5,sub,14,GREY)


def image(slide,path,x,y,w,h):
    slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w), Inches(h))


def node(slide,x,y,label,color):
    rect(slide,x,y,2.45,1.0,color,True); add_textbox(slide,x+.08,y+.12,2.29,.7,label,17,'#FFFFFF',True,PP_ALIGN.CENTER)


def deck():
    make_charts(); prs=Presentation(); prs.slide_width=Inches(W); prs.slide_height=Inches(H)
    # 1
    s=base_slide(prs,1,'КОНФЕРЕНЦИЯ ВЫСОКОВСКОГО · 2026'); add_textbox(s,.78,1.15,11.5,2.5,'Возрастная динамика\nпотенциальной потребности\nв сопровождении детей',31,NAVY,True); add_textbox(s,.82,4.3,9.7,.9,'Пространственная типология жилых территорий Санкт-Петербурга',18,TEAL,True); add_textbox(s,.82,6.45,7,.3,'Печа-куча · 20 × 20',11,GREY)
    # 2
    s=base_slide(prs,2); title(s,'После школы маршрут не заканчивается')
    node(s,1,3.1,'дом',NAVY); node(s,5.35,3.1,'школа',BLUE); node(s,9.7,3.1,'занятие',ORANGE)
    for x in [3.55,7.9]: add_textbox(s,x,3.32,.8,.4,'→',30,TEAL,True,PP_ALIGN.CENTER)
    add_textbox(s,1.1,5.2,10.8,.55,'Внешкольное занятие — ещё одна регулярная точка городской повседневности.',19,NAVY,False,PP_ALIGN.CENTER)
    #3
    s=base_slide(prs,3); title(s,'Близко — ещё не значит самостоятельно')
    rect(s,1.1,2.55,4.8,2.1,PALE,True); add_textbox(s,1.35,2.8,4.3,1.6,'Расстояние\nдо площадки',29,BLUE,True,PP_ALIGN.CENTER)
    rect(s,7.4,2.55,4.8,2.1,'#FFF4E8',True); add_textbox(s,7.65,2.8,4.3,1.6,'Возможность\nидти одному',29,ORANGE,True,PP_ALIGN.CENTER)
    add_textbox(s,5.95,3.2,1.3,.5,'≠',34,RED,True,PP_ALIGN.CENTER)
    #4
    s=base_slide(prs,4); title(s,'Вопрос — что меняется с возрастом?'); add_textbox(s,1.05,2.55,11,.9,'Как меняется наблюдаемое пешеходное предложение внешкольных занятий\nдля ребёнка 7 и 13 лет из одной и той же жилой точки?',25,NAVY,True,PP_ALIGN.CENTER); add_textbox(s,2.3,5.3,8.8,.45,'Это вопрос о пространственных возможностях, не о фактических поездках.',15,GREY,False,PP_ALIGN.CENTER)
    #5
    s=base_slide(prs,5); title(s,'Измеряем предложение, а не поведение')
    for i,(a,b,c) in enumerate([('Единица','жилая точка',TEAL),('Объект','опубликованная координата',BLUE),('Показатель','число достижимых координат',ORANGE)]):
        x=1.05+i*4.1; rect(s,x,2.65,3.45,2.5,PALE if i!=2 else '#FFF4E8',True); add_textbox(s,x+.2,2.95,3.05,.4,a,13,GREY,True,PP_ALIGN.CENTER); add_textbox(s,x+.2,3.55,3.05,1.0,b,19,c,True,PP_ALIGN.CENTER)
    #6
    s=base_slide(prs,6); title(s,'Каталог превращается в наблюдаемый слой'); image(s,fig_path('catalogue_funnel.png'),1.25,2.25,10.9,3.9); add_textbox(s,1.0,6.25,11.2,.4,'Анализ ограничен опубликованными карточками с пригодными полями, а не всем существующим предложением.',12,GREY,False,PP_ALIGN.CENTER)
    #7
    s=base_slide(prs,7); title(s,'Один граф — два возрастных фильтра')
    node(s,1.0,3.0,'жилая\nточка',NAVY); node(s,5.45,2.25,'7 лет',TEAL); node(s,5.45,4.0,'13 лет',ORANGE); node(s,9.85,3.0,'возрастно\nдопустимые\nкоординаты',BLUE)
    for y in [2.5,4.25]: add_textbox(s,3.75,y,1,.35,'→',28,GREY,True,PP_ALIGN.CENTER); add_textbox(s,8.5,y,1,.35,'→',28,GREY,True,PP_ALIGN.CENTER)
    #8
    s=base_slide(prs,8); title(s,'Сценарий B1: пешком до 30 минут')
    add_textbox(s,1.1,2.3,11.1,.9,'Для каждой жилой точки считаем уникальные координаты возрастно-допустимых программ, достижимые по пешеходной сети.',25,NAVY,True,PP_ALIGN.CENTER)
    add_textbox(s,2.2,5.0,8.9,.65,'30 минут — исследовательский порог, а не норматив и не граница самостоятельности.',15,RED,True,PP_ALIGN.CENTER)
    #9
    s=base_slide(prs,9); title(s,'Направления не взаимозаменяемы')
    labels=['программирование','изобразительное\nискусство','танец','шахматы','спорт','ещё 38 направлений']
    for i,l in enumerate(labels):
        x=1.0+(i%3)*4.05; y=2.2+(i//3)*1.65; rect(s,x,y,3.45,1.05,[BLUE,TEAL,ORANGE,NAVY,RED,GREY][i],True); add_textbox(s,x+.1,y+.17,3.25,.65,l,16,'#FFFFFF',True,PP_ALIGN.CENTER)
    #10
    s=base_slide(prs,10); title(s,'Порог времени меняет картину'); image(s,fig_path('thresholds.png'),1.55,1.7,10.3,4.8); add_textbox(s,1.25,6.65,11,.3,'Медиана по 43 направлениям; только сетево-покрытые жилые точки.',11,GREY,False,PP_ALIGN.CENTER)
    #11
    s=base_slide(prs,11); title(s,'Возрастной профиль различается по направлениям'); image(s,fig_path('directions_age.png'),2.0,2.05,9.5,4.5); add_textbox(s,1.45,6.4,10.5,.35,'На 30 минутах: 24 направления выше для 13 лет, 19 — выше для 7 лет.',13,GREY,False,PP_ALIGN.CENTER)
    #12
    s=base_slide(prs,12); title(s,'Программирование: профиль чаще меняется с возрастом'); image(s,MAPS/'blocks_dominant_state_81.png',2.05,1.65,9.2,5.55)
    #13
    s=base_slide(prs,13); title(s,'Изобразительное искусство: другой профиль'); image(s,MAPS/'blocks_dominant_state_38.png',2.05,1.65,9.2,5.55)
    #14
    s=base_slide(prs,14); title(s,'Одна карта не заменяет сравнение направлений')
    rect(s,1.0,2.15,5.2,2.9,'#E8F4F2',True); add_textbox(s,1.3,2.55,4.6,1.9,'Программирование\n46% → 63%\n7 → 13 лет',27,TEAL,True,PP_ALIGN.CENTER)
    rect(s,7.1,2.15,5.2,2.9,'#FFF4E8',True); add_textbox(s,7.4,2.55,4.6,1.9,'Изобразительное искусство\n85% → 81%\n7 → 13 лет',27,ORANGE,True,PP_ALIGN.CENTER)
    add_textbox(s,1.3,5.7,10.7,.35,'Доли означают наличие наблюдаемой координаты ≤30 минут, а не посещение занятия.',12,GREY,False,PP_ALIGN.CENTER)
    #15
    s=base_slide(prs,15); title(s,'Квартал — способ увидеть неоднородность')
    rect(s,1.05,2.0,11.1,3.9,PALE,True); add_textbox(s,1.45,2.4,10.3,.55,'Жилые точки сначала получают возрастной профиль.',22,NAVY,True,PP_ALIGN.CENTER); add_textbox(s,1.45,3.5,10.3,.55,'Затем показатели агрегируются к готовым кварталам BlocksNet.',22,NAVY,True,PP_ALIGN.CENTER); add_textbox(s,1.45,4.6,10.3,.55,'Типы кварталов пока не присваиваются.',22,RED,True,PP_ALIGN.CENTER)
    #16
    s=base_slide(prs,16); title(s,'Разница N13 − N7 видна территориально'); image(s,MAPS/'blocks_delta_N_81.png',2.05,1.65,9.2,5.55)
    #17
    s=base_slide(prs,17); title(s,'Порог — это допущение, которое надо показывать')
    add_textbox(s,1.25,2.0,10.7,1.0,'15, 20 и 30 минут дают разные масштабы различий.',29,NAVY,True,PP_ALIGN.CENTER); rect(s,2.25,4.05,8.85,.85,TEAL,True); add_textbox(s,2.35,4.15,8.65,.55,'поэтому «доступность» без времени неполна',21,'#FFFFFF',True,PP_ALIGN.CENTER)
    #18
    s=base_slide(prs,18); title(s,'Что в этом подходе новое?')
    add_textbox(s,1.1,2.05,11.2,2.9,'Не просто «сколько площадок рядом»,\nа как возрастной фильтр меняет\nнаблюдаемое предложение в одном пространстве.',30,NAVY,True,PP_ALIGN.CENTER)
    #19
    s=base_slide(prs,19); title(s,'Чего эти карты не говорят')
    lines=['не измеряют реальные поездки','не измеряют самостоятельность','не измеряют сопровождение родителей','не знают запись, вместимость и спрос']
    for i,t in enumerate(lines): add_textbox(s,1.7,1.8+i*1.1,9.9,.5,'—  '+t,22,RED if i<3 else GREY,False)
    #20
    s=base_slide(prs,20,'СПАСИБО'); add_textbox(s,.9,1.5,11.5,2.4,'Возраст — это не только\nхарактеристика ребёнка.\nЭто фильтр городской возможности.',34,NAVY,True,PP_ALIGN.CENTER); add_textbox(s,1.1,5.85,11,.55,'Следующий шаг — сопоставить профили с планировочной структурой, не выдавая модель за поведение семей.',15,TEAL,True,PP_ALIGN.CENTER)
    prs.save(OUT/'pecha-kucha-age-dynamics-spb.pptx')


def memo_files():
    script = '''# Устный сценарий: 20 × 20 секунд

Каждый пункт соответствует одному слайду. Текст рассчитан на ориентир 35–45 слов, но его лучше проговорить вслух и сократить под естественный темп.

1. Я исследую не то, сколько родители фактически возят детей, а пространственные условия, в которых такая зависимость от сопровождения может сохраняться. Мой вопрос: как меняется доступное внешкольное предложение, когда ребёнок становится старше?
2. После школы повседневная география ребёнка не заканчивается. Появляется третья обязательная точка — занятие. Для семьи это может быть ещё один регулярный маршрут между домом, школой и площадкой.
3. Обычная карта расстояний слишком быстро делает вывод. Площадка может быть близкой, но это не равняется возможности ребёнка идти туда самостоятельно. Между пространственной близостью и независимой мобильностью остаётся много условий.
4. Поэтому я задаю более узкий и проверяемый вопрос. Для одних и тех же жилых точек: как меняется наблюдаемое предложение занятий для семилетнего и тринадцатилетнего ребёнка?
5. Здесь важно различать предложение и поведение. Я считаю опубликованные возрастно-допустимые координаты площадок. Это не число детей, не запись в группы и не реальные поездки.
6. Исходный каталог велик, но не каждая карточка пригодна для пространственного анализа. Я сохраняю это ограничение: результат относится только к наблюдаемому слою карточек с координатой и нужными метками.
7. Для обоих возрастов используется одна пешеходная сеть и одни жилые точки. Меняется только возрастной фильтр карточек. Поэтому разницу можно читать как различие опубликованного возрастного предложения, а не как эффект смены территории.
8. Базовый сценарий — пешеходная достижимость за тридцать минут. Это не норматив и не ответ на вопрос, должен ли ребёнок идти один. Это прозрачный порог, который можно менять и проверять.
9. Нельзя сложить все кружки в одну корзину. Программирование, танец, шахматы и искусство имеют разную возрастную структуру, разную географию и не заменяют друг друга для ребёнка.
10. На этом графике видно, что выбор порога существенен. И для семи, и для тринадцати лет доступная доля растёт от пятнадцати к тридцати минутам. Значит, доступность должна всегда называться вместе со временем.
11. Возрастной сдвиг не однонаправленный. В 24 из 43 направлений на тридцати минутах наблюдаемая доступность выше для 13 лет. В 19 направлениях — для 7 лет. Общая средняя карта скрыла бы этот факт.
12. Первый пример — программирование. Карта показывает преобладающее состояние жилых точек внутри квартала. Это иллюстрация различий, а не диагноз территории и не утверждение о самостоятельных поездках.
13. Второй пример — изобразительное искусство. Пространственный рисунок и возрастной профиль здесь другие. Сравнение двух направлений объясняет, почему типология не должна строиться на одной суммарной цифре кружков.
14. На тридцати минутах программирование наблюдается около 46 процентов точек для семи лет и 63 процентов для тринадцати. Для изобразительного искусства — примерно 85 и 81 процент. Разные направления дают разные возрастные траектории.
15. Чтобы не остановиться на отдельных точках, я агрегирую результаты к готовым кварталам BlocksNet. Но пока не кластеризую кварталы: сначала нужно увидеть распределения и проверить, какие сочетания признаков вообще содержательны.
16. Эта карта показывает медианную разницу числа достижимых координат в квартале. Положительное и отрицательное значение — это не оценка качества квартала, а направление изменения наблюдаемого предложения между возрастами.
17. Проверка нескольких порогов нужна не для выбора «правильного» времени, а чтобы не сделать вывод, который существует только при одном предположении. Пока можно говорить только о чувствительности результата к порогу.
18. Методический вклад здесь — возрастной фильтр в оценке доступности. Он позволяет увидеть, что даже при общей близости площадок предложение для возрастов устроено по-разному.
19. У исследования есть жёсткие границы. Оно не знает, куда ребёнок действительно ходит, есть ли свободные места, может ли семья оплатить занятие и разрешают ли родители идти одному. Эти вопросы требуют других данных.
20. Поэтому результат — не готовая типология и не измерение родительской нагрузки. Это воспроизводимая основа для следующего шага: проверить, какие планировочные особенности связаны с разными возрастными профилями возможностей.
'''
    sources = '''# Памятка: данные, допущения и ответы на вопросы

## Что показано

Пешеходная пространственная достижимость **опубликованных** возрастно-допустимых координат программ дополнительного образования из жилых точек Санкт-Петербурга. Базовый результат — B1, 30 минут пешком. `N` — число уникальных координат площадок, не карточек и не мест в группах.

## Данные

- Навигатор дополнительного образования Санкт-Петербурга: 43 250 скачанных карточек; аналитический слой B1 — 16 067 карточек с 1 743 уникальными координатами. Дата локальной выгрузки: 9–11 ноября 2026.
- Жилые точки: выгрузка Urban API; 30 611 точек, из которых 30 224 имеют сетевое покрытие.
- Пешеходная сеть: OSM PBF Санкт-Петербурга; параметры B1 зафиксированы в репозитории расчёта.
- Готовые кварталы: BlocksNet, `blocks_cleaned.geojson`.

## Ограничения

- Координата карточки не подтверждает адрес конкретной группы.
- Неизвестны запись, вместимость, спрос, расписание, цена и фактическая платность.
- Отсутствие координаты не означает отсутствия занятия.
- Результат не измеряет реальные поездки, независимую мобильность, безопасность маршрутов или сопровождение родителей.
- Это не проверка нормативов и не готовая типология кварталов.

## Короткие ответы

**Почему 7 и 13?** Это два прозрачных возрастных сценария для проверки того, меняется ли слой возрастно-допустимых программ; они не означают единый возраст самостоятельности.

**Почему 30 минут?** Это воспроизводимый пешеходный порог. Результаты также проверены на 15 и 20 минутах, поэтому 30 минут не выдается за единственно правильную границу.

**Почему нет транспорта?** Транспортный сценарий был рассчитан отдельно, но проверка параметров маршрутов ещё не позволяет использовать его как основной вывод конференции.

**Почему не измерить сопровождение?** Для этого нужны дневники, GPS или опрос семей. В текущем дизайне их нет; исследование рассматривает только пространственную предпосылку.

**Что дальше?** Сопоставить возрастные профили с морфологией и функциями кварталов, затем отдельно валидировать интерпретацию данными о реальном поведении.
'''
    (OUT/'speaker-script.md').write_text(script,encoding='utf-8')
    (OUT/'sources-assumptions-qa.md').write_text(sources,encoding='utf-8')


def pdf():
    # A compact PDF companion: 20 pages with the same headline and selected visual.
    pdf_path=OUT/'pecha-kucha-age-dynamics-spb.pdf'; c=canvas.Canvas(str(pdf_path),pagesize=(960,540))
    pdfmetrics.registerFont(TTFont('Arial','C:/Windows/Fonts/arial.ttf')); pdfmetrics.registerFont(TTFont('ArialBold','C:/Windows/Fonts/arialbd.ttf'))
    slides=[
      ('Возрастная динамика потенциальной\nпотребности в сопровождении детей',None),('После школы маршрут не заканчивается',None),('Близко — ещё не значит самостоятельно',None),('Что меняется с возрастом?',None),('Измеряем предложение, а не поведение',None),('Каталог превращается в наблюдаемый слой','catalogue_funnel.png'),('Один граф — два возрастных фильтра',None),('B1: пешком до 30 минут',None),('Направления не взаимозаменяемы',None),('Порог времени меняет картину','thresholds.png'),('Возрастной профиль различается по направлениям','directions_age.png'),('Программирование: возрастной профиль',MAPS/'blocks_dominant_state_81.png'),('Изобразительное искусство: другой профиль',MAPS/'blocks_dominant_state_38.png'),('Одна карта не заменяет сравнение направлений',None),('Квартал — способ увидеть неоднородность',None),('Разница N13 − N7 видна территориально',MAPS/'blocks_delta_N_81.png'),('Порог — это допущение',None),('Возрастной фильтр городской возможности',None),('Чего карты не говорят',None),('Следующий шаг — планировочная типология',None)]
    for i,(head,asset) in enumerate(slides,1):
        c.setFillColor(NAVY); c.rect(0,0,960,540,fill=1,stroke=0); c.setFillColorRGB(1,1,1); c.setFont('ArialBold',28)
        y=450
        for line in head.split('\n'):
            c.drawCentredString(480,y,line); y-=38
        c.setFillColor(TEAL); c.setFont('ArialBold',10); c.drawString(45,505,'ВОЗРАСТНОЙ ПРОФИЛЬ ПЕШЕЙ ДОСТУПНОСТИ'); c.drawRightString(915,505,f'{i:02d}')
        if asset:
            p=asset if isinstance(asset,Path) else OUT/asset
            im=Image.open(p); iw,ih=im.size; scale=min(760/iw,260/ih); w,h=iw*scale,ih*scale; c.drawImage(ImageReader(im),480-w/2,70,w,h)
        c.setFillColor('#B9D6E4'); c.setFont('Arial',12); c.drawCentredString(480,28,'Печа-куча · 20 × 20 · Санкт-Петербург')
        c.showPage()
    c.save()


if __name__ == '__main__':
    deck(); memo_files(); pdf()
