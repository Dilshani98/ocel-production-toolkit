import os, sys
import pm4py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from injection.run_injection import build_messy_dataset, save_messy_dataset, to_fragmented_format

ocel = pm4py.read_ocel2_xml(os.path.join(os.path.dirname(__file__), "..", "socel2_hinge.xml"))
OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "messy"))

for severity in [0.05, 0.15, 0.30]:
    state, gt_log = build_messy_dataset(ocel, severity=severity, seed=42)
    ev, ob, rel, o2o = to_fragmented_format(state.events, state.objects, state.relations, state.o2o)
    save_messy_dataset(ev, ob, rel, o2o, gt_log, OUT, severity)
    print(f"severity {severity}: {len(gt_log.changes)} changes")