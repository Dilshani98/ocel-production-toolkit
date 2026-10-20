"""Scores a reconstructed log against the clean log. This is the ONLY code that reads ground truth.

A reconstructed log ("recon") is a dict of DataFrames in the internal column names of
reconstruction/mapping.py: events (_record_id, _activity, _timestamp), objects (_item_id, _item_type),
relations (_record_id, _item_id, _item_type, _role), o2o (_item_id, _linked_item_id, _link_type),
and optionally clusters (_item_id, _cluster_id): which messy object IDs were merged, and the ID
the output uses for them. Output tables use cluster IDs for objects.
"""
import json
from dataclasses import dataclass, field

import pandas as pd

INTERNAL = {
    "events": {"ocel:eid": "_record_id", "ocel:activity": "_activity", "ocel:timestamp": "_timestamp"},
    "objects": {"ocel:oid": "_item_id", "ocel:type": "_item_type"},
    "relations": {"ocel:eid": "_record_id", "ocel:oid": "_item_id", "ocel:type": "_item_type", "ocel:qualifier": "_role"},
    "o2o": {"ocel:oid": "_item_id", "ocel:oid_2": "_linked_item_id", "ocel:qualifier": "_link_type"},
}


# ---------------------------------------------------------------- loading ground truth

def load_clean_ocel(path):
    """Clean OCEL 2.0 log as four tables with internal column names (original clean IDs)."""
    import pm4py
    ocel = pm4py.read_ocel2_xml(path)
    return {kind: getattr(ocel, kind)[list(cols)].rename(columns=cols).reset_index(drop=True)
            for kind, cols in INTERNAL.items()}


def load_ground_truth(path):
    with open(path) as f:
        return json.load(f)


@dataclass
class Truth:
    events: pd.DataFrame          # clean events, messy IDs, in clean file order
    objects: pd.DataFrame         # clean objects, messy IDs
    e2o: set                      # (event, object, qualifier)
    o2o: set                      # (object, object, qualifier)
    true_id: dict                 # every messy object ID -> the messy ID of the real object it is
    clone_pairs: set              # frozenset({original, clone})
    drifted: set = field(default_factory=set)
    distorted: set = field(default_factory=set)
    damaged_e2o: set = field(default_factory=set)   # clean E2O triples the injector damaged
    damaged_o2o: set = field(default_factory=set)   # clean O2O triples the injector damaged


def build_truth(clean, gt=None):
    """Translates the clean log to messy IDs with the ids_renamed record, and collects what the
    injector changed. gt=None means no injection (clean-baseline run): IDs are used as they are."""
    gt = gt or []
    renames = [g for g in gt if g["change_type"] == "ids_renamed"]
    if len(renames) > 1:
        raise ValueError("more than one ids_renamed record")
    if renames:
        ev_map, ob_map = renames[0]["details"]["events"], renames[0]["details"]["objects"]
    else:
        ev_map = {e: e for e in clean["events"]["_record_id"]}
        ob_map = {o: o for o in clean["objects"]["_item_id"]}
    for name, ids, mapping in (("event", clean["events"]["_record_id"], ev_map),
                               ("object", clean["objects"]["_item_id"], ob_map)):
        missing = set(ids) - set(mapping)
        if missing:
            raise ValueError(f"{len(missing)} clean {name} IDs have no rename, e.g. {sorted(missing)[:3]}")
        if len(set(mapping.values())) != len(mapping):
            raise ValueError(f"{name} rename table is not one-to-one")

    events = clean["events"].assign(_record_id=clean["events"]["_record_id"].map(ev_map))
    events["_timestamp"] = pd.to_datetime(events["_timestamp"], utc=True, format="mixed")
    objects = clean["objects"].assign(_item_id=clean["objects"]["_item_id"].map(ob_map))
    rel, o2o = clean["relations"], clean["o2o"]
    e2o = set(zip(rel["_record_id"].map(ev_map), rel["_item_id"].map(ob_map), rel["_role"]))
    o2o_set = set(zip(o2o["_item_id"].map(ob_map), o2o["_linked_item_id"].map(ob_map), o2o["_link_type"]))

    true_id = {o: o for o in objects["_item_id"]}
    clone_pairs = set()
    for g in gt:
        if g["change_type"] == "clone_created":
            true_id[g["details"]["clone_id"]] = g["target_id"]
            clone_pairs.add(frozenset((g["target_id"], g["details"]["clone_id"])))
    real = lambda oid: true_id.get(oid, oid)

    # Damaged items, as clean triples. Missing-E2O records hold no qualifier, so match on (event, object).
    damaged_pairs = {(g["details"]["event_id"], real(g["target_id"])) for g in gt
                     if g["change_type"] in ("relation_removed", "relation_reassigned")}
    damaged_e2o = {t for t in e2o if (t[0], t[1]) in damaged_pairs}
    damaged_o2o = set()
    for g in gt:
        d = g["details"]
        if g["change_type"] == "target_swapped":
            damaged_o2o.add((real(g["target_id"]), real(d["original_target"]), d["qualifier"]))
        elif g["change_type"] == "o2o_reassigned":
            pair = (g["target_id"], d["other_id"]) if d["clone_side"] == "source" else (d["other_id"], g["target_id"])
            damaged_o2o.add((real(pair[0]), real(pair[1]), d["qualifier"]))
    damaged_o2o &= o2o_set

    return Truth(events=events, objects=objects, e2o=e2o, o2o=o2o_set, true_id=true_id,
                 clone_pairs=clone_pairs,
                 drifted={g["target_id"] for g in gt if g["change_type"] == "timestamp_shifted"},
                 distorted={g["target_id"] for g in gt if g["change_type"] == "activity_relabelled"},
                 damaged_e2o=damaged_e2o, damaged_o2o=damaged_o2o)


# ---------------------------------------------------------------- helpers

def prf(predicted, truth):
    """Precision, recall, F1 over two sets. Empty prediction = 0.0; both empty = 1.0."""
    predicted, truth = set(predicted), set(truth)
    if not predicted and not truth:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "n_predicted": 0, "n_true": 0, "n_correct": 0}
    hit = len(predicted & truth)
    p = hit / len(predicted) if predicted else 0.0
    r = hit / len(truth) if truth else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": p, "recall": r, "f1": f1,
            "n_predicted": len(predicted), "n_true": len(truth), "n_correct": hit}


def resolve_objects(output_ids, clusters, true_id):
    """Maps each output object ID to the real object it stands for, or None.
    Strict rule: an output ID stands for real object X only if its cluster contains X's own ID and
    every member is X (or a clone of X). The output ID's text never matters."""
    members = {}
    if clusters is not None and len(clusters):
        for oid, cid in zip(clusters["_item_id"], clusters["_cluster_id"]):
            members.setdefault(cid, set()).add(oid)
    resolved = {}
    for out_id in set(output_ids):
        group = members.get(out_id, {out_id})
        reals = {true_id.get(m) for m in group}
        x = next(iter(reals)) if len(reals) == 1 else None
        resolved[out_id] = x if x is not None and x in group else None
    return resolved


def _as_triples(a, b, c, resolve_a=None, resolve_b=None):
    # Unresolved objects become ("?", id): they count as predictions but can never match truth.
    fix = lambda r, v: v if r is None else (r[v] if r[v] is not None else ("?", v))
    return set(zip([fix(resolve_a, v) for v in a], [fix(resolve_b, v) for v in b], c))


def _timestamps(series):
    return pd.to_datetime(series, utc=True, format="mixed", errors="coerce")


# ---------------------------------------------------------------- metric areas

def score_events(recon, truth):
    out, clean = set(recon["events"]["_record_id"]), set(truth.events["_record_id"])
    return {"missing_events": len(clean - out), "extra_events": len(out - clean)}


def score_labels(recon, messy, truth):
    clean = truth.events.set_index("_record_id")["_activity"]
    out = recon["events"].drop_duplicates("_record_id").set_index("_record_id")["_activity"].reindex(clean.index)
    before = messy["events"].set_index("_record_id")["_activity"].reindex(clean.index)
    distorted = clean.index.isin(list(truth.distorted))
    was_valid = before == clean
    return {"accuracy": float((out == clean).mean()),
            "distorted_restored": float((out[distorted] == clean[distorted]).mean()) if distorted.any() else 1.0,
            "valid_wrongly_changed": int((was_valid & out.notna() & (out != before)).sum())}


def score_timestamps(recon, messy, truth):
    clean = truth.events.set_index("_record_id")["_timestamp"]
    out = _timestamps(recon["events"].drop_duplicates("_record_id").set_index("_record_id")["_timestamp"]).reindex(clean.index)
    before = _timestamps(messy["events"].set_index("_record_id")["_timestamp"]).reindex(clean.index)
    drifted = clean.index.isin(list(truth.drifted))
    error = (out[drifted] - clean[drifted]).dt.total_seconds().abs()
    backward = lambda s: int((_timestamps(s).diff().dt.total_seconds() < 0).sum())
    return {"drifted_restored_exactly": float((error == 0).mean()) if drifted.any() else 1.0,
            "drifted_mean_abs_error_s": float(error.mean()) if drifted.any() else 0.0,
            "untouched_changed": int((~drifted & out.notna() & (out != before)).sum()),
            "backward_steps_messy": backward(messy["events"]["_timestamp"]),
            "backward_steps_output": backward(recon["events"]["_timestamp"])}


def score_identity(recon, truth):
    """Pairwise identity scores. Pairs are counted, not listed (a cluster of n gives n(n-1)/2 pairs),
    so very large clusters (e.g. a naive baseline merging thousands of objects) stay cheap."""
    clusters = recon.get("clusters")
    n_predicted = correct = impure = 0
    if clusters is not None and len(clusters):
        c = clusters.drop_duplicates("_item_id")
        sizes = c.groupby("_cluster_id").size()
        n_predicted = int((sizes * (sizes - 1) // 2).sum())
        cluster_of = dict(zip(c["_item_id"], c["_cluster_id"]))
        correct = sum(1 for pair in truth.clone_pairs
                      if len({cluster_of.get(i, ("none", i)) for i in pair}) == 1)
        real = c["_item_id"].map(lambda i: truth.true_id.get(i, "?" + str(i)))
        impure = int((real.groupby(c["_cluster_id"]).nunique() > 1).sum())
    n_true = len(truth.clone_pairs)
    if n_predicted == 0 and n_true == 0:
        p = r = f1 = 1.0
    else:
        p = correct / n_predicted if n_predicted else 0.0
        r = correct / n_true if n_true else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": p, "recall": r, "f1": f1, "n_predicted": n_predicted, "n_true": n_true,
            "n_correct": correct, "false_merges": n_predicted - correct,
            "missed_merges": n_true - correct, "impure_clusters": impure}


def _with_affected(result, predicted, damaged):
    result["affected_recall"] = len(predicted & damaged) / len(damaged) if damaged else 1.0
    result["n_affected"] = len(damaged)
    return result


def score_e2o(recon, truth, resolved):
    rel = recon["relations"]
    predicted = _as_triples(rel["_record_id"], rel["_item_id"], rel["_role"], resolve_b=resolved)
    return _with_affected(prf(predicted, truth.e2o), predicted, truth.damaged_e2o)


def score_o2o(recon, truth, resolved):
    o2o = recon["o2o"]
    predicted = _as_triples(o2o["_item_id"], o2o["_linked_item_id"], o2o["_link_type"], resolved, resolved)
    return _with_affected(prf(predicted, truth.o2o), predicted, truth.damaged_o2o)


def score_validity(recon):
    ev, ob, rel, o2o = recon["events"], recon["objects"], recon["relations"], recon["o2o"]
    events, objects = set(ev["_record_id"]), set(ob["_item_id"])
    obj_type = ob.drop_duplicates("_item_id").set_index("_item_id")["_item_type"]
    rel_type = rel["_item_id"].map(obj_type)
    return {"duplicate_event_ids": int(ev["_record_id"].duplicated().sum()),
            "duplicate_object_ids": int(ob["_item_id"].duplicated().sum()),
            "duplicate_relation_rows": int(rel.duplicated(["_record_id", "_item_id", "_role"]).sum()),
            "duplicate_o2o_rows": int(o2o.duplicated(["_item_id", "_linked_item_id", "_link_type"]).sum()),
            "relations_unknown_event": int((~rel["_record_id"].isin(events)).sum()),
            "relations_unknown_object": int((~rel["_item_id"].isin(objects)).sum()),
            "o2o_unknown_object": int((~o2o["_item_id"].isin(objects) | ~o2o["_linked_item_id"].isin(objects)).sum()),
            "objects_with_several_types": int((ob.groupby("_item_id")["_item_type"].nunique() > 1).sum()),
            "relation_type_mismatch": int((rel_type.notna() & (rel_type != rel["_item_type"])).sum())
                                      if "_item_type" in rel else 0,
            "unparsable_timestamps": int(_timestamps(ev["_timestamp"]).isna().sum())}


def dfg_edges(events, objects, relations):
    """Object-centric directly-follows edges: for each object, its events in time order (ties broken
    by the event's row in the events table); counts of (object type, activity, next activity)."""
    ev = events[["_record_id", "_activity", "_timestamp"]].drop_duplicates("_record_id").copy()
    ev["_row"] = range(len(ev))
    ev["_timestamp"] = _timestamps(ev["_timestamp"])
    types = objects.drop_duplicates("_item_id").set_index("_item_id")["_item_type"]
    rel = relations[["_record_id", "_item_id"]].drop_duplicates().merge(ev, on="_record_id")
    rel["_type"] = rel["_item_id"].map(types)
    rel = rel.dropna(subset=["_type"]).sort_values(["_item_id", "_timestamp", "_row"], kind="stable")
    rel["_next"] = rel.groupby("_item_id")["_activity"].shift(-1)
    edges = rel.dropna(subset=["_next"])
    return edges.groupby(["_type", "_activity", "_next"]).size().to_dict()


def score_usefulness(recon, truth, clean):
    out = dfg_edges(recon["events"], recon["objects"], recon["relations"])
    rel = clean["relations"]
    ref = dfg_edges(clean["events"], clean["objects"], rel)   # clean IDs: only activities and types matter
    edges = prf(set(out), set(ref))
    keys = set(out) | set(ref)
    freq_diff = sum(abs(out.get(k, 0) - ref.get(k, 0)) for k in keys) / sum(ref.values()) if ref else 0.0
    counts_out = recon["objects"].drop_duplicates("_item_id")["_item_type"].value_counts()
    counts_ref = truth.objects["_item_type"].value_counts()
    diff = counts_out.reindex(counts_ref.index.union(counts_out.index), fill_value=0) - \
           counts_ref.reindex(counts_ref.index.union(counts_out.index), fill_value=0)
    result = {"edge_precision": edges["precision"], "edge_recall": edges["recall"], "edge_f1": edges["f1"],
              "edge_frequency_difference": freq_diff, "object_count_abs_difference": int(diff.abs().sum())}
    result.update({f"object_count_difference[{t}]": int(v) for t, v in diff.items()})
    return result


# ---------------------------------------------------------------- everything together

def score(recon, messy, truth, clean, system="toolkit", severity=None):
    """All metric areas as one long table: system, severity, area, metric, value."""
    output_ids = list(recon["relations"]["_item_id"]) + list(recon["o2o"]["_item_id"]) + \
                 list(recon["o2o"]["_linked_item_id"]) + list(recon["objects"]["_item_id"])
    resolved = resolve_objects(output_ids, recon.get("clusters"), truth.true_id)
    areas = {"events": score_events(recon, truth),
             "labels": score_labels(recon, messy, truth),
             "timestamps": score_timestamps(recon, messy, truth),
             "identity": score_identity(recon, truth),
             "e2o": score_e2o(recon, truth, resolved),
             "o2o": score_o2o(recon, truth, resolved),
             "validity": score_validity(recon),
             "usefulness": score_usefulness(recon, truth, clean)}
    rows = [{"system": system, "severity": severity, "area": area, "metric": m, "value": v}
            for area, metrics in areas.items() for m, v in metrics.items()]
    return pd.DataFrame(rows)
