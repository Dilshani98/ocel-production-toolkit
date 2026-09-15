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



def inject_object_clones(ocel, object_type, severity, seed, gt_log):
#    Duplicates objects under a new ID, then reassigns some of their event-object relations to the new ID.

    rng = random.Random(seed)
    objects_df = ocel.objects.copy()
    relations_df = ocel.relations.copy()
    existing_ids = set(objects_df["ocel:oid"])

    eligible = objects_df[objects_df["ocel:type"] == object_type]
    n_to_clone = max(1, int(len(eligible) * severity))
    targets = rng.sample(list(eligible["ocel:oid"]), n_to_clone)

    new_objects = []
    for original_id in targets:
        clone_id = _generate_alias_id(rng, object_type, existing_ids)
        existing_ids.add(clone_id)

        original_row = objects_df[objects_df["ocel:oid"] == original_id].iloc[0].copy()
        original_row["ocel:oid"] = clone_id
        new_objects.append(original_row)
        gt_log.record("object_clones", "clone_created", original_id, {"clone_id": clone_id})

        mask = relations_df["ocel:oid"] == original_id
        related_rows = relations_df[mask].index.tolist()
        rng.shuffle(related_rows)
        half = len(related_rows) // 2
        reassign_to_clone = related_rows[:half]

        relations_df.loc[reassign_to_clone, "ocel:oid"] = clone_id
        for idx in reassign_to_clone:
            gt_log.record("object_clones", "relation_reassigned", original_id,
                           {"clone_id": clone_id, "event_id": relations_df.loc[idx, "ocel:eid"]})

    objects_df = pd.concat([objects_df, pd.DataFrame(new_objects)], ignore_index=True)
    return objects_df, relations_df
 


