import pm4py
from injection.ground_truth_log import GroundTruthLog
from injection.patterns import inject_object_clones

ocel = pm4py.read_ocel2_xml("socel2_hinge.xml")

eligible = ocel.objects[ocel.objects["ocel:type"] == "Workstation"]
print(f"Total Workstation objects: {len(eligible)}")


# gt_log = GroundTruthLog()

# messy_objects, messy_relations = inject_object_clones(
#     ocel, object_type="Workstation", severity=0.15, seed=42, gt_log=gt_log
# )

# print(f"Original objects: {len(ocel.objects)}, Messy objects: {len(messy_objects)}")
# print(f"Ground truth changes logged: {len(gt_log.changes)}")

# print(f"Original relations: {len(ocel.relations)}, Messy relations: {len(messy_relations)}")

# gt_log.save("ground_truth_changes.json")