"""The toolkit pipeline on mapped messy tables: label cleaning -> timestamp repair -> identity resolution."""
from reconstruction.cleaning import clean_activity_labels, repair_timestamp_drift
from reconstruction.identity import resolve_identities

TABLES = ("events", "objects", "relations", "o2o")


def run_toolkit(tables, identity_settings=None, identity_decision="fellegi_sunter"):
    t = {k: tables[k].copy() for k in TABLES}
    t["events"], label_log = clean_activity_labels(t["events"])
    t["events"], ts_report, _ = repair_timestamp_drift(t["events"])
    out, id_report, pairs = resolve_identities(t, identity_settings, identity_decision)
    report = {"labels_changed": int(label_log["n_events"].sum()) if len(label_log) else 0,
              "timestamps": ts_report, "identity": id_report}
    return out, report, pairs
