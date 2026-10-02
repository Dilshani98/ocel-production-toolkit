import pm4py
import os
import pandas as pd
from injection.ground_truth_log import GroundTruthLog
from injection.patterns import (
    inject_object_clones, inject_missing_e2o, inject_incorrect_o2o,
    inject_timestamp_drift, inject_label_distortion
)

class OCELState:
    # each pattern function chained together

    def __init__(self, ocel):
        self.events = ocel.events.copy()
        self.objects = ocel.objects.copy()
        self.relations = ocel.relations.copy()
        self.o2o = ocel.o2o.copy()


def build_messy_dataset(ocel, severity, seed):
    gt_log = GroundTruthLog()
    state = OCELState(ocel)

    state.objects, state.relations = inject_object_clones(
        state, object_type="SteelSheet", severity=severity, seed=seed, gt_log=gt_log
    )
    state.relations = inject_missing_e2o(
        state, activity_filter="AssembleHinge", severity=severity, seed=seed, gt_log=gt_log
    )
    state.o2o = inject_incorrect_o2o(
        state, qualifier_filter="created from", severity=severity, seed=seed, gt_log=gt_log
    )
    state.events = inject_timestamp_drift(
        state, activity_filter="HeatSteelSheet", severity=severity, seed=seed, gt_log=gt_log
    )
    state.events = inject_label_distortion(
        state, activity_filter="HeatSteelSheet", severity=severity, seed=seed, gt_log=gt_log
    )

    return state, gt_log



def save_messy_dataset(state, gt_log, output_dir, severity, seed):
    os.makedirs(output_dir, exist_ok=True)

    state.events.to_csv(os.path.join(output_dir, f"messy_events_sev{severity}.csv"), index=False)
    state.objects.to_csv(os.path.join(output_dir, f"messy_objects_sev{severity}.csv"), index=False)
    state.relations.to_csv(os.path.join(output_dir, f"messy_relations_sev{severity}.csv"), index=False)
    state.o2o.to_csv(os.path.join(output_dir, f"messy_o2o_sev{severity}.csv"), index=False)

    gt_log.save(os.path.join(output_dir, f"ground_truth_sev{severity}.json"))

    print(f"Saved messy dataset + ground truth for severity {severity} to {output_dir}")