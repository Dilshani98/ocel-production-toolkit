from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from reconstruction.identity import object_timelines, learn_lifecycles, IdentitySettings


@dataclass
class RelationSettings:
    pattern_ratio: float = 1.5        # usual type set must cover >= this x the events of the next set
    min_events: int = 30              # an activity needs this many events to learn its usual set
    dominant_share: float = 0.99      # R1: one object in at least this share of the activity's events of that type


def link_patterns(events, relations, types):
    """For every event: the set of object types it links (empty set if none)."""
    rel = relations[["_record_id", "_item_id"]].drop_duplicates()
    rel = rel.assign(_type=rel["_item_id"].map(types)).dropna(subset=["_type"])
    sets = rel.groupby("_record_id")["_type"].agg(frozenset)
    ev = events[["_record_id", "_activity"]].drop_duplicates("_record_id").set_index("_record_id")
    ev["types"] = [sets.get(e, frozenset()) for e in ev.index]
    return ev


def expected_types(patterns, settings):
    """Usual type set per activity, with the evidence for trusting it."""
    out = {}
    for activity, pats in patterns.groupby("_activity")["types"]:
        vc = pats.value_counts()
        top = int(vc.iloc[0])
        second = int(vc.iloc[1]) if len(vc) > 1 else 0
        ratio = top / second if second else float("inf")
        trusted = len(pats) >= settings.min_events and ratio >= settings.pattern_ratio and len(vc.index[0]) > 0
        out[activity] = {"usual": vc.index[0], "events": int(len(pats)), "top_share": top / len(pats),
                         "ratio_to_next": ratio, "trusted": bool(trusted)}
    return out


def find_missing(patterns, expected):
    rows = []
    for activity, info in expected.items():
        if not info["trusted"]:
            continue
        evs = patterns[patterns["_activity"] == activity]
        for e, present in zip(evs.index, evs["types"]):
            rows += [(e, activity, t) for t in sorted(info["usual"] - present)]
    return pd.DataFrame(rows, columns=["event", "activity", "type"])


def _usual_role(relations, activity_of, types):
    rel = relations.assign(_activity=relations["_record_id"].map(activity_of), _type=relations["_item_id"].map(types))
    return rel.groupby(["_activity", "_type"])["_role"].agg(lambda r: r.value_counts().index[0]).to_dict() \
        if "_role" in rel else {}


def dominant_objects(relations, activity_of, types, settings):
    """R1: per (activity, type), the object present in at least dominant_share of events that link the type."""
    rel = relations[["_record_id", "_item_id"]].drop_duplicates()
    rel = rel.assign(_activity=rel["_record_id"].map(activity_of), _type=rel["_item_id"].map(types))
    out = {}
    for (a, t), g in rel.groupby(["_activity", "_type"]):
        n_events = g["_record_id"].nunique()
        vc = g.groupby("_item_id")["_record_id"].nunique().sort_values(ascending=False, kind="stable")
        share = vc.iloc[0] / n_events
        out[(a, t)] = (vc.index[0], float(share)) if share >= settings.dominant_share else (None, float(share))
    return out


def fitting_orphans(missing, timelines, types, lifecycles, event_time):
    """All (event, orphan) pairs where the orphan fits the event's place in its lifecycle.
    Returns columns event, activity, type, orphan, distance."""
    acts = timelines.groupby("_item_id")["_activity"].agg(frozenset)
    times = timelines.pivot_table(index="_item_id", columns="_activity", values="_timestamp", aggfunc="min")
    out = []
    for (a, t), g in missing.groupby(["activity", "type"]):
        lc = lifecycles.get(t)
        if lc is None or a not in lc["usual"]:
            continue
        usual, order = lc["usual"], lc["order"]
        ids = [o for o in types.index[types == t] if a not in acts.get(o, frozenset())
               and (acts.get(o, frozenset()) | {a}) <= usual and len(acts.get(o, frozenset())) > 0]
        if not ids:
            continue
        i = order.index(a)
        prev = order[i - 1] if i > 0 else None
        nxt = order[i + 1] if i + 1 < len(order) else None
        orph = pd.DataFrame({"orphan": ids})
        orph["t_prev"] = times.reindex(ids)[prev].values if prev in times else pd.NaT
        orph["t_next"] = times.reindex(ids)[nxt].values if nxt in times else pd.NaT
        ev = pd.DataFrame({"event": g["event"].values, "t_event": event_time.reindex(g["event"]).values})
        pairs = ev.merge(orph, how="cross")
        fit = pd.Series(True, index=pairs.index)
        evidence = pd.Series(False, index=pairs.index)
        distance = pd.Series(0.0, index=pairs.index)
        for col, key, sign in (("t_prev", (prev, a), 1), ("t_next", (a, nxt), -1)):
            if key[0] is None or key[1] is None or key not in lc["gaps"]:
                continue
            arr = lc["gaps"][key]
            gap = ((pairs["t_event"] - pairs[col]) if sign == 1 else (pairs[col] - pairs["t_event"])).dt.total_seconds()
            known = gap.notna()
            fit &= ~known | ((gap >= arr[0]) & (gap <= arr[-1]))
            evidence |= known
            spread = max(np.quantile(arr, 0.99) - np.quantile(arr, 0.01), 1.0)
            distance += ((gap - np.median(arr)).abs() / spread).fillna(0)
        keep = fit & evidence                     # an orphan with no timing evidence never fits
        out.append(pairs.loc[keep, ["event", "orphan"]].assign(activity=a, type=t, distance=distance[keep].values))
    cols = ["event", "orphan", "activity", "type", "distance"]
    return pd.concat(out, ignore_index=True)[cols] if out else pd.DataFrame(columns=cols)


def recover_missing_links(tables, settings=None, eager=False):
    """Returns (tables with recovered links, report, links table).
    eager=True is the comparison baseline B4: after R1, every remaining missing link takes its nearest-in-time
    fitting orphan, one-to-one, with no uniqueness rule."""
    settings = settings or RelationSettings()
    out = {k: v.copy() for k, v in tables.items()}
    types = tables["objects"].drop_duplicates("_item_id").set_index("_item_id")["_item_type"]
    activity_of = tables["events"].drop_duplicates("_record_id").set_index("_record_id")["_activity"]
    event_time = pd.to_datetime(tables["events"].drop_duplicates("_record_id").set_index("_record_id")["_timestamp"],
                                utc=True, format="mixed")
    patterns = link_patterns(tables["events"], tables["relations"], types)
    expected = expected_types(patterns, settings)
    missing = find_missing(patterns, expected)
    roles = _usual_role(tables["relations"], activity_of, types)
    report = {"settings": asdict(settings), "eager": eager,
              "activities": {a: {k: (sorted(v) if k == "usual" else v) for k, v in info.items()}
                             for a, info in expected.items()},
              "missing_links": int(len(missing))}
    links = missing.assign(rule="none", object=None, n_candidates=0)
    if missing.empty:
        report.update({"added_R1": 0, "added_R2": 0, "added_eager": 0, "possible": 0})
        return out, report, links

    # R1: dominant object
    dominant = dominant_objects(tables["relations"], activity_of, types, settings)
    r1 = [dominant.get((a, t), (None, 0))[0] for a, t in zip(links["activity"], links["type"])]
    links["object"] = r1
    links.loc[links["object"].notna(), "rule"] = "R1"
    links["dominant_share"] = [dominant.get((a, t), (None, 0.0))[1] for a, t in zip(links["activity"], links["type"])]

    # R2: doubly unique orphan (only for links R1 did not fill)
    timelines = object_timelines(tables["events"], tables["relations"])
    lifecycles, _, _ = learn_lifecycles(timelines, types, IdentitySettings())
    open_links = links[links["rule"] == "none"]
    fits = fitting_orphans(open_links, timelines, types, lifecycles, event_time)
    n_per_event = fits.groupby(["event", "type"]).size()
    links["n_candidates"] = [int(n_per_event.get((e, t), 0)) for e, t in zip(links["event"], links["type"])]
    open_index = {(e, t): i for i, e, t, r in zip(links.index, links["event"], links["type"], links["rule"]) if r == "none"}
    if eager:
        used, filled = set(), {}
        ranked = fits.sort_values(["distance", "event", "orphan"])
        for e, t, o in zip(ranked["event"], ranked["type"], ranked["orphan"]):
            i = open_index.get((e, t))
            if i is not None and i not in filled and o not in used:
                filled[i] = o
                used.add(o)
        for i, o in filled.items():
            links.at[i, "object"], links.at[i, "rule"] = o, "eager"
    elif len(fits):
        per_event = fits.groupby(["event", "type"])["orphan"].transform("size")
        per_orphan = fits.groupby("orphan")["event"].transform("size")
        unique = fits[(per_event == 1) & (per_orphan == 1)]
        for e, t, o in zip(unique["event"], unique["type"], unique["orphan"]):
            i = open_index.get((e, t))
            if i is not None:
                links.at[i, "object"], links.at[i, "rule"] = o, "R2"

    added = links[links["rule"] != "none"]
    new_rows = pd.DataFrame({"_record_id": added["event"].values, "_item_id": added["object"].values,
                             "_item_type": added["type"].values,
                             "_role": [roles.get((a, t)) for a, t in zip(added["activity"], added["type"])]})
    rel_cols = list(tables["relations"].columns)
    out["relations"] = pd.concat([tables["relations"], new_rows[[c for c in rel_cols if c in new_rows]]],
                                 ignore_index=True).drop_duplicates().reset_index(drop=True)
    links.loc[links["rule"] == "none", "rule"] = "possible"
    links.loc[(links["rule"] == "possible") & (links["n_candidates"] == 0), "rule"] = "no candidate"
    report.update({"added_R1": int((links["rule"] == "R1").sum()), "added_R2": int((links["rule"] == "R2").sum()),
                   "added_eager": int((links["rule"] == "eager").sum()),
                   "possible": int((links["rule"] == "possible").sum()),
                   "no_candidate": int((links["rule"] == "no candidate").sum())})
    return out, report, links
