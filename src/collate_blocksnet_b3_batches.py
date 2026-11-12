"""Write every B3 direction result by reading each completed checkpoint once."""
import argparse
import json
import pickle
from pathlib import Path

import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    root = args.input
    settings = json.loads((root / "settings.json").read_text(encoding="utf-8"))
    batch_paths = sorted((root / "batches").glob("batch-*.pkl"))
    if not batch_paths:
        raise RuntimeError("No checkpoint batches found")
    expected = (30611 + int(settings["batch_size"]) - 1) // int(settings["batch_size"])
    if len(batch_paths) != expected:
        raise RuntimeError(f"Expected {expected} batches, found {len(batch_paths)}")
    parts = {name: [] for name, *_ in settings["case"]}
    for idx, path in enumerate(batch_paths, 1):
        with path.open("rb") as handle:
            batch = pickle.load(handle)
        if set(batch) != set(parts):
            raise RuntimeError(f"Unexpected case set in {path.name}")
        for name, frame in batch.items():
            parts[name].append(frame)
        if idx % 100 == 0 or idx == len(batch_paths):
            print(f"loaded {idx}/{len(batch_paths)}", flush=True)
    summary_cases = {}
    for name, frames in parts.items():
        out = pd.concat(frames, ignore_index=True)
        if len(out) != 30611 or not out.origin_id.astype(str).is_unique:
            raise RuntimeError(f"{name}: incomplete or duplicate origins")
        folder = root / name
        folder.mkdir(exist_ok=True)
        out.to_csv(folder / "b3-by-origin.csv", index=False, encoding="utf-8-sig")
        summary_cases[name] = {"origins": int(len(out)), "network_covered": int(out.network_covered.eq(True).sum())}
    summary = {"scenario": "B3", "status": "computed", "origins": 30611,
               "direction_cases": len(parts), "assembled_from_completed_batches": len(batch_paths),
               "cases": summary_cases, "settings": settings}
    (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
