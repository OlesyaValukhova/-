"""Compare reviewed specific activity titles on one saved walking matrix."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd


def main():
    p = argparse.ArgumentParser()
    for name in ('selection', 'scenarios', 'matrix', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    titles = pd.read_csv(a.selection, encoding='utf-8-sig', dtype={'program_id': str})
    scenarios = pd.read_csv(a.scenarios, encoding='utf-8-sig', dtype={'program_id': str})
    matrix = pd.read_csv(a.matrix, index_col=0, encoding='utf-8-sig')
    joined = scenarios.merge(titles[['program_id', 'activity_label']], on='program_id', validate='many_to_one')
    if not set(joined.location_id).issubset(matrix.columns):
        raise ValueError('Missing selected coordinates in matrix')
    summary = []
    for (activity, age), part in joined.groupby(['activity_label', 'age']):
        if age not in (7, 13):
            continue
        for evidence, field in [('program_age', 'program_age_match'), ('group_evidence', 'program_and_group_match')]:
            picked = part[part[field] == True]
            locations = sorted(set(picked.location_id))
            for threshold in (10, 15, 20, 30):
                count = (matrix[locations] <= threshold).sum(axis=1) if locations else pd.Series(0, index=matrix.index)
                summary.append({'activity': activity, 'age': int(age), 'evidence': evidence,
                                'threshold_minutes': threshold, 'selected_programs': len(picked),
                                'selected_coordinates': len(locations), 'origins': len(count),
                                'median_coordinates': float(np.median(count)),
                                'origins_without_coordinate': int((count == 0).sum())})
    a.output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(summary).to_csv(a.output/'summary.csv', index=False, encoding='utf-8-sig')
    print(pd.DataFrame(summary).query("age in [7,13] and evidence == 'program_age' and threshold_minutes == 15").to_string(index=False))


if __name__ == '__main__':
    main()
