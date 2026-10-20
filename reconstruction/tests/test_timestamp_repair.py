import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pandas as pd
from reconstruction.mapping import SchemaMapping, apply_mapping
from reconstruction.cleaning import clean_activity_labels, repair_timestamp_drift

DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data", "messy")
TAG = sys.argv[1] if len(sys.argv) > 1 else "sev0_15"
raw = pd.read_csv(os.path.join(DATA, f"messy_events_{TAG}.csv"))
gt = json.load(open(os.path.join(DATA, f"ground_truth_{TAG}.json")))

mapping = SchemaMapping(
    record_id_col="record_id", activity_col="activity_name", timestamp_col="event_time",
    item_id_col="item_id", item_type_col="item_category",
    linked_item_id_col="linked_item_id", link_type_col="link_type", role_col="role",
)
events = apply_mapping(raw, mapping, "events")

# The toolkit pipeline: labels first, then timestamps. No ground truth used here.
events, _ = clean_activity_labels(events)
repaired, report, log = repair_timestamp_drift(events)
print(report)

# Scoring (ground truth used only below).
truth = {g["target_id"]: pd.to_datetime(g["details"]["original_timestamp"], utc=True)
         for g in gt if g["pattern"] == "timestamp_drift"}
before = pd.to_datetime(events["_timestamp"], utc=True, format="mixed")
after = repaired["_timestamp"]
ids = events["_record_id"]

drifted = ids.isin(truth)
orig = ids.map(truth)
err_before = (before[drifted] - orig[drifted]).dt.total_seconds().abs()
err_after = (after[drifted] - orig[drifted]).dt.total_seconds().abs()
restored = int((err_after == 0).sum())
untouched_changed = int((~drifted & (after != before)).sum())

print(f"drifted events:           {int(drifted.sum())}")
print(f"restored exactly:         {restored}")
print(f"mean error before/after:  {err_before.mean():.1f}s / {err_after.mean():.1f}s")
print(f"untouched events changed: {untouched_changed}")

assert report["status"] == "repaired"
assert report["culprit_activity"] == "HeatSteelSheet"
assert untouched_changed == 0, "repair changed events that were not drifted"
assert report["backward_after"] < report["backward_before"] * 0.05
print("ALL TIMESTAMP REPAIR TESTS PASSED")