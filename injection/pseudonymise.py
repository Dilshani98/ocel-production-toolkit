import random
import re
from collections import Counter

ID_PATTERN = re.compile(r"^(.*?)(\d+)$")


def _split(oid):
    match = ID_PATTERN.match(str(oid))
    return (match.group(1), match.group(2)) if match else (str(oid), None)


def _shuffled_numbers(ids, prefix, rng, digits_like):
    # Give `ids` the numbers 1..n in random order, written as prefix + number.
    # Keeps zero-padding if the original numbers were padded (e.g. "01").
    numbers = list(range(1, len(ids) + 1))
    rng.shuffle(numbers)
    padded = any(d.startswith("0") for d in digits_like)
    width = max(len(d) for d in digits_like) if padded else 0
    return {old: f"{prefix}{str(n).zfill(width)}" for old, n in zip(ids, numbers)}


def _object_id_map(objects_df, rng):
    # Per object type: if most IDs share one prefix, every ID of that type (clones included)
    # is renamed into that prefix with shuffled numbers. Otherwise each prefix is shuffled on its own.
    mapping = {}
    for _, group in objects_df.groupby("ocel:type", sort=True):
        ids = sorted(group["ocel:oid"].astype(str))
        prefixes = Counter(_split(i)[0] for i in ids)
        main, count = prefixes.most_common(1)[0]
        if count / len(ids) >= 0.5 and len(ids) > 1:
            digits = [_split(i)[1] for i in ids if _split(i)[0] == main]
            mapping.update(_shuffled_numbers(ids, main, rng, digits))
        else:
            mapping.update(_prefix_map(ids, rng))
    return mapping


def _prefix_map(ids, rng):
    # Shuffle numbers within each ID prefix. IDs alone in their prefix keep their ID.
    groups = {}
    for i in sorted(map(str, ids)):
        groups.setdefault(_split(i)[0], []).append(i)
    mapping = {}
    for prefix, members in groups.items():
        if len(members) == 1:
            mapping[members[0]] = members[0]
        else:
            mapping.update(_shuffled_numbers(members, prefix, rng, [_split(m)[1] for m in members]))
    return mapping


def _natural_key(oid):
    prefix, digits = _split(oid)
    return (prefix, int(digits) if digits else -1)


def check_no_dangling_ids(events_df, objects_df, relations_df, o2o_df):
    events, objects = set(events_df["ocel:eid"]), set(objects_df["ocel:oid"])
    assert events_df["ocel:eid"].is_unique, "duplicate event IDs"
    assert objects_df["ocel:oid"].is_unique, "duplicate object IDs"
    assert relations_df["ocel:eid"].isin(events).all(), "relation points to unknown event"
    assert relations_df["ocel:oid"].isin(objects).all(), "relation points to unknown object"
    assert o2o_df["ocel:oid"].isin(objects).all(), "o2o source is unknown"
    assert o2o_df["ocel:oid_2"].isin(objects).all(), "o2o target is unknown"


def pseudonymise_ids(state, seed, gt_log, event_prefix="e_"):
    # Renames every ID so that ID text and numbers carry no information. Objects: numbers are
    # shuffled within their type's prefix (clones look like any other object). Events: all get
    # one prefix and shuffled numbers, so an event ID does not name its activity or its outcome.
    # The ground truth is rewritten to the new IDs and gets one "ids_renamed" record mapping
    # clean-log IDs to the new IDs.
    rng = random.Random(seed)
    clone_ids = {c["details"]["clone_id"] for c in gt_log.changes if c["change_type"] == "clone_created"}

    obj_map = _object_id_map(state.objects, rng)
    ev_map = _shuffled_numbers(sorted(map(str, state.events["ocel:eid"])), event_prefix, rng, [])
    assert len(set(obj_map.values())) == len(obj_map), "object renaming is not one-to-one"
    assert len(set(ev_map.values())) == len(ev_map), "event renaming is not one-to-one"

    state.events["ocel:eid"] = state.events["ocel:eid"].map(ev_map)
    state.objects["ocel:oid"] = state.objects["ocel:oid"].map(obj_map)
    state.relations["ocel:eid"] = state.relations["ocel:eid"].map(ev_map)
    state.relations["ocel:oid"] = state.relations["ocel:oid"].map(obj_map)
    state.o2o["ocel:oid"] = state.o2o["ocel:oid"].map(obj_map)
    state.o2o["ocel:oid_2"] = state.o2o["ocel:oid_2"].map(obj_map)

    # Objects are written in ID order, so appended clone rows end up at random positions.
    # Events keep their order (file order is evidence for timestamp repair); relation and O2O
    # rows were changed in place and keep their positions.
    keys = [_natural_key(oid) for oid in state.objects["ocel:oid"]]
    order = sorted(range(len(keys)), key=keys.__getitem__)
    state.objects = state.objects.iloc[order].reset_index(drop=True)

    check_no_dangling_ids(state.events, state.objects, state.relations, state.o2o)

    both = {**obj_map, **ev_map}
    for change in gt_log.changes:
        change["target_id"] = both.get(change["target_id"], change["target_id"])
        change["details"] = {k: both.get(v, v) if isinstance(v, str) else v
                             for k, v in change["details"].items()}

    clean_objects = {old: new for old, new in obj_map.items() if old not in clone_ids}
    gt_log.record("pseudonymisation", "ids_renamed", "all",
                  {"note": "maps clean-log IDs to IDs in the messy files; clone IDs are in clone_created records",
                   "objects": clean_objects, "events": ev_map})
    return state
