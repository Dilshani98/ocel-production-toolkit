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


def inject_missing_e2o(ocel, activity_filter, severity, seed, gt_log):
# 'Lost Memory' pattern: removes a fraction of event-object relationship
    rng = random.Random(seed)
    relations_df = ocel.relations.copy()

    eligible_mask = relations_df["ocel:activity"] == activity_filter
    eligible_idx = relations_df[eligible_mask].index.tolist()

    n_to_remove = int(len(eligible_idx) * severity)
    to_remove = rng.sample(eligible_idx, n_to_remove)

    for idx in to_remove:
        row = relations_df.loc[idx]
        gt_log.record("missing_e2o", "relation_removed", row["ocel:oid"],
                       {"event_id": row["ocel:eid"], "activity": row["ocel:activity"],
                        "object_type": row["ocel:type"]})

    relations_df = relations_df.drop(index=to_remove)
    return relations_df



def inject_incorrect_o2o(ocel, qualifier_filter, severity, seed, gt_log, max_id_distance=3):
# 'Cuckoo's Egg' pattern: swaps the target of a fraction of object-object relationships to a nearby

    rng = random.Random(seed)
    o2o_df = ocel.o2o.copy()

    eligible_mask = o2o_df["ocel:qualifier"] == qualifier_filter
    eligible_idx = o2o_df[eligible_mask].index.tolist()
    n_to_swap = int(len(eligible_idx) * severity)
    targets = rng.sample(eligible_idx, n_to_swap)

    all_target_ids = set(o2o_df.loc[eligible_idx, "ocel:oid_2"])

    def extract_number(oid):
        match = re.search(r"(\d+)$", oid)
        return int(match.group(1)) if match else None

    for idx in targets:
        row = o2o_df.loc[idx]
        original_target = row["ocel:oid_2"]
        prefix = re.sub(r"\d+$", "", original_target)
        num = extract_number(original_target)

        candidates = [f"{prefix}{num + d}" for d in range(-max_id_distance, max_id_distance + 1)
                      if d != 0 and f"{prefix}{num + d}" in all_target_ids]
        if not candidates:
            continue

        wrong_target = rng.choice(candidates)
        o2o_df.loc[idx, "ocel:oid_2"] = wrong_target

        gt_log.record("incorrect_o2o", "target_swapped", row["ocel:oid"],
                       {"original_target": original_target, "wrong_target": wrong_target,
                        "qualifier": qualifier_filter})

    return o2o_df


