import random
import pandas as pd

def inject_object_clones(ocel, object_type, severity, seed, gt_log):
    """
    Duplicates a fraction of objects of the given type under a new ID,
    then reassigns some of their event-object relations to the new ID.
    """
    rng = random.Random(seed)

    objects_df = ocel.objects.copy()
    relations_df = ocel.relations.copy()

    #Pick which objects of this type to "clone"
    eligible = objects_df[objects_df["ocel:type"] == object_type]
    n_to_clone = max(1, int(len(eligible) * severity))
    targets = rng.sample(list(eligible["ocel:oid"]), n_to_clone)

    new_objects = []
    for original_id in targets:
        clone_id = f"{original_id}_clone"

        #Create the clone object (same type, same attributes)
        original_row = objects_df[objects_df["ocel:oid"] == original_id].iloc[0].copy()
        original_row["ocel:oid"] = clone_id
        new_objects.append(original_row)
        gt_log.record("object_clones", "clone_created", original_id, {"clone_id": clone_id})

        #Split this object's relations between original and clone
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