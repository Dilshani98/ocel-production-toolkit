import sys, os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
from reconstruction.mapping import SchemaMapping, apply_mapping
from reconstruction.profiling import build_profile_report

DATA_DIR = os.path.join(PROJECT_ROOT, "data", "messy")
TAG = "sev0_15"
load = lambda n: pd.read_csv(os.path.join(DATA_DIR, f"messy_{n}_{TAG}.csv"))

mapping = SchemaMapping("record_id", "activity_name", "event_time", "item_id",
                        "item_category", "linked_item_id", "link_type", "role")

events = apply_mapping(load("events"), mapping, "events")
objects = apply_mapping(load("objects"), mapping, "objects")
relations = apply_mapping(load("relations"), mapping, "relations")
o2o = apply_mapping(load("o2o"), mapping, "o2o")

report = build_profile_report(events, objects, relations, o2o)

for k, v in report.items():
    if k == "label_suspects":
        print(f"\nLabel suspects ({len(v)}):")
        print(v.to_string(index=False))
    else:
        print(f"{k}: {v}")