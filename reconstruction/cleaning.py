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


def clean_activity_labels(events, rare_share=0.02, similarity=0.85, dominance=5):
    events = events.copy()
    counts = events["_activity"].value_counts()
    total = len(events)

    mapping, log_rows = {}, []
    for label, n in counts.items():
        if n / total >= rare_share:
            continue
        best, best_score = None, 0.0
        for other, other_n in counts.items():
            if other == label or other_n < dominance * n:
                continue
            score = _similarity(_normalise(label), _normalise(other))
            if score > best_score:
                best, best_score = other, score
        if best is not None and best_score >= similarity:
            mapping[label] = best
            log_rows.append({"old_label": label, "new_label": best,
                             "n_events": int(n), "similarity": round(best_score, 3)})

    events["_activity"] = events["_activity"].replace(mapping)
    change_log = pd.DataFrame(log_rows, columns=["old_label", "new_label", "n_events", "similarity"])
    return events, change_log