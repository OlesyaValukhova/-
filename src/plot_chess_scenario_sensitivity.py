"""Visualise age-threshold sensitivity using the saved paired scenario table."""
import argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd


def main():
    p = argparse.ArgumentParser()
    p.add_argument('summary', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    df = pd.read_csv(a.summary, encoding='utf-8-sig')
    comparison = 'age_7_10_vs_age_13_20'
    df = df[df.comparison == comparison].set_index('scenario')
    labels = ['По возрасту программы', 'С дополнительными\nсведениями о группе']
    rows = [df.loc['program_age'], df.loc['group_evidence']]
    if any(int(row[['first_more', 'equal', 'second_more']].sum()) != int(row.origins) for row in rows):
        raise ValueError('Scenario totals differ from origin count')
    colors = ['#b54d46', '#c7d0d4', '#258077']
    descriptions = ['Больше в сценарии для 7 лет', 'Число равно', 'Больше в сценарии для 13 лет']
    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_facecolor('#faf9f6'); ax.set_facecolor('#faf9f6')
    for i, row in enumerate(rows):
        left = 0
        for key, color in zip(['first_more', 'equal', 'second_more'], colors):
            value = int(row[key]); ax.barh(i, value, left=left, height=.5, color=color)
            if value > 0:
                ax.text(left + value/2, i, f'{value}', ha='center', va='center',
                        color='white' if key != 'equal' else '#27353a', fontsize=15, weight='bold')
            left += value
    ax.set_yticks(range(2), labels, fontsize=13); ax.invert_yaxis()
    ax.set_xlim(0, 1265); ax.set_xticks([0, 250, 500, 750, 1000, 1265]); ax.tick_params(axis='x', labelsize=10)
    ax.set_xlabel('Число жилых точек (всего 1 265)', fontsize=11)
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.tick_params(axis='y', length=0); ax.set_axisbelow(True)
    from matplotlib.patches import Patch
    handles = [Patch(facecolor=c, label=l) for c, l in zip(colors, descriptions)]
    fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.5, .105), ncol=3, frameon=False, fontsize=10)
    fig.suptitle('Шахматные программы: результат зависит от отбора карточек', fontsize=18, weight='bold', ha='left', x=.02)
    ax.set_title('Сценарии: 7 лет и 10 минут / 13 лет и 20 минут пешком', loc='left', fontsize=12, pad=20)
    fig.text(.02, .015, 'Пороги условные, не нормы самостоятельности. Координаты программ не подтверждают место занятий.\n'
             'Данные Навигатора и OSM на 09.11.2026; Василеостровский район и выбранные соседние программы.', fontsize=9, color='#465459')
    fig.tight_layout(rect=[0, .19, 1, .9])
    a.output.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.output / 'scenario-sensitivity.png', dpi=180, facecolor=fig.get_facecolor())
    fig.savefig(a.output / 'scenario-sensitivity.svg', facecolor=fig.get_facecolor())


if __name__ == '__main__':
    main()
