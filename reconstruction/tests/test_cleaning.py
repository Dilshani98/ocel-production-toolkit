import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pandas as pd
from reconstruction.mapping import SchemaMapping, apply_mapping
from reconstruction.cleaning import clean_activity_labels

DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data", "messy")
raw = pd.read_csv(os.path.join(DATA, "messy_events_sev0_15.csv"))

mapping = SchemaMapping(
    record_id_col="record_id", activity_col="activity_name", timestamp_col="event_time",
    item_id_col="item_id", item_type_col="item_category",
    linked_item_id_col="linked_item_id", link_type_col="link_type", role_col="role",
)
events = apply_mapping(raw, mapping, "events")

cleaned, log = clean_activity_labels(events)

print(log.to_string(index=False))
print("labels before:", events["_activity"].nunique())
print("labels after :", cleaned["_activity"].nunique())
print("events changed:", int(log["n_events"].sum()))

assert len(cleaned) == len(events), "row count changed"
assert cleaned["_activity"].nunique() == 11, "expected 11 real activities"
assert log["n_events"].sum() == 886, "expected 886 corrected events"
assert set(log["new_label"]) == {"HeatSteelSheet"}
print("ALL CLEANING TESTS PASSED")