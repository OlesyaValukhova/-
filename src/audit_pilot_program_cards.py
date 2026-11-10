"""Audit selected Navigator cards without treating a card as a verified venue."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def age_segment(row: pd.Series) -> str:
    at7 = row.min_age <= 7 <= row.max_age
    at13 = row.min_age <= 13 <= row.max_age
    if at7 and at13:
        return "both_7_and_13"
    if at7:
        return "only_7"
    if at13:
        return "only_13"
    return "neither"


def audit_activity(activity: str, source: Path, details: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.read_csv(source, encoding="utf-8-sig")
    d["activity"] = activity
    d["age_segment"] = d.apply(age_segment, axis=1)
    records = []
    for row in d.itertuples(index=False):
        path = details / f"{row.program_id}-detail.json"
        record = {"activity": activity, "program_id": row.program_id, "detail_file_found": path.exists()}
        if path.exists():
            card = json.loads(path.read_text(encoding="utf-8"))
            groups = card.get("groups") or []
            ages = [(float(g["min_age"]), float(g["max_age"])) for g in groups if g.get("min_age") not in (None, "") and g.get("max_age") not in (None, "")]
            record.update({
                "payment_raw": card.get("payment"),
                "cost_raw": card.get("cost"),
                "cost_published": bool(str(card.get("cost") or "").strip()),
                "activity_status_raw": card.get("activity_status"),
                "group_count_detail": len(groups),
                "groups_with_numeric_ages": len(ages),
                "any_group_allows_7": any(lo <= 7 <= hi for lo, hi in ages),
                "any_group_allows_13": any(lo <= 13 <= hi for lo, hi in ages),
                "free_places_count": card.get("free_places_count"),
                "program_min_age_detail": card.get("min_age"),
                "program_max_age_detail": card.get("max_age"),
            })
        records.append(record)
    return d, pd.DataFrame(records)


def describe(programs: pd.DataFrame, detail: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for activity, d in programs.groupby("activity", sort=False):
        for segment, s in d.groupby("age_segment", sort=False):
            detail_s = detail[(detail.activity == activity) & detail.program_id.isin(s.program_id)]
            rows.append({
                "activity": activity,
                "age_segment": segment,
                "program_cards": len(s),
                "unique_coordinates": s.location_id.nunique(),
                "inside_boundary_cards": int((s.spatial_class == "inside_boundary").sum()),
                "buffer_cards": int((s.spatial_class == "outside_within_buffer").sum()),
                "cards_with_detail": int(detail_s.detail_file_found.sum()),
                "cards_with_published_cost_text": int(detail_s.cost_published.fillna(False).sum()),
                "cards_with_group_age_information": int((detail_s.groups_with_numeric_ages.fillna(0) > 0).sum()),
                "cards_where_program_7_but_no_group_7": int(((s.min_age <= 7) & (7 <= s.max_age) & ~detail_s.set_index("program_id").reindex(s.program_id).any_group_allows_7.fillna(False).to_numpy()).sum()),
                "cards_where_program_13_but_no_group_13": int(((s.min_age <= 13) & (13 <= s.max_age) & ~detail_s.set_index("program_id").reindex(s.program_id).any_group_allows_13.fillna(False).to_numpy()).sum()),
            })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chess", type=Path, required=True)
    parser.add_argument("--robotics", type=Path, required=True)
    parser.add_argument("--details", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    chess, chess_detail = audit_activity("Шахматы", args.chess, args.details)
    robotics, robotics_detail = audit_activity("Робототехника", args.robotics, args.details)
    programs = pd.concat([chess, robotics], ignore_index=True)
    detail = pd.concat([chess_detail, robotics_detail], ignore_index=True)
    args.output.mkdir(parents=True, exist_ok=True)
    programs.to_csv(args.output / "selected-program-cards.csv", index=False, encoding="utf-8-sig")
    detail.to_csv(args.output / "selected-card-fields.csv", index=False, encoding="utf-8-sig")
    describe(programs, detail).to_csv(args.output / "age-and-card-audit-summary.csv", index=False, encoding="utf-8-sig")
    # A small reproducible inspection set: first two cards from each activity and age segment.
    sample = programs.sort_values(["activity", "age_segment", "program_id"]).groupby(["activity", "age_segment"], group_keys=False).head(2)
    sample.merge(detail, on=["activity", "program_id"], how="left").to_csv(
        args.output / "manual-inspection-sample.csv", index=False, encoding="utf-8-sig"
    )


if __name__ == "__main__":
    main()
