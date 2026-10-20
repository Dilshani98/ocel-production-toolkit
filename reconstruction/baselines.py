"""Naive baselines. They see only the messy tables (mapped to internal column names), like the toolkit.

B1: hygiene only. Labels, roles, link types and object types are compared by a normalised key
    (trimmed, lower-case, no spaces/underscores/dashes/punctuation); each key is written back as its
    most frequent original spelling. IDs are trimmed, timestamps parsed to UTC, exact duplicate rows
    dropped. No similarity matching, no timestamp repair, no merging.
B2: B1 plus a naive identity rule: objects of the same type with an identical attribute record
    (a blank counts as a value; all-blank records never merge) are merged, but only when the group
    has at most `max_group` members (None = no limit).
"""
import re
import pandas as pd

ID_COLUMNS = {"events": ["_record_id"], "objects": ["_item_id"],
              "relations": ["_record_id", "_item_id"], "o2o": ["_item_id", "_linked_item_id"]}
# Vocabularies normalised together: (column name, tables it appears in)
VOCABULARIES = [("_activity", ["events"]), ("_item_type", ["objects", "relations"]),
                ("_role", ["relations"]), ("_link_type", ["o2o"])]
BLANK = "<blank>"     # printable on purpose: pandas' string hashing stops at a NUL character


def _key(value):
    return re.sub(r"[\W_]+", "", str(value).strip()).casefold()


def _spelling_map(values):
    """Maps every original value to the most frequent original spelling with the same key."""
    counts = values.dropna().value_counts()
    best = {}
    for value, n in sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0]))):   # ties: alphabetical
        best.setdefault(_key(value), value)
    return {value: best[_key(value)] for value in counts.index}


def apply_b1(tables):
    out = {kind: df.copy() for kind, df in tables.items() if kind in ID_COLUMNS}
    report = {}
    for kind, cols in ID_COLUMNS.items():
        for col in cols:
            out[kind][col] = out[kind][col].astype(str).str.strip()
    for col, kinds in VOCABULARIES:
        present = [k for k in kinds if col in out[k]]
        if not present:
            continue
        mapping = _spelling_map(pd.concat([out[k][col] for k in present]))
        changed = 0
        for k in present:
            old = out[k][col]
            new = old.map(mapping).where(old.notna(), old)
            changed += int(((new != old) & old.notna()).sum())
            out[k][col] = new
        report[f"values_respelled{col}"] = changed
    out["events"]["_timestamp"] = pd.to_datetime(out["events"]["_timestamp"], utc=True, format="mixed", errors="coerce")
    for kind in ID_COLUMNS:
        before = len(out[kind])
        out[kind] = out[kind].drop_duplicates().reset_index(drop=True)
        report[f"duplicates_dropped_{kind}"] = before - len(out[kind])
    return out, report


def apply_b2(tables, max_group=2):
    out, report = apply_b1(tables)
    objects = out["objects"]
    attrs = [c for c in objects.columns if c not in ("_item_id", "_item_type")]
    values = objects[attrs].astype("object").where(objects[attrs].notna(), BLANK).astype(str)
    signature = objects["_item_type"].astype(str) + "\x1f" + values.agg("\x1f".join, axis=1)
    mergeable = ~objects[attrs].isna().all(axis=1)

    groups = objects[mergeable].groupby(signature[mergeable])["_item_id"].apply(sorted)
    sizes = groups.map(len)
    keep = sizes >= 2
    if max_group is not None:
        keep &= sizes <= max_group
    canonical = {}
    for members in groups[keep]:
        for m in members:
            canonical[m] = members[0]
    report.update({"groups_merged": int(keep.sum()), "objects_merged_away": len(canonical) - int(keep.sum()),
                   "groups_too_large": int((sizes > max_group).sum()) if max_group is not None else 0})

    rename = lambda s: s.map(lambda v: canonical.get(v, v))
    out["objects"] = objects[~objects["_item_id"].isin(set(canonical) - set(canonical.values()))].reset_index(drop=True)
    out["relations"]["_item_id"] = rename(out["relations"]["_item_id"])
    out["o2o"]["_item_id"] = rename(out["o2o"]["_item_id"])
    out["o2o"]["_linked_item_id"] = rename(out["o2o"]["_linked_item_id"])
    for kind in ("relations", "o2o"):                     # merging can create exact duplicates
        before = len(out[kind])
        out[kind] = out[kind].drop_duplicates().reset_index(drop=True)
        report[f"duplicates_after_merge_{kind}"] = before - len(out[kind])
    out["clusters"] = pd.DataFrame({"_item_id": list(canonical), "_cluster_id": list(canonical.values())})
    return out, report
