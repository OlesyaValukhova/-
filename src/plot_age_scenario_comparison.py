"""Render a simple research figure from an existing scenario summary CSV."""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--summary', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--threshold', type=int, default=15)
    a = p.parse_args()
    data = pd.read_csv(a.summary, encoding='utf-8-sig')
    data = data[(data.category_kind == 'all') & (data.threshold_minutes == a.threshold)]
    if data.duplicated(['age', 'scenario']).any():
        raise ValueError('Expected one result per age and scenario')
    values = data.pivot(index='age', columns='scenario', values='median_reachable_programs').sort_index()
    scenarios = ['programme_age', 'programme_and_group_intervals']
    if values.empty or any(s not in values for s in scenarios) or values[scenarios].isna().any().any():
        raise ValueError('Both scenarios are needed for each age')
    a.output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 12})
    fig, ax = plt.subplots(figsize=(12, 7), layout='constrained')
    x = np.arange(len(values))
    width = .34
    b1 = ax.bar(x-width/2, values[scenarios[0]], width, color='#356E95',
                label='Подходит возраст программы')
    b2 = ax.bar(x+width/2, values[scenarios[1]], width, color='#E69B4A',
                label='Также есть подходящие возраст и даты группы')
    ax.bar_label(b1, padding=4, fontsize=12)
    ax.bar_label(b2, padding=4, fontsize=12)
    ax.set_xticks(x, [str(int(age)) for age in values.index])
    ax.set_xlabel('Возраст ребёнка, лет')
    ax.set_ylabel('Медианное число записей программ на здание')
    ax.set_title('Программы по возрастам: что меняется при проверке групп',
                 loc='left', fontsize=17, weight='bold', pad=18)
    ax.set_ylim(0, max(values[scenarios].to_numpy().max() * 1.23, 1))
    ax.yaxis.grid(True, color='#DDE4E8', linewidth=.7)
    ax.set_axisbelow(True)
    ax.spines[['top', 'right']].set_visible(False)
    ax.legend(loc='upper left', frameon=False, fontsize=11)
    fig.text(.06, -.06,
             f'Василеостровский район · {a.threshold} минут по пешеходной сети без подходов к узлам · 9 ноября 2026\n'
             'Это записи Навигатора: адрес и работа группы не подтверждены; меньше записей не означает меньше реальных занятий.',
             fontsize=10, color='#46535C', va='top')
    fig.savefig(a.output / 'age-scenarios.png', dpi=180, bbox_inches='tight', facecolor='white')
    fig.savefig(a.output / 'age-scenarios.svg', bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(str(a.output / 'age-scenarios.png'))


if __name__ == '__main__':
    main()
