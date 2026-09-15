import random
import pandas as pd


def _generate_alias_id(rng, object_type, existing_ids):
    #Creates a plausible, independent-looking ID for a cloned object

    prefix_map = {
        "SteelSheet": "SS", "FormedPart": "FP", "MalePart": "MP",
        "FemalePart": "FEP", "Hinge": "HG", "SteelPin": "PIN",
    }
    prefix = prefix_map.get(object_type, "OBJ")
    while True:
        candidate = f"{prefix}-{rng.randint(100000, 999999)}"
        if candidate not in existing_ids:
            return candidate


def validate_object_clones(objects_df, gt_log):
    # Check every clone exists in the object table
    problems = []
    for change in gt_log.changes:
        if change["change_type"] == "clone_created":
            clone_id = change["details"]["clone_id"]
            if clone_id not in objects_df["ocel:oid"].values:
                problems.append(f"Missing clone: {clone_id}")
    return problems


