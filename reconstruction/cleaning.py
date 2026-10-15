import difflib
import re
from functools import lru_cache
import pandas as pd


def _normalise(label):
    """Ignore case, spaces, underscores and dashes when comparing labels."""
    return re.sub(r"[\s_\-]+", "", str(label)).casefold()



@lru_cache(maxsize=None)
def _similarity(a, b):
    """Spelling similarity between two labels (0 to 1), cached for speed."""
    return difflib.SequenceMatcher(None, a, b).ratio()



def clean_activity_labels(events, rare_share=0.02, similarity=0.85, dominance=5, ambiguity_margin=0.03, return_ambiguous=False):

    events = events.copy()
    counts = events["_activity"].value_counts()
    total = len(events)

    resolved = {}                       # label -> final label it maps to
    log_rows, ambiguous_rows = [], []

    # Most frequent first, so every candidate is already resolved when we need it.
    for label, n in counts.items():
        if n / total >= rare_share:
            continue
        scored = []
        for other, other_n in counts.items():
            if other == label or other_n < dominance * n:
                continue
            scored.append((_similarity(_normalise(label), _normalise(other)), other))
        if not scored:
            continue
        scored.sort(reverse=True)
        best_score = scored[0][0]
        if best_score < similarity:
            continue

        close = [(sc, c) for sc, c in scored if best_score - sc < ambiguity_margin]
        finals = {resolved.get(c, c) for _, c in close}
        if len(finals) > 1:
            ambiguous_rows.append({"label": label, "n_events": int(n),
                                   "candidate_1": close[0][1], "score_1": round(close[0][0], 3),
                                   "candidate_2": close[1][1], "score_2": round(close[1][0], 3)})
            continue

        final = finals.pop()
        resolved[label] = final
        log_rows.append({"old_label": label, "new_label": final,
                         "n_events": int(n), "similarity": round(best_score, 3)})

    events["_activity"] = events["_activity"].replace(resolved)
    change_log = pd.DataFrame(log_rows, columns=["old_label", "new_label", "n_events", "similarity"])
    if return_ambiguous:
        ambiguous = pd.DataFrame(ambiguous_rows, columns=["label", "n_events", "candidate_1",
                                                           "score_1", "candidate_2", "score_2"])
        return events, change_log, ambiguous
    return events, change_log


def repair_timestamp_drift(events, min_share=0.9, min_suspects=20, percentile=95):
 
    events = events.copy().reset_index(drop=True)
    ts = pd.to_datetime(events["_timestamp"], utc=True, format="mixed")
    events["_timestamp"] = ts

    step = ts.diff().dt.total_seconds()                 # time difference to previous row
    backward_before = int((step < 0).sum())
    suspect_pos = [i - 1 for i in step.index[step < 0]]  # row BEFORE each backward step
    gaps = [-step.iloc[i + 1] for i in suspect_pos]

    report = {"backward_before": backward_before, "n_suspects": len(suspect_pos),
              "culprit_activity": None, "shift_seconds": 0, "n_corrected": 0,
              "backward_after": backward_before, "status": "no systematic drift found"}
    empty_log = pd.DataFrame(columns=["record_id", "old_timestamp", "new_timestamp", "shift_seconds"])

    if len(suspect_pos) < min_suspects:
        return events, report, empty_log

    acts = events["_activity"].iloc[suspect_pos]
    culprit, share = acts.value_counts().index[0], acts.value_counts(normalize=True).iloc[0]
    if share < min_share:
        return events, report, empty_log

    culprit_gaps = [g for p, g in zip(suspect_pos, gaps) if events["_activity"].iloc[p] == culprit]
    shift = int(round(float(pd.Series(culprit_gaps).quantile(percentile / 100))))

    first, last = min(suspect_pos), max(suspect_pos)
    in_block = (events.index >= first) & (events.index <= last) & (events["_activity"] == culprit)

    old = events.loc[in_block, "_timestamp"].copy()
    events.loc[in_block, "_timestamp"] = old - pd.Timedelta(seconds=shift)

    change_log = pd.DataFrame({"record_id": events.loc[in_block, "_record_id"].values,
                               "old_timestamp": old.values,
                               "new_timestamp": events.loc[in_block, "_timestamp"].values,
                               "shift_seconds": shift})
    backward_after = int((events["_timestamp"].diff().dt.total_seconds() < 0).sum())
    report.update({"culprit_activity": culprit, "shift_seconds": shift,
                   "n_corrected": int(in_block.sum()), "backward_after": backward_after,
                   "status": "repaired"})
    return events, report, change_log