"""Build the small synthetic example dataset in examples/synthetic/ (our own made-up factory, no external data).

    python examples/make_synthetic.py [--out examples/synthetic] [--seed 1]

Modelled on the hand-made Plant factory in reconstruction/tests/test_o2o.py, scaled up so the toolkit can learn
from it. The clean factory: coils are split into sheets, each sheet is heated and formed into a part, each part
is inspected. Every 10 minutes one sheet starts; the gaps between its steps are regular. The oven logs a check
and one of four sensor records at the moment it heats a sheet.

Then five kinds of damage, each recorded in damage_log.json (used by the tests only; the toolkit never reads it):
    label typos         a few "InspectPart" events get a misspelled activity name
    timestamp drift     one block of consecutive "HeatSheet" events is recorded 120 s late
    clones              some sheets are logged by a second system: the later steps move to a new ID
    missing links       some heat events lose their oven link; some inspections lose their part link
    wrong O2O targets   some parts say they were created from the wrong sheet

The four CSV files use their own column names (see mapping.json). IDs are opaque random numbers.
Deterministic: the same seed gives byte-identical files.
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
T0 = pd.Timestamp("2026-03-02 06:00:00", tz="UTC")
N_SHEETS, N_COILS = 240, 12
N_CLONES, N_TYPOS, N_DRIFT, DRIFT_S = 24, 5, 40, 120
N_NO_OVEN, N_NO_PART, N_SWAPPED = 12, 6, 12
OVEN_LOGS = ("LogTemperature", "LogPressure", "LogDoorState", "LogFanSpeed")   # the oven's record after a heat
TYPOS = ("InspectPrt", "InspectPrt", "InspectPart_", "InspctPart", "InspectPrt")
COLUMNS = {"record_id_col": "event_ref", "activity_col": "step", "timestamp_col": "recorded_at",
           "item_id_col": "thing_id", "item_type_col": "thing_kind", "linked_item_id_col": "other_thing",
           "link_type_col": "relation", "role_col": "part_played"}


def clean_factory(rng):
    """Events (with file order), objects with attributes, E2O links and O2O links of the undamaged factory."""
    events, rel, o2o = [], [], []
    objects = [(f"coil{c}", "Coil", None) for c in range(N_COILS)]
    objects += [(m, "Machine", None) for m in ("splitter", "oven", "press", "scanner")]

    def event(key, act, sec, links):
        events.append({"key": key, "act": act, "time": T0 + pd.Timedelta(seconds=int(sec))})
        rel.extend((key, o, r) for o, r in links)

    for k in range(N_SHEETS):
        s, f, coil = f"sheet{k}", f"part{k}", f"coil{k % N_COILS}"
        objects += [(s, "SteelSheet", round(2.0 + rng.normal(0, 0.05), 4)), (f, "FormedPart", None)]
        t = k * 600
        heat = t + 40 + int(rng.integers(-3, 4))
        form = heat + 30 + int(rng.integers(-3, 4))
        inspect = form + 50 + int(rng.integers(-3, 4))
        event(f"split{k}", "SplitCoil", t, [(s, "output"), (coil, "input"), ("splitter", "machine")])
        event(f"check{k}", "CheckOven", heat, [("oven", "machine")])
        event(f"heat{k}", "HeatSheet", heat, [(s, "input"), ("oven", "machine")])
        event(f"temp{k}", OVEN_LOGS[k % len(OVEN_LOGS)], heat, [("oven", "machine")])
        event(f"form{k}", "FormPart", form, [(s, "input"), (f, "output"), ("press", "machine")])
        event(f"inspect{k}", "InspectPart", inspect, [(f, "input"), ("scanner", "machine")])
        o2o += [(s, coil, "created from"), (f, s, "created from")]
    # file order is time order (stable, so the oven's check / heat / temperature rows stay in that order)
    events = sorted(events, key=lambda e: e["time"])
    return events, objects, rel, o2o


def damage(events, objects, rel, o2o, rng):
    log = {"seed_note": "damage chosen with the same random generator as the clean factory"}
    ev = {e["key"]: e for e in events}
    kind = {o: t for o, t, _ in objects}

    # 1. label typos on InspectPart
    picks = rng.choice(N_SHEETS, size=N_TYPOS, replace=False)
    log["label_typos"] = []
    for k, wrong in zip(sorted(int(p) for p in picks), TYPOS):
        ev[f"inspect{k}"]["act"] = wrong
        log["label_typos"].append({"event": f"inspect{k}", "recorded": wrong, "right": "InspectPart"})

    # 2. one contiguous block of HeatSheet events recorded late
    start = int(rng.integers(20, N_SHEETS - N_DRIFT - 20))
    drifted = [f"heat{k}" for k in range(start, start + N_DRIFT)]
    log["timestamp_drift"] = {"activity": "HeatSheet", "seconds": DRIFT_S,
                              "events": [{"event": e, "right_time": str(ev[e]["time"])} for e in drifted]}
    for e in drifted:
        ev[e]["time"] = ev[e]["time"] + pd.Timedelta(seconds=DRIFT_S)

    # 3. clones: the later steps of a sheet are logged under a second ID (suffix of its 3 steps, 1 or 2 long)
    log["clones"] = []
    sheets = sorted(int(p) for p in rng.choice(N_SHEETS, size=N_CLONES, replace=False))
    moved_o2o = set()
    for k in sheets:
        s, c = f"sheet{k}", f"sheet{k}_copy"
        mass = next(m for o, _, m in objects if o == s)
        objects.append((c, "SteelSheet", mass))                    # the second system copies the record
        kind[c] = "SteelSheet"
        steps = [f"heat{k}", f"form{k}"] if rng.random() < 0.5 else [f"form{k}"]
        rel[:] = [(e, c if (o == s and e in steps) else o, r) for e, o, r in rel]
        moved = []
        for i, (a, b, q) in enumerate(o2o):
            if (a == s or b == s) and rng.random() < 0.5:
                o2o[i] = (c if a == s else a, c if b == s else b, q)
                moved.append([a, b])
                moved_o2o.add(i)
        log["clones"].append({"original": s, "clone": c, "moved_events": steps, "moved_o2o": moved})

    # 4. missing links: oven links on heat events, part links on inspections
    log["removed_links"] = []
    for prefix, typ, n in (("heat", "Machine", N_NO_OVEN), ("inspect", "FormedPart", N_NO_PART)):
        for k in sorted(int(p) for p in rng.choice(N_SHEETS, size=n, replace=False)):
            e = f"{prefix}{k}"
            gone = [(x, o, r) for x, o, r in rel if x == e and kind[o] == typ]
            rel[:] = [t for t in rel if t not in gone]
            log["removed_links"] += [{"event": e, "object": o, "role": r} for _, o, r in gone]

    # 5. wrong O2O targets: a part says it was created from another sheet (never one touched by cloning)
    log["swapped_o2o"] = []
    part_links = [i for i, (a, b, q) in enumerate(o2o)
                  if kind.get(a) == "FormedPart" and i not in moved_o2o and not b.endswith("_copy")]
    for i in sorted(int(p) for p in rng.choice(part_links, size=N_SWAPPED, replace=False)):
        a, b, q = o2o[i]
        others = [o for o, t, _ in objects if t == "SteelSheet" and o != b and not o.endswith("_copy")]
        wrong = others[int(rng.integers(len(others)))]
        o2o[i] = (a, wrong, q)
        log["swapped_o2o"].append({"source": a, "right_target": b, "recorded_target": wrong})
    return events, objects, rel, o2o, log


def opaque_ids(events, objects, rng):
    """Random numbers for every event and object, so no ID text says what a record is."""
    ev_ids = {e["key"]: f"E{n:05d}" for e, n in zip(events, rng.permutation(len(events)) + 1)}
    ob_ids = {o: f"T{n:05d}" for (o, _, _), n in zip(objects, rng.permutation(len(objects)) + 1)}
    return ev_ids, ob_ids


def build(seed=1):
    """Returns the four tables (with the example's own column names) and the damage log in output IDs."""
    rng = np.random.default_rng(seed)
    events, objects, rel, o2o = clean_factory(rng)
    events, objects, rel, o2o, log = damage(events, objects, rel, o2o, rng)
    ev_ids, ob_ids = opaque_ids(events, objects, rng)
    kind = {o: t for o, t, _ in objects}
    tables = {
        "events": pd.DataFrame({"event_ref": [ev_ids[e["key"]] for e in events],
                                "step": [e["act"] for e in events],
                                "recorded_at": [e["time"].isoformat() for e in events]}),
        "objects": pd.DataFrame({"thing_id": [ob_ids[o] for o, _, _ in objects],
                                 "thing_kind": [t for _, t, _ in objects],
                                 "mass_kg": [m for _, _, m in objects]}).sort_values("thing_id").reset_index(drop=True),
        "relations": pd.DataFrame({"event_ref": [ev_ids[e] for e, _, _ in rel], "thing_id": [ob_ids[o] for _, o, _ in rel],
                                   "thing_kind": [kind[o] for _, o, _ in rel], "part_played": [r for _, _, r in rel]}),
        "o2o": pd.DataFrame({"thing_id": [ob_ids[a] for a, _, _ in o2o], "other_thing": [ob_ids[b] for _, b, _ in o2o],
                             "relation": [q for _, _, q in o2o]}),
    }
    e, o = (lambda k: ev_ids[k]), (lambda k: ob_ids[k])
    out_log = {
        "label_typos": [{**t, "event": e(t["event"])} for t in log["label_typos"]],
        "timestamp_drift": {**log["timestamp_drift"], "events": [{**d, "event": e(d["event"])}
                                                                 for d in log["timestamp_drift"]["events"]]},
        "clones": [{"original": o(c["original"]), "clone": o(c["clone"]),
                    "moved_events": [e(x) for x in c["moved_events"]], "moved_o2o": [[o(a), o(b)] for a, b in c["moved_o2o"]]}
                   for c in log["clones"]],
        "removed_links": [{**r, "event": e(r["event"]), "object": o(r["object"])} for r in log["removed_links"]],
        "swapped_o2o": [{"source": o(s["source"]), "right_target": o(s["right_target"]),
                         "recorded_target": o(s["recorded_target"])} for s in log["swapped_o2o"]],
    }
    return tables, out_log


def write(out_dir, seed=1):
    tables, log = build(seed)
    os.makedirs(out_dir, exist_ok=True)
    for kind, df in tables.items():
        df.to_csv(os.path.join(out_dir, f"{kind}.csv"), index=False, lineterminator="\n")
    folder = os.path.relpath(out_dir, os.path.dirname(HERE)).replace(os.sep, "/")
    config = {"folder": folder, "files": {k: f"{k}.csv" for k in tables}, "columns": COLUMNS}
    for name, obj in (("mapping.json", config), ("damage_log.json", log)):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8", newline="\n") as f:
            json.dump(obj, f, indent=2)
            f.write("\n")
    return tables, log


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the synthetic example dataset.")
    parser.add_argument("--out", default=os.path.join(HERE, "synthetic"))
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)
    tables, log = write(args.out, args.seed)
    print(", ".join(f"{k}: {len(v)} rows" for k, v in tables.items()))
    print(f"damage: {len(log['label_typos'])} label typos, {len(log['timestamp_drift']['events'])} drifted events, "
          f"{len(log['clones'])} clones, {len(log['removed_links'])} removed links, "
          f"{len(log['swapped_o2o'])} wrong O2O targets")


if __name__ == "__main__":
    main()
