"""Audit age, coordinate, payment and group-status fields of citywide B1 inputs."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def value_counts(rows: list[dict], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(field, "")) for row in rows).items()))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--offers", type=Path, nargs="+", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error("Output must be new")
    a.output.mkdir(parents=True)
    rows: list[dict] = []
    for offer_path in a.offers:
        offers = pd.read_csv(offer_path, encoding="utf-8-sig", dtype={"program_id": str})
        for offer in offers.to_dict("records"):
            card_path = Path(str(offer["card_file"]))
            card = json.loads(card_path.read_text(encoding="utf-8"))
            groups = card.get("groups") or []
            group_age = [g for g in groups if g.get("min_age") not in (None, "") and g.get("max_age") not in (None, "")]
            rows.append({
                "activity_key": offer["activity_key"], "program_id": offer["program_id"],
                "coordinate_id": offer["coordinate_id"], "program_min_age": offer["min_age"],
                "program_max_age": offer["max_age"], "published_address_present": bool(str(offer.get("published_address") or "").strip()),
                "payment_code": card.get("payment"), "cost_present": bool(str(card.get("cost") or "").strip()),
                "activity_status": card.get("activity_status"), "group_count": len(groups),
                "numeric_age_group_count": len(group_age),
                "group_statuses": " | ".join(sorted({str((g.get("status") or {}).get("display_name") or "") for g in groups})),
                "group_entry_periods": " | ".join(sorted({str((g.get("entry_period_type") or {}).get("display_name") or "") for g in groups})),
                "min_lesson_start": min((str(g.get("lesson_start")) for g in groups if g.get("lesson_start")), default=""),
                "max_lesson_end": max((str(g.get("lesson_end")) for g in groups if g.get("lesson_end")), default=""),
                "card_file": str(card_path),
            })
    with (a.output / "card-field-audit.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    summary = {"created_utc": datetime.now(timezone.utc).isoformat(), "cards": len(rows),
               "by_activity": {}, "limits": [
                   "Payment code and cost fields are source metadata, not a verified price at enrolment.",
                   "A nonempty group list or date is not proof that a child can enrol or that a session is running.",
                   "This audit describes saved Navigator cards, not all city provision."]}
    for activity in sorted({r["activity_key"] for r in rows}):
        one = [r for r in rows if r["activity_key"] == activity]
        summary["by_activity"][activity] = {"cards": len(one), "payment_code": value_counts(one, "payment_code"),
            "cost_present": sum(r["cost_present"] for r in one), "activity_status": value_counts(one, "activity_status"),
            "published_address_present": sum(r["published_address_present"] for r in one),
            "cards_with_groups": sum(r["group_count"] > 0 for r in one),
            "cards_with_numeric_age_group": sum(r["numeric_age_group_count"] > 0 for r in one),
            "group_entry_periods": value_counts(one, "group_entry_periods")}
    (a.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
