import os, sys, json
import pandas as pd

# Leak and integrity checks on the generated messy data, for all three severities (seed 42 folder by default;
# pass another folder, e.g. data/seeds/seed7, as the first argument).

D = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "data", "messy")
TAGS = ("sev0_05", "sev0_15", "sev0_3")


def check(tag):
    ev = pd.read_csv(os.path.join(D, f"messy_events_{tag}.csv"))
    obj = pd.read_csv(os.path.join(D, f"messy_objects_{tag}.csv"))
    rel = pd.read_csv(os.path.join(D, f"messy_relations_{tag}.csv"))
    o2o = pd.read_csv(os.path.join(D, f"messy_o2o_{tag}.csv"))
    gt = json.load(open(os.path.join(D, f"ground_truth_{tag}.json")))

    # 1. No OCEL-style column names left in any file
    for name, df in [("events", ev), ("objects", obj), ("relations", rel), ("o2o", o2o)]:
        left = [c for c in df.columns if c.startswith("ocel:")]
        assert not left, f"{tag} {name}: OCEL columns left: {left}"

    # 2. Timestamp ground truth is correct for ALL logged events
    ev["event_time"] = pd.to_datetime(ev["event_time"], utc=True, format="mixed")
    now = ev.set_index("record_id")["event_time"]
    ts = [c for c in gt if c["pattern"] == "timestamp_drift"]
    bad = sum(now[c["target_id"]] - pd.to_datetime(c["details"]["original_timestamp"], utc=True)
              != pd.Timedelta(seconds=c["details"]["drift_seconds"]) for c in ts)
    assert ts and bad == 0, f"{tag}: {bad} of {len(ts)} timestamp entries wrong"

    # 3. The relations table does not leak clean columns, and nothing points to something that doesn't exist
    leak = [c for c in rel.columns if c in ("activity_name", "event_time")]
    assert not leak, f"{tag}: relations leak clean columns {leak}"
    dangling = {"relations -> unknown event": (~rel["record_id"].isin(ev["record_id"])).sum(),
                "relations -> unknown object": (~rel["item_id"].isin(obj["item_id"])).sum(),
                "o2o unknown source": (~o2o["item_id"].isin(obj["item_id"])).sum(),
                "o2o unknown target": (~o2o["linked_item_id"].isin(obj["item_id"])).sum()}
    assert not any(dangling.values()), f"{tag}: dangling references {dangling}"
    print(f"   {tag}: {len(ev)} events, {len(obj)} objects, {len(rel)} links, {len(o2o)} O2O links; "
          f"{len(ts)} timestamp entries all correct; no OCEL columns, leaks or dangling references")


if __name__ == "__main__":
    for tag in TAGS:
        check(tag)
    print(f"MESSY OUTPUT VERIFIED ({len(TAGS)} severities, {os.path.normpath(D)})")
