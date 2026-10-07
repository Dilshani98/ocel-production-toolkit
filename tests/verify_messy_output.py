import os, json
import pandas as pd

D = os.path.join(os.path.dirname(__file__), "..", "data", "messy")
tag = "sev0_15"
ev  = pd.read_csv(os.path.join(D, f"messy_events_{tag}.csv"))
obj = pd.read_csv(os.path.join(D, f"messy_objects_{tag}.csv"))
rel = pd.read_csv(os.path.join(D, f"messy_relations_{tag}.csv"))
o2o = pd.read_csv(os.path.join(D, f"messy_o2o_{tag}.csv"))
gt  = json.load(open(os.path.join(D, f"ground_truth_{tag}.json")))

# 1. No OCEL-style column names left in any file
for name, df in [("events", ev), ("objects", obj), ("relations", rel), ("o2o", o2o)]:
    print(name, "ocel: columns left ->", [c for c in df.columns if c.startswith("ocel:")])

# 2. Timestamp ground truth is correct for ALL logged events
ev["event_time"] = pd.to_datetime(ev["event_time"], utc=True)
now = ev.set_index("record_id")["event_time"]
ts = [c for c in gt if c["pattern"] == "timestamp_drift"]
bad = 0
for c in ts:
    orig = pd.to_datetime(c["details"]["original_timestamp"], utc=True)
    if now[c["target_id"]] - orig != pd.Timedelta(seconds=c["details"]["drift_seconds"]):
        bad += 1
print("Timestamp entries wrong:", bad, "of", len(ts))

# 3. Nothing points to something that doesn't exist
print("relations leaking clean columns:",
      [c for c in rel.columns if c in ("activity_name", "event_time")])
print("relations -> unknown event :", (~rel["record_id"].isin(ev["record_id"])).sum())
print("relations -> unknown object:", (~rel["item_id"].isin(obj["item_id"])).sum())
print("o2o unknown source         :", (~o2o["item_id"].isin(obj["item_id"])).sum())
print("o2o unknown target         :", (~o2o["linked_item_id"].isin(obj["item_id"])).sum())