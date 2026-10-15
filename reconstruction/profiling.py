from difflib import SequenceMatcher
import pandas as pd


def profile_activity_labels(events, rare_share=0.02, similarity=0.85):
    """Finds rare activity names that look like typos of a common name.
    Uses only the messy events table (mapped columns)."""
    counts = events["_activity"].value_counts()
    total = counts.sum()
    common = counts[counts / total >= rare_share].index.tolist()
    rare = counts[counts / total < rare_share].index.tolist()

    suspects = []
    for name in rare:
        best, best_score = None, 0.0
        for ref in common:
            score = SequenceMatcher(None, name, ref).ratio()
            if score > best_score:
                best, best_score = ref, score
        if best_score >= similarity:
            suspects.append({"label": name, "count": int(counts[name]),
                             "likely_intended": best, "similarity": round(best_score, 3)})
    return pd.DataFrame(suspects)


def profile_unlinked_records(events, relations):
    """Records that exist in the events table but have no link to any item."""
    linked = set(relations["_record_id"])
    unlinked = events[~events["_record_id"].isin(linked)]
    return len(unlinked)


def profile_event_ordering(events):
    """Counts records whose time is earlier than the previous record's
    time within the same activity (a sign of timestamp problems)."""
    ts = pd.to_datetime(events["_timestamp"], utc=True, format="mixed")
    backwards = ts.diff().dt.total_seconds() < 0   # record is earlier than the one before it
    return {
        "out_of_order_records": int(backwards.sum()),
        "share_out_of_order": round(float(backwards.mean()), 4),
    }


def build_profile_report(events, objects, relations, o2o):
    return {
        "n_events": len(events),
        "n_items": len(objects),
        "n_links": len(relations),
        "n_item_to_item_links": len(o2o),
        "duplicate_item_to_item_links": int(o2o.duplicated().sum()),
        "label_suspects": profile_activity_labels(events),
        "unlinked_records": profile_unlinked_records(events, relations),
        "out_of_order_records": profile_event_ordering(events),
    }