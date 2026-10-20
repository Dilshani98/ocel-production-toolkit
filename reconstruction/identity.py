"""Object identity resolution (stage 8): finds objects recorded under two IDs and merges them.

Uses only the (cleaned) messy tables. No type names, activity names or ID text are used.
1. Learn each object type's usual lifecycle from its complete objects: activity set, order, gap ranges.
2. Fragments = objects whose activity set is a strict subset of their type's usual set.
3. Blocking (hard rules): same type, disjoint activity sets whose union is the usual set, merged timeline
   in the usual order, every gap inside the range seen in complete objects (widened by gap_margin).
4. Comparison vector per candidate pair: time fit, shared specific neighbour, agreement of each varying
   attribute. Each feature: a level, or "unknown" (no evidence, weight 0).
5. Fellegi-Sunter: m and u probabilities and the match share estimated by EM over the candidate pairs
   (no labels); u is initialised from random complementary pairs. Weight = sum of log2(m/u).
6. Decision: posterior >= match_threshold -> match; < nonmatch_threshold -> non-match; between -> possible
   (not merged). A match is merged only if the pair is each side's best candidate with a margin of at least
   margin_bits over the next one (ambiguity rule), and each fragment merges at most once.
"""
import math
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

UNKNOWN = "unknown"
TIME_LEVELS = ["typical", "plausible", "unusual"]
AGREE_LEVELS = ["agree", "disagree"]


@dataclass
class IdentitySettings:
    min_complete: int = 30            # a type needs this many complete objects to learn its lifecycle
    gap_margin: float = 0.05          # widen observed gap ranges by this share of the range
    match_threshold: float = 0.9
    nonmatch_threshold: float = 0.5
    margin_bits: float = 1.0
    min_pairs_for_em: int = 10
    n_random_pairs: int = 20000
    em_max_iter: int = 500
    em_tol: float = 1e-9
    smoothing: float = 0.5
    seed: int = 0


# ---------------------------------------------------------------- lifecycles and fragments

def object_timelines(events, relations):
    ev = events[["_record_id", "_activity", "_timestamp"]].drop_duplicates("_record_id").copy()
    ev["_timestamp"] = pd.to_datetime(ev["_timestamp"], utc=True, format="mixed")
    return relations[["_record_id", "_item_id"]].drop_duplicates().merge(ev, on="_record_id")


def learn_lifecycles(timelines, types, settings):
    acts = timelines.groupby("_item_id")["_activity"].agg(frozenset)
    obj = pd.DataFrame({"type": types.reindex(acts.index), "acts": acts}).dropna(subset=["type"])
    times = timelines.pivot_table(index="_item_id", columns="_activity", values="_timestamp", aggfunc="min")
    lifecycles = {}
    for typ, grp in obj.groupby("type"):
        usual = grp["acts"].value_counts().index[0]
        complete = grp.index[grp["acts"] == usual]
        if len(usual) < 2 or len(complete) < settings.min_complete:
            continue
        t = times.loc[complete, sorted(usual)]
        orders = t.apply(lambda r: tuple(r.sort_values(kind="stable").index), axis=1).value_counts()
        order = list(orders.index[0])
        gaps = {(x, y): np.sort((t[y] - t[x]).dt.total_seconds().values) for x, y in zip(order, order[1:])}
        lifecycles[typ] = {"usual": usual, "order": order, "gaps": gaps, "n_complete": int(len(complete)),
                           "order_share": float(orders.iloc[0] / len(complete))}
    is_frag = [t in lifecycles and a < lifecycles[t]["usual"] for t, a in zip(obj["type"], obj["acts"])]
    return lifecycles, obj[is_frag], times


def _time_measures(merged, lc, settings):
    """For merged timelines (one column per activity): order/range check, extremeness, distance."""
    ok = pd.Series(True, index=merged.index)
    extreme = pd.Series(0.0, index=merged.index)
    distance = pd.Series(0.0, index=merged.index)
    for (x, y), arr in lc["gaps"].items():
        g = (merged[y] - merged[x]).dt.total_seconds()
        span = arr[-1] - arr[0]
        lo, hi = arr[0] - settings.gap_margin * span, arr[-1] + settings.gap_margin * span
        ok &= (g >= 0) & (g >= lo) & (g <= hi)
        q = np.searchsorted(arr, g.values, side="right") / len(arr)
        extreme = np.maximum(extreme, np.abs(q - 0.5) * 2)
        spread = max(np.quantile(arr, 0.99) - np.quantile(arr, 0.01), 1.0)
        distance += (g - np.median(arr)).abs() / spread
    level = np.where(extreme <= 0.5, "typical", np.where(extreme <= 0.9, "plausible", "unusual"))
    return ok, pd.Series(level, index=merged.index), distance


def complementary_pairs(fragments, times, lifecycles):
    """All same-type fragment pairs with disjoint activity sets whose union is the usual set."""
    out = []
    for typ, lc in lifecycles.items():
        f = fragments[fragments["type"] == typ]
        if f.empty:
            continue
        groups = f.groupby(f["acts"].map(lambda s: tuple(sorted(s)))).groups
        for key, ids in groups.items():
            other = tuple(sorted(lc["usual"] - frozenset(key)))
            if other not in groups or key > other:
                continue
            A = times.loc[list(ids), list(key)].add_prefix("a|").reset_index().rename(columns={"_item_id": "a"})
            B = times.loc[list(groups[other]), list(other)].add_prefix("b|").reset_index().rename(columns={"_item_id": "b"})
            pairs = A.merge(B, how="cross")
            merged = pd.DataFrame({act: pairs[f"a|{act}"] if act in key else pairs[f"b|{act}"] for act in lc["order"]})
            pairs = pairs[["a", "b"]].assign(type=typ)
            out.append((pairs, merged))
    return out


# ---------------------------------------------------------------- comparison features

def specific_neighbours(relations, o2o):
    """Neighbours via shared events (E2O) and O2O links. A neighbour is 'specific' if its degree (number of
    distinct objects it neighbours) is below the largest jump in log-degree; above it are hubs."""
    rel = relations[["_record_id", "_item_id"]].drop_duplicates()
    e = rel.merge(rel, on="_record_id", suffixes=("", "_nb"))
    e = e[e["_item_id"] != e["_item_id_nb"]][["_item_id", "_item_id_nb"]]
    o = pd.concat([o2o[["_item_id", "_linked_item_id"]].set_axis(["_item_id", "_item_id_nb"], axis=1),
                   o2o[["_linked_item_id", "_item_id"]].set_axis(["_item_id", "_item_id_nb"], axis=1)])
    nb = pd.concat([e, o]).drop_duplicates()
    if nb.empty:
        return {}, 0
    degree = nb.groupby("_item_id_nb")["_item_id"].nunique()
    distinct = np.sort(degree.unique())
    cutoff = int(distinct[np.argmax(np.diff(np.log(distinct)))]) if len(distinct) > 1 else int(distinct[0])
    spec = nb[nb["_item_id_nb"].map(degree) <= cutoff]
    return spec.groupby("_item_id")["_item_id_nb"].agg(set).to_dict(), cutoff


def _decimals(value):
    text = str(value)
    return len(text.split(".")[1].rstrip()) if "." in text and "e" not in text.lower() else 0


def _attribute_level(x, y):
    if pd.isna(x) or pd.isna(y):
        return UNKNOWN
    try:
        fx, fy = float(x), float(y)
    except (TypeError, ValueError):
        return "agree" if str(x) == str(y) else "disagree"
    # Agree if one value could be a rounded version of the other (half a unit of the coarser precision)
    tolerance = 0.5 * 10 ** -min(_decimals(x), _decimals(y))
    return "agree" if abs(fx - fy) <= tolerance * (1 + 1e-9) else "disagree"


def compare(pairs, time_level, neighbours, attributes):
    """Comparison vector (one column per feature) for candidate pairs."""
    gamma = pd.DataFrame({"time": time_level.values}, index=pairs.index)
    na = pairs["a"].map(neighbours)
    nbb = pairs["b"].map(neighbours)
    gamma["neighbour"] = [UNKNOWN if not isinstance(x, set) or not isinstance(y, set) else
                          ("agree" if x & y else "disagree") for x, y in zip(na, nbb)]
    for col in attributes.columns:
        va, vb = pairs["a"].map(attributes[col]), pairs["b"].map(attributes[col])
        gamma[f"attr:{col}"] = [_attribute_level(x, y) for x, y in zip(va, vb)]
    return gamma


# ---------------------------------------------------------------- Fellegi-Sunter with EM

def _levels(feature):
    return TIME_LEVELS if feature == "time" else AGREE_LEVELS


def _initial_m(feature):
    return np.array([0.6, 0.3, 0.1]) if feature == "time" else np.array([0.9, 0.1])


def _distribution(values, levels, alpha):
    counts = np.array([(values == lv).sum() for lv in levels], dtype=float) + alpha
    return counts / counts.sum()


def fit_fellegi_sunter(gamma, gamma_random, settings):
    """EM over candidate pairs (features independent within each class; unknown values skipped).
    Returns per-pair weights (bits) and posteriors, and the m/u table."""
    feats = list(gamma.columns)
    codes = {f: np.array([_levels(f).index(v) if v != UNKNOWN else -1 for v in gamma[f]]) for f in feats}
    m = {f: _initial_m(f) for f in feats}
    u = {f: _distribution(gamma_random[f].values, _levels(f), settings.smoothing)
         if f in gamma_random else np.full(len(_levels(f)), 1 / len(_levels(f))) for f in feats}
    pi = 0.5
    n = len(gamma)
    for _ in range(settings.em_max_iter):
        lm, lu = np.zeros(n), np.zeros(n)
        for f in feats:
            k = codes[f] >= 0
            lm[k] += np.log(m[f][codes[f][k]])
            lu[k] += np.log(u[f][codes[f][k]])
        g = 1 / (1 + np.exp(np.clip(np.log(1 - pi) + lu - np.log(pi) - lm, -700, 700)))
        new_pi = float(np.clip(g.mean(), 1e-6, 1 - 1e-6))
        change = abs(new_pi - pi)
        for f in feats:
            k = codes[f] >= 0
            L = len(_levels(f))
            nm = (np.bincount(codes[f][k], weights=g[k], minlength=L) + settings.smoothing)
            nu = (np.bincount(codes[f][k], weights=1 - g[k], minlength=L) + settings.smoothing)
            nm, nu = nm / nm.sum(), nu / nu.sum()
            change = max(change, np.abs(nm - m[f]).max(), np.abs(nu - u[f]).max())
            m[f], u[f] = nm, nu
        pi = new_pi
        if change < settings.em_tol:
            break
    # Orientation: the match class is the one where the best level of each feature is more likely
    if sum(m[f][0] - u[f][0] for f in feats) < 0:
        m, u, pi = u, m, 1 - pi
    lm, lu = np.zeros(n), np.zeros(n)
    for f in feats:
        k = codes[f] >= 0
        lm[k] += np.log(m[f][codes[f][k]])
        lu[k] += np.log(u[f][codes[f][k]])
    weight = (lm - lu) / math.log(2)
    posterior = 1 / (1 + np.exp(np.clip(np.log(1 - pi) + lu - np.log(pi) - lm, -700, 700)))
    table = pd.DataFrame([{"feature": f, "level": lv, "m": m[f][i], "u": u[f][i],
                           "weight_bits": math.log2(m[f][i] / u[f][i])}
                          for f in feats for i, lv in enumerate(_levels(f))])
    return weight, posterior, table, pi


# ---------------------------------------------------------------- decisions

def decide_fellegi_sunter(pairs, settings):
    """Status per pair: non_match, possible, ambiguous, conflict or merged."""
    p = pairs.copy()
    p["status"] = np.where(p["posterior"] >= settings.match_threshold, "match",
                           np.where(p["posterior"] >= settings.nonmatch_threshold, "possible", "non_match"))
    competitors = p[p["posterior"] >= settings.nonmatch_threshold]
    long = pd.concat([competitors[["a", "weight"]].rename(columns={"a": "x"}),
                      competitors[["b", "weight"]].rename(columns={"b": "x"})]).reset_index()
    long = long.sort_values(["x", "weight", "index"], ascending=[True, False, True])
    best = long.groupby("x").head(1).set_index("x")["index"]
    second = long.groupby("x")["weight"].apply(lambda w: w.iloc[1] if len(w) > 1 else -np.inf)
    for idx in p.index[p["status"] == "match"]:
        a, b, w = p.at[idx, "a"], p.at[idx, "b"], p.at[idx, "weight"]
        mutual = best.get(a) == idx and best.get(b) == idx
        clear = w - second.get(a, -np.inf) >= settings.margin_bits and w - second.get(b, -np.inf) >= settings.margin_bits
        p.at[idx, "status"] = "accepted" if mutual and clear else "ambiguous"
    return _one_to_one(p, p["status"] == "accepted", order=p["weight"], descending=True)


def decide_closest(pairs):
    """Baseline B3: every fragment takes its closest-in-time candidate, one-to-one, no thresholds."""
    p = pairs.copy()
    p["status"] = "candidate"
    return _one_to_one(p, pd.Series(True, index=p.index), order=p["time_distance"], descending=False)


def _one_to_one(p, eligible, order, descending):
    used = set()
    ranked = p[eligible].assign(_o=order[eligible]).sort_values(["_o", "a", "b"], ascending=[not descending, True, True])
    for idx, a, b in zip(ranked.index, ranked["a"], ranked["b"]):
        if a in used or b in used:
            p.at[idx, "status"] = "conflict"
        else:
            p.at[idx, "status"] = "merged"
            used.update((a, b))
    p.loc[eligible & (p["status"] == "candidate"), "status"] = "conflict"
    return p


# ---------------------------------------------------------------- applying merges

def apply_merges(tables, merged_pairs, first_seen):
    """Rewrite tables so each merged pair becomes one object. Canonical ID = fragment seen first.
    Blank attributes of the kept row are filled from the partner (the kept row wins on conflicts)."""
    out = {k: v.copy() for k, v in tables.items() if k in ("events", "objects", "relations", "o2o")}
    canonical = {}
    for a, b in zip(merged_pairs["a"], merged_pairs["b"]):
        keep, drop = (a, b) if first_seen.get(a) <= first_seen.get(b) else (b, a)
        canonical[keep], canonical[drop] = keep, keep
    if canonical:
        obj = out["objects"].set_index("_item_id")
        drops = [k for k, v in canonical.items() if k != v]
        keeps = [canonical[d] for d in drops]
        filled = obj.loc[keeps].combine_first(obj.loc[drops].set_axis(keeps))
        obj.loc[keeps] = filled[obj.columns].values
        out["objects"] = obj.drop(index=drops).reset_index()
        rename = lambda s: s.map(lambda v: canonical.get(v, v))
        out["relations"]["_item_id"] = rename(out["relations"]["_item_id"])
        out["o2o"]["_item_id"] = rename(out["o2o"]["_item_id"])
        out["o2o"]["_linked_item_id"] = rename(out["o2o"]["_linked_item_id"])
        out["relations"] = out["relations"].drop_duplicates().reset_index(drop=True)
        out["o2o"] = out["o2o"].drop_duplicates().reset_index(drop=True)
    out["clusters"] = pd.DataFrame({"_item_id": list(canonical), "_cluster_id": list(canonical.values())})
    return out


# ---------------------------------------------------------------- everything together

def resolve_identities(tables, settings=None, decision="fellegi_sunter"):
    """Returns (output tables with a clusters table, report dict, candidate pair table)."""
    settings = settings or IdentitySettings()
    types = tables["objects"].drop_duplicates("_item_id").set_index("_item_id")["_item_type"]
    timelines = object_timelines(tables["events"], tables["relations"])
    lifecycles, fragments, times = learn_lifecycles(timelines, types, settings)
    neighbours, hub_cutoff = specific_neighbours(tables["relations"], tables["o2o"])
    first_seen = timelines.groupby("_item_id")["_timestamp"].min().to_dict()
    rng = np.random.default_rng(settings.seed)

    blocks, randoms, n_complementary = [], [], 0
    for pairs, merged in complementary_pairs(fragments, times, lifecycles):
        lc = lifecycles[pairs["type"].iloc[0]]
        ok, level, distance = _time_measures(merged, lc, settings)
        n_complementary += len(pairs)
        pairs = pairs.assign(time_level=level.values, time_distance=distance.values)
        take = rng.choice(len(pairs), size=min(len(pairs), settings.n_random_pairs), replace=False)
        randoms.append(pairs.iloc[np.sort(take)])
        blocks.append(pairs[ok.values])
    columns = ["a", "b", "type", "time_level", "time_distance"]
    cand = pd.concat(blocks, ignore_index=True) if blocks else pd.DataFrame(columns=columns)
    rand = pd.concat(randoms, ignore_index=True) if randoms else pd.DataFrame(columns=columns)

    report = {"settings": asdict(settings), "decision": decision, "hub_cutoff": hub_cutoff,
              "lifecycles": {t: {"usual": sorted(lc["usual"]), "order": lc["order"], "n_complete": lc["n_complete"],
                                 "order_share": lc["order_share"]} for t, lc in lifecycles.items()},
              "fragments": int(len(fragments)), "complementary_pairs": int(n_complementary),
              "candidate_pairs": int(len(cand)), "m_u_tables": {}, "match_share": {}}
    results = []
    for typ, c in cand.groupby("type"):
        objs = tables["objects"].drop_duplicates("_item_id").set_index("_item_id")
        frag_ids = fragments.index[fragments["type"] == typ]
        attr_cols = [col for col in objs.columns if col != "_item_type"
                     and objs.loc[objs.index.intersection(frag_ids), col].nunique() > 1]
        attributes = objs[attr_cols]
        c = c.copy()
        if decision == "closest":
            results.append(c)
            continue
        gamma = compare(c, c["time_level"], neighbours, attributes)
        r = rand[rand["type"] == typ]
        gamma_random = compare(r, r["time_level"], neighbours, attributes)
        if len(c) < settings.min_pairs_for_em:
            c["weight"], c["posterior"] = 0.0, settings.nonmatch_threshold     # too few pairs: possible only
        else:
            c["weight"], c["posterior"], table, pi = fit_fellegi_sunter(gamma, gamma_random, settings)
            report["m_u_tables"][typ] = table.to_dict("records")
            report["match_share"][typ] = pi
        c = pd.concat([c, gamma.add_prefix("γ_")], axis=1)
        results.append(c)
    cand = pd.concat(results, ignore_index=True) if results else cand.assign(status=[])
    if len(cand):
        cand = decide_closest(cand) if decision == "closest" else decide_fellegi_sunter(cand, settings)
    merged_pairs = cand[cand["status"] == "merged"] if len(cand) else cand
    out = apply_merges(tables, merged_pairs, first_seen)
    report["status_counts"] = cand["status"].value_counts().to_dict() if len(cand) else {}
    report["merged_pairs"] = int(len(merged_pairs))
    return out, report, cand
