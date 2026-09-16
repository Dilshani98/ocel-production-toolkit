import pm4py
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from injection.ground_truth_log import GroundTruthLog
from injection.patterns import inject_object_clones, validate_object_clones, inject_missing_e2o


ocel = pm4py.read_ocel2_xml("socel2_hinge.xml")


# --------------------Checking the object clone injection and validation:

gt_log = GroundTruthLog()

messy_objects, messy_relations = inject_object_clones(
    ocel, object_type="SteelSheet", severity=0.15, seed=42, gt_log=gt_log
)

print(f"Original: {len(ocel.objects)}, Messy: {len(messy_objects)}")

print(gt_log.changes[0])  # Show a few logged changes

print(messy_objects[messy_objects["ocel:oid"].str.startswith("SS-")].head())

print("Problems found:", validate_object_clones(messy_objects, gt_log))






# -----------------Checking the missing event-object relation injection:

# gt_log2 = GroundTruthLog()

# messy_relations2 = inject_missing_e2o(
#     ocel, activity_filter="AssembleHinge", severity=0.10, seed=42, gt_log=gt_log2
# )

# print(f"Original relations: {len(ocel.relations)}, After removal: {len(messy_relations2)}")
# print(f"Changes logged: {len(gt_log2.changes)}")



# Which events had relations removed?
# removed_event_ids = {c["details"]["event_id"] for c in gt_log2.changes}

# # For those events, how many relations do they have left in the messy data?
# remaining_counts = messy_relations2[messy_relations2["ocel:eid"].isin(removed_event_ids)] \
#     .groupby("ocel:eid").size() 

# fully_orphaned = [eid for eid in removed_event_ids if eid not in remaining_counts.index]

# print(f"Events affected by removal: {len(removed_event_ids)}")
# print(f"Events with zero relations left (fully orphaned): {len(fully_orphaned)}")


# print(ocel.o2o.head(10) if hasattr(ocel, 'o2o') and ocel.o2o is not None else "No O2O table found")
# print(ocel.o2o.shape if hasattr(ocel, 'o2o') and ocel.o2o is not None else "")






# ----------------------Checking the incorrect object-object relation injection:

# gt_log3 = GroundTruthLog()
# messy_o2o = inject_incorrect_o2o(
#     ocel, qualifier_filter="created from", severity=0.10, seed=42, gt_log=gt_log3
# )
# print(f"Original O2O rows: {len(ocel.o2o)}, Messy O2O rows: {len(messy_o2o)}")
# print(f"Changes logged: {len(gt_log3.changes)}")
# print(messy_o2o.head())


# # Look at a few real logged changes
# for change in gt_log3.changes[:5]:
#     print(change)

# # Confirm those specific rows actually changed in messy_o2o
# sample_oid = gt_log3.changes[0]["target_id"]
# print(messy_o2o[messy_o2o["ocel:oid"] == sample_oid])