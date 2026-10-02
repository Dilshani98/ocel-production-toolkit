import pm4py
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from injection.run_injection import build_messy_dataset, save_messy_dataset, to_fragmented_format


# ocel = pm4py.read_ocel2_xml("socel2_hinge.xml")

ocel = pm4py.read_ocel2_xml(os.path.join(os.path.dirname(__file__), "..", "socel2_hinge.xml")) #debug the import error

state, gt_log = build_messy_dataset(ocel, severity=0.15, seed=42)

print(f"Total changes logged: {len(gt_log.changes)}")
print(f"Pattern breakdown:")


from collections import Counter
print(Counter(c["pattern"] for c in gt_log.changes))


timestamp_ids = {c["target_id"] for c in gt_log.changes if c["pattern"] == "timestamp_drift"}
label_ids = {c["target_id"] for c in gt_log.changes if c["pattern"] == "label_distortion"}

overlap = timestamp_ids & label_ids

print(f"Events with BOTH timestamp drift AND label distortion: {len(overlap)}")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "messy")

events_out, objects_out, relations_out, o2o_out = to_fragmented_format(
    state.events, state.objects, state.relations, state.o2o
)

save_messy_dataset(events_out, objects_out, relations_out, o2o_out,
                   gt_log, OUTPUT_DIR, severity=0.15)

# quick self-checks
print(events_out.columns.tolist())
print("Duplicate O2O rows:", o2o_out.duplicated().sum())