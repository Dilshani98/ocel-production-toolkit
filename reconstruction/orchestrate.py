"""The complete toolkit, one step at a time: the same calls in the same order as run_complete_toolkit
(complete.py -> toolkit.py -> pipeline.py), so each step can be timed and the O2O settings passed through.
Kept separate so the frozen files stay unchanged; with default settings the output equals run_complete_toolkit.
"""
import time

from reconstruction.cleaning import clean_activity_labels, repair_timestamp_drift
from reconstruction.identity import resolve_identities
from reconstruction.relations import recover_missing_links
from reconstruction.o2o import repair_o2o

TABLES = ("events", "objects", "relations", "o2o")
STEPS = ("activity labels", "timestamps", "object identity", "missing links", "object-to-object links")


def run_steps(tables, identity_settings=None, relation_settings=None, o2o_settings=None, progress=None):
    """Returns (out, report, extra, info): out, report and extra as from run_complete_toolkit; info holds the
    seconds per step and the tables after identity resolution (the input of missing-link recovery).
    progress(step_number, step_name, seconds) is called after each step."""
    timings, clock = [], time.perf_counter()

    def done(name):
        nonlocal clock
        now = time.perf_counter()
        timings.append((name, now - clock))
        if progress:
            progress(len(timings), name, now - clock)
        clock = now

    t = {k: tables[k].copy() for k in TABLES}
    t["events"], label_log = clean_activity_labels(t["events"])
    done(STEPS[0])
    t["events"], ts_report, _ = repair_timestamp_drift(t["events"])
    done(STEPS[1])
    out, id_report, pairs = resolve_identities(t, identity_settings, "fellegi_sunter")
    report = {"labels_changed": int(label_log["n_events"].sum()) if len(label_log) else 0,
              "timestamps": ts_report, "identity": id_report}
    done(STEPS[2])
    clusters = out.get("clusters")
    after_identity = {k: out[k] for k in TABLES}
    out, rel_report, links = recover_missing_links(after_identity, relation_settings)
    out["clusters"] = clusters
    report["relations"] = rel_report
    done(STEPS[3])
    out, o2o_report, decisions = repair_o2o({k: out[k] for k in TABLES}, settings=o2o_settings, delete=False)
    out["clusters"] = clusters
    report["o2o"] = o2o_report
    done(STEPS[4])
    extra = {"identity_pairs": pairs, "links": links, "o2o_decisions": decisions}
    return out, report, extra, {"timings": timings, "after_identity": after_identity}
