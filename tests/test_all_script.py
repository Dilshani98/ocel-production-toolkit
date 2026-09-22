import pm4py
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from injection.run_injection import build_messy_dataset, save_messy_dataset
from injection.ground_truth_log import GroundTruthLog
from injection.patterns import inject_object_clones, validate_object_clones, inject_missing_e2o, inject_timestamp_drift, inject_incorrect_o2o, inject_label_distortion

# ocel = pm4py.read_ocel2_xml("socel2_hinge.xml")

ocel = pm4py.read_ocel2_xml(os.path.join(os.path.dirname(__file__), "..", "socel2_hinge.xml"))

state, gt_log = build_messy_dataset(ocel, severity=0.15, seed=42)

print(f"Total changes logged: {len(gt_log.changes)}")
print(f"Pattern breakdown:")


from collections import Counter
print(Counter(c["pattern"] for c in gt_log.changes))


timestamp_ids = {c["target_id"] for c in gt_log.changes if c["pattern"] == "timestamp_drift"}
label_ids = {c["target_id"] for c in gt_log.changes if c["pattern"] == "label_distortion"}

overlap = timestamp_ids & label_ids

print(f"Events with BOTH timestamp drift AND label distortion: {len(overlap)}")

save_messy_dataset(state, gt_log, output_dir="../data/messy", severity=0.15, seed=42)