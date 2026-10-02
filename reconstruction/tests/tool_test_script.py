import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pandas as pd
from reconstruction.mapping import SchemaMapping, apply_mapping

events = pd.read_csv(os.path.join(os.path.dirname(__file__), "..", "..", "data", "messy", "messy_events_sev0_15.csv"))

mapping = SchemaMapping(
    record_id_col="record_id",
    activity_col="activity_name",
    timestamp_col="event_time",
    item_id_col="item_id",
    item_type_col="item_category",
)

# mapped_events = apply_mapping(events, mapping, kind="events")
# print(mapped_events.columns.tolist())
# print(mapped_events.head(3))


objects = pd.read_csv(os.path.join(os.path.dirname(__file__), "..", "..", "data", "messy", "messy_objects_sev0_15.csv"))
relations = pd.read_csv(os.path.join(os.path.dirname(__file__), "..", "..", "data", "messy", "messy_relations_sev0_15.csv"))

mapped_objects = apply_mapping(objects, mapping, kind="objects")
print("Objects columns:", mapped_objects.columns.tolist())

mapped_relations = apply_mapping(relations, mapping, kind="relations")
print("Relations columns:", mapped_relations.columns.tolist())