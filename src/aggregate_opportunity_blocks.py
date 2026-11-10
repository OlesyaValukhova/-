"""Aggregate the age-opportunity pilot to residential blocks and explore clusters.

This is an exploratory pilot typology.  It is limited to the acquisition area
and one activity; clusters are descriptive, not a city-wide typology.
"""
import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


FEATURES = [
    "age_7_nearest_minutes", "age_13_nearest_minutes",
    "age_7_locations_within_15min", "age_13_locations_within_15min",
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--origins", type=Path, required=True)
    p.add_argument("--blocks", type=Path, required=True)
    p.add_argument("--opportunities", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error("Output must be new")
    a.output.mkdir(parents=True)
    origins = gpd.read_file(a.origins)
    blocks = gpd.read_file(a.blocks).to_crs(origins.crs)
    values = pd.read_csv(a.opportunities, encoding="utf-8-sig")
    values["source_row"] = values["origin_id"].str.replace("origin-source-", "", regex=False).astype(int)
    origins = origins.merge(values.drop(columns="origin_id"), on="source_row", how="inner")
    # ``fid`` is a source identifier; keep it distinct from a GeoDataFrame index.
    joined = gpd.sjoin(origins, blocks[["fid", "geometry"]], how="left", predicate="within")
    joined = joined.dropna(subset=["fid"]).copy()
    joined["fid"] = joined["fid"].astype(int)
    records = []
    for fid, group in joined.groupby("fid"):
        record = {"fid": fid, "residential_points": len(group)}
        for col in FEATURES:
            record[f"median_{col}"] = group[col].median()
        for age in (7, 13):
            col = f"age_{age}_locations_within_15min"
            record[f"share_{age}_with_two_15min"] = (group[col] >= 2).mean()
        records.append(record)
    frame = pd.DataFrame(records).sort_values("fid")
    clustering_features = [f"median_{x}" for x in FEATURES]
    x = StandardScaler().fit_transform(frame[clustering_features])
    candidate_scores = {}
    for k in range(2, min(6, len(frame))):
        labels = KMeans(n_clusters=k, random_state=20261110, n_init=50).fit_predict(x)
        candidate_scores[k] = float(silhouette_score(x, labels))
    selected_k = max(candidate_scores, key=candidate_scores.get)
    model = KMeans(n_clusters=selected_k, random_state=20261110, n_init=50).fit(x)
    frame["exploratory_cluster"] = model.labels_ + 1
    cluster_profile = frame.groupby("exploratory_cluster")[clustering_features + ["residential_points", "share_7_with_two_15min", "share_13_with_two_15min"]].median()
    frame.to_csv(a.output / "block-opportunity-profile.csv", index=False, encoding="utf-8-sig")
    output = blocks[["fid", "geometry"]].merge(frame, on="fid", how="inner")
    output.to_file(a.output / "block-opportunity-profile.geojson", driver="GeoJSON")
    report = {"status": "computed", "input_origins": len(origins), "origins_joined_to_blocks": len(joined),
              "blocks_with_origins": len(frame), "features": clustering_features,
              "candidate_silhouette_scores": candidate_scores, "selected_cluster_count": selected_k,
              "cluster_median_profiles": cluster_profile.reset_index().to_dict(orient="records"),
              "limitations": ["Blocks are inherited from a legacy Prostor layer whose source date was not verified.",
                              "This is one activity and one acquisition-area pilot, not a Saint Petersburg typology.",
                              "Clusters summarize published age-eligible locations, not observed mobility, accompaniment, safety, quality, capacity or demand."]}
    (a.output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    (a.output / "README.md").write_text("# Пилотная квартальная агрегация\n\n"
        "Квартальные показатели и exploratory-кластеры построены только для шахматного пилота. "
        "Число кластеров выбрано как максимум silhouette среди k=2…5; это диагностика структуры пилота, не готовая типология города.\n", encoding="utf8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
