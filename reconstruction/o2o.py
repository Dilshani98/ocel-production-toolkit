"""Incorrect O2O detection and repair (stage 10): finds object-to-object links that the behaviour does not
support and rewrites them only when the right targets are determined. Never deletes a link (except in the
comparison baseline B5).

Uses only the (cleaned) messy tables. No type names, activity names or ID text are used.
1. Groups = (link type, source type, target type). A link is "supported" if its two objects share an event.
   A group is verifiable only if at least min_support of its links are supported and at least
   min_meeting_share of the supported pairs meet in one activity (the group's meeting activity).
2. Detect: a link in a verifiable group whose two objects share no event.
3. Repair (set rule): per source and group, U = its unsupported links and C = the objects of the target type
   in the source's meeting-activity events that the source is not already linked to in this group.
   Replace only if |C| = |U| >= 1 (for one link: the unique candidate). Otherwise leave the links unchanged
   and list them as flagged.
"""
from collections import Counter
from dataclasses import dataclass, asdict

import pandas as pd


@dataclass
class O2OSettings:
    min_support: float = 0.5          # share of a group's links that must be supported to check the group
    min_meeting_share: float = 0.9    # share of supported pairs that must meet in one activity


def repair_o2o(tables, settings=None, delete=False):
    """Returns (tables with repaired O2O, report, decisions table).
    delete=True is the comparison baseline B5: unsupported links in verifiable groups are removed instead."""
    settings = settings or O2OSettings()
    out = {k: v.copy() for k, v in tables.items()}
    types = tables["objects"].drop_duplicates("_item_id").set_index("_item_id")["_item_type"]
    activity = tables["events"].drop_duplicates("_record_id").set_index("_record_id")["_activity"]
    rel = tables["relations"][["_record_id", "_item_id"]].drop_duplicates()
    obj_events = rel.groupby("_item_id")["_record_id"].agg(set).to_dict()
    ev_objs = rel.groupby("_record_id")["_item_id"].agg(set).to_dict()

    o = tables["o2o"].reset_index(drop=True).copy()
    o["src_type"] = o["_item_id"].map(types)
    o["tgt_type"] = o["_linked_item_id"].map(types)
    shared = [obj_events.get(x, set()) & obj_events.get(y, set()) for x, y in zip(o["_item_id"], o["_linked_item_id"])]
    o["supported"] = [len(s) > 0 for s in shared]
    o["meets_in"] = [Counter(activity.get(e) for e in s).most_common(1)[0][0] if s else None for s in shared]

    groups, report_groups = {}, []
    for key, g in o.dropna(subset=["src_type", "tgt_type"]).groupby(["_link_type", "src_type", "tgt_type"]):
        support = float(g["supported"].mean())
        meet = g.loc[g["supported"], "meets_in"].value_counts()
        meet_share = float(meet.iloc[0] / meet.sum()) if len(meet) else 0.0
        verifiable = support >= settings.min_support and meet_share >= settings.min_meeting_share
        groups[key] = meet.index[0] if verifiable else None
        report_groups.append({"link_type": key[0], "source_type": key[1], "target_type": key[2], "links": len(g),
                              "support": support, "meeting_share": meet_share, "verifiable": verifiable})
    o["meeting_activity"] = [groups.get((q, s, t)) for q, s, t in zip(o["_link_type"], o["src_type"], o["tgt_type"])]
    o["detected"] = o["meeting_activity"].notna() & ~o["supported"]

    decisions = o.loc[o["detected"], ["_item_id", "_linked_item_id", "_link_type", "tgt_type"]].copy()
    decisions["new_target"], decisions["status"] = None, "flagged"
    if delete:
        decisions["status"] = "removed"
        out["o2o"] = tables["o2o"].reset_index(drop=True).loc[~o["detected"].values].reset_index(drop=True)
    else:
        linked = o.groupby(["_item_id", "_link_type", "tgt_type"])["_linked_item_id"].agg(set).to_dict()
        new_o2o = tables["o2o"].reset_index(drop=True).copy()
        for (x, q, t), g in decisions.groupby(["_item_id", "_link_type", "tgt_type"]):
            a = o.loc[g.index[0], "meeting_activity"]
            pool = {z for e in obj_events.get(x, set()) if activity.get(e) == a
                    for z in ev_objs.get(e, set()) if types.get(z) == t and z != x}
            candidates = sorted(pool - linked.get((x, q, t), set()))
            if len(candidates) == len(g) >= 1:
                for idx, z in zip(sorted(g.index), candidates):
                    new_o2o.at[idx, "_linked_item_id"] = z
                    decisions.at[idx, "new_target"], decisions.at[idx, "status"] = z, "repaired"
        out["o2o"] = new_o2o.drop_duplicates().reset_index(drop=True)

    report = {"settings": asdict(settings), "delete": delete, "groups": report_groups,
              "links": int(len(o)), "detected": int(o["detected"].sum()),
              "repaired": int((decisions["status"] == "repaired").sum()),
              "flagged": int((decisions["status"] == "flagged").sum()),
              "removed": int((decisions["status"] == "removed").sum())}
    return out, report, decisions.rename(columns={"_item_id": "source", "_linked_item_id": "old_target",
                                                  "_link_type": "link_type", "tgt_type": "target_type"})
