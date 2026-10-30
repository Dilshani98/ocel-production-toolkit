"""Cut a small demo subset from the damaged sOCEL 2.0 data (seed 42, 15%) into examples/socel_subset/.

    python examples/make_socel_subset.py [--start 0.10] [--end 0.17]

Needs data/messy (run tests/generate_datasets.py first). The subset is derived from the sOCEL 2.0 log, so it is
only committed once the dataset's licence allows redistribution; until then it is generated locally (the folder
is in .gitignore).

How rows are chosen (file order is time order):
    1. a window of event rows, from --start to --end as shares of the file (default 10%-17%; this window was
       chosen because it overlaps the start of the drifted timestamp block, so the demo shows every kind of repair)
    2. "whole" objects: objects all of whose events fall inside the window
    3. events: the window's events that involve at least one whole object
    4. objects: every object those events involve (shared resources such as machines appear with these events only)
    5. links: every event-to-object link of those events; object-to-object links whose two ends are both kept
Columns keep the damaged data's names; mapping.json says which column is which.
"""
import argparse
import json
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOURCE = os.path.join(ROOT, "data", "messy")
TAG = "sev0_15"
COLUMNS = {"record_id_col": "record_id", "activity_col": "activity_name", "timestamp_col": "event_time",
           "item_id_col": "item_id", "item_type_col": "item_category", "linked_item_id_col": "linked_item_id",
           "link_type_col": "link_type", "role_col": "role"}


def subset(tables, start, end):
    """tables: events, objects, relations, o2o with the damaged data's column names. Returns the four subsets."""
    ev, rel = tables["events"], tables["relations"]
    window = set(ev["record_id"].iloc[int(len(ev) * start):int(len(ev) * end)])
    linked = rel[rel["record_id"].isin(window)]["item_id"].unique()
    outside = set(rel[~rel["record_id"].isin(window)]["item_id"])
    whole = set(linked) - outside
    keep_events = set(rel[rel["record_id"].isin(window) & rel["item_id"].isin(whole)]["record_id"])
    rel_out = rel[rel["record_id"].isin(keep_events)]
    objects = set(rel_out["item_id"])
    o2o = tables["o2o"]
    return {"events": ev[ev["record_id"].isin(keep_events)],
            "objects": tables["objects"][tables["objects"]["item_id"].isin(objects)],
            "relations": rel_out,
            "o2o": o2o[o2o["item_id"].isin(objects) & o2o["linked_item_id"].isin(objects)]}


def damage_inside(sub, truth):
    """For the printed summary only: how much of each kind of damage falls inside the subset."""
    ids = set(sub["events"]["record_id"]) | set(sub["objects"]["item_id"])
    out = {}
    for c in truth:
        if c["target_id"] in ids or c.get("details", {}).get("clone_id") in ids:
            out[c["pattern"]] = out.get(c["pattern"], 0) + 1
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cut the sOCEL 2.0 demo subset.")
    parser.add_argument("--start", type=float, default=0.10)
    parser.add_argument("--end", type=float, default=0.17)
    parser.add_argument("--out", default=os.path.join(HERE, "socel_subset"))
    args = parser.parse_args(argv)
    if not os.path.exists(os.path.join(SOURCE, f"messy_events_{TAG}.csv")):
        raise SystemExit("data/messy is missing: run python tests/generate_datasets.py first")
    tables = {k: pd.read_csv(os.path.join(SOURCE, f"messy_{k}_{TAG}.csv"), low_memory=False)
              for k in ("events", "objects", "relations", "o2o")}
    sub = subset(tables, args.start, args.end)
    os.makedirs(args.out, exist_ok=True)
    for k, df in sub.items():
        df.to_csv(os.path.join(args.out, f"{k}.csv"), index=False, lineterminator="\n")
    config = {"folder": os.path.relpath(args.out, ROOT).replace(os.sep, "/"),
              "files": {k: f"{k}.csv" for k in sub}, "columns": COLUMNS}
    with open(os.path.join(args.out, "mapping.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
    print(", ".join(f"{k}: {len(sub[k])} of {len(tables[k])} rows ({len(sub[k]) / len(tables[k]):.1%})" for k in sub))
    truth = json.load(open(os.path.join(SOURCE, f"ground_truth_{TAG}.json")))
    print("damage records inside the subset (printed only, not written):", damage_inside(sub, truth))


if __name__ == "__main__":
    main()
