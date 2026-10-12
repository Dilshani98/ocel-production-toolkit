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

def to_fragmented_format(events_df, objects_df, relations_df, o2o_df):
    """Renames OCEL-style columns to generic source-system names, so the
    saved data looks like a raw export, not an OCEL file."""
    events_out = events_df.rename(columns={
        "ocel:eid": "record_id", "ocel:activity": "activity_name",
        "ocel:timestamp": "event_time"})
    objects_out = objects_df.rename(columns={
        "ocel:oid": "item_id", "ocel:type": "item_category"})
    relations_out = relations_df.drop(columns=["ocel:activity", "ocel:timestamp"]).rename(columns={
    "ocel:eid": "record_id",
    "ocel:oid": "item_id",
    "ocel:type": "item_category",
    "ocel:qualifier": "role",
    }) 
    o2o_out = o2o_df.rename(columns={
        "ocel:oid": "item_id", "ocel:oid_2": "linked_item_id",
        "ocel:qualifier": "link_type"})
    return events_out, objects_out, relations_out, o2o_out


def save_messy_dataset(events_df, objects_df, relations_df, o2o_df, gt_log, output_dir, severity):
    os.makedirs(output_dir, exist_ok=True)
    tag = str(severity).replace(".", "_")
    events_df.to_csv(os.path.join(output_dir, f"messy_events_sev{tag}.csv"), index=False)
    objects_df.to_csv(os.path.join(output_dir, f"messy_objects_sev{tag}.csv"), index=False)
    relations_df.to_csv(os.path.join(output_dir, f"messy_relations_sev{tag}.csv"), index=False)
    o2o_df.to_csv(os.path.join(output_dir, f"messy_o2o_sev{tag}.csv"), index=False)
    gt_log.save(os.path.join(output_dir, f"ground_truth_sev{tag}.json"))
    print(f"Saved messy dataset + ground truth for severity {severity} to {output_dir}")