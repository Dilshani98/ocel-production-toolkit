import sys, os

# Project root is two folders up from reconstruction/tests/
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
from reconstruction.mapping import SchemaMapping, apply_mapping

DATA_DIR = os.path.join(PROJECT_ROOT, "data", "messy")
TAG = "sev0_15"


def load(name):
    return pd.read_csv(os.path.join(DATA_DIR, f"messy_{name}_{TAG}.csv"))


events = load("events")
objects = load("objects")
relations = load("relations")
o2o = load("o2o")

mapping = SchemaMapping(
    record_id_col="record_id",
    activity_col="activity_name",
    timestamp_col="event_time",
    item_id_col="item_id",
    item_type_col="item_category",
    linked_item_id_col="linked_item_id",
    link_type_col="link_type",
    role_col="role",
)

# ---------- 1. Mapping works on all four file types ----------
m_events = apply_mapping(events, mapping, kind="events")
m_objects = apply_mapping(objects, mapping, kind="objects")
m_relations = apply_mapping(relations, mapping, kind="relations")
m_o2o = apply_mapping(o2o, mapping, kind="o2o")

print("Events   :", m_events.columns.tolist()[:3], "...")
print("Objects  :", m_objects.columns.tolist()[:2], "...")
print("Relations:", m_relations.columns.tolist())
print("O2O      :", m_o2o.columns.tolist())

assert {"_record_id", "_activity", "_timestamp"} <= set(m_events.columns)
assert {"_item_id", "_item_type"} <= set(m_objects.columns)
assert set(m_relations.columns) == {"_record_id", "_item_id", "_item_type", "_role"}
assert set(m_o2o.columns) == {"_item_id", "_linked_item_id", "_link_type"}

# ---------- 2. Check whether Row counts change ----------
assert len(m_events) == len(events)
assert len(m_objects) == len(objects)
assert len(m_relations) == len(relations)
assert len(m_o2o) == len(o2o)
print("Row counts unchanged by mapping: OK")

# ---------- 3. Check whether relations not carry the clean label/time ----------
assert "_activity" not in m_relations.columns
assert "_timestamp" not in m_relations.columns
print("No clean activity/timestamp leaking in relations: OK")

# ---------- 4. Wrong column name must fail ----------
bad_mapping = SchemaMapping(
    record_id_col="record_id",
    activity_col="this_column_does_not_exist",
    timestamp_col="event_time",
    item_id_col="item_id",
    item_type_col="item_category",
    linked_item_id_col="linked_item_id",
    link_type_col="link_type",
    role_col="role",
)
try:
    apply_mapping(events, bad_mapping, kind="events")
    raise AssertionError("Bad column name was NOT caught")
except ValueError as e:
    print("Correctly caught bad column:", e)

# ---------- 5. Unknown kind must fail ----------
try:
    apply_mapping(o2o, mapping, kind="o2o_typo")
    raise AssertionError("Unknown kind was NOT caught")
except ValueError as e:
    print("Correctly caught unknown kind:", e)

print("\nAll mapping tests passed.")