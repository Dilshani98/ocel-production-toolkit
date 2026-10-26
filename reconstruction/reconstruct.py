"""Reconstruct an OCEL 2.0 log from four messy tables. This is the toolkit's user-facing command.

    python -m reconstruction.reconstruct --config mapping.json --out output_folder [--formats sqlite xml json]

The config (JSON) names the four input files and the columns that hold each field, for example:
    {"folder": "data/raw",
     "files": {"events": "events.csv", "objects": "objects.csv", "relations": "relations.csv", "o2o": "o2o.csv"},
     "columns": {"record_id_col": "record_id", "activity_col": "activity_name", "timestamp_col": "event_time",
                 "item_id_col": "item_id", "item_type_col": "item_category", "linked_item_id_col": "linked_item_id",
                 "link_type_col": "link_type", "role_col": "role"}}

Outputs in the output folder:
    log.<format>                 the reconstructed OCEL 2.0 log (SQLite with the specification's keys by default)
    repair_report.json / .md     what was changed, how many, and what was left alone and why
    changes_*.csv                every change made (labels, timestamps, merged objects, added links, repaired links)
    review_*.csv                 what the toolkit did not decide and a person should look at

Only the four input tables are read. The toolkit runs label cleaning, timestamp repair, object identity
resolution, missing-link recovery and object-to-object repair, then writes the log with the export module.
"""
import argparse
import json
import os

import pandas as pd

from reconstruction.mapping import SchemaMapping, apply_mapping
from reconstruction.complete import run_complete_toolkit
from reconstruction.export import write, FORMATS

KINDS = ("events", "objects", "relations", "o2o")


def load_tables(config):
    mapping = SchemaMapping(**config["columns"])
    folder = config.get("folder", ".")
    tables = {}
    for kind in KINDS:
        path = os.path.join(folder, config["files"][kind])
        tables[kind] = apply_mapping(pd.read_csv(path, low_memory=False), mapping, kind)
    return tables


def _changes(before, after, extra):
    """Every change, derived by comparing the input with the output (and the toolkit's decision tables)."""
    ev_in = before["events"].drop_duplicates("_record_id").set_index("_record_id")
    ev_out = after["events"].drop_duplicates("_record_id").set_index("_record_id").reindex(ev_in.index)
    label = ev_in["_activity"] != ev_out["_activity"]
    labels = pd.DataFrame({"event": ev_in.index[label], "old_label": ev_in["_activity"][label].values,
                           "new_label": ev_out["_activity"][label].values})
    t_in = pd.to_datetime(ev_in["_timestamp"], utc=True, format="mixed")
    t_out = pd.to_datetime(ev_out["_timestamp"], utc=True, format="mixed")
    moved = t_in != t_out
    timestamps = pd.DataFrame({"event": ev_in.index[moved], "old_time": t_in[moved].astype(str).values,
                               "new_time": t_out[moved].astype(str).values,
                               "shift_seconds": (t_out[moved] - t_in[moved]).dt.total_seconds().values})
    clusters = after.get("clusters")
    merged = clusters[clusters["_item_id"] != clusters["_cluster_id"]].rename(
        columns={"_item_id": "merged_id", "_cluster_id": "kept_id"}) if clusters is not None and len(clusters) \
        else pd.DataFrame(columns=["merged_id", "kept_id"])
    links = extra["links"]
    added = links[links["rule"].isin(["R1", "R2"])][["event", "activity", "type", "object", "rule"]] \
        if len(links) else pd.DataFrame(columns=["event", "activity", "type", "object", "rule"])
    dec = extra["o2o_decisions"]
    repaired = dec[dec["status"] == "repaired"][["source", "link_type", "old_target", "new_target"]] \
        if len(dec) else pd.DataFrame(columns=["source", "link_type", "old_target", "new_target"])
    return {"labels": labels, "timestamps": timestamps, "merged_objects": merged,
            "added_links": added, "repaired_o2o": repaired}


def _review(extra):
    """Decisions the toolkit left open, with the reason."""
    pairs = extra["identity_pairs"]
    open_pairs = pairs[pairs["status"].isin(["possible", "ambiguous"])] if len(pairs) else pairs
    identity = pd.DataFrame({"object_a": open_pairs.get("a", []), "object_b": open_pairs.get("b", []),
                             "posterior": open_pairs.get("posterior", []),
                             "reason": open_pairs.get("status", pd.Series(dtype=str)).map(
                                 {"possible": "match probability between the two thresholds",
                                  "ambiguous": "another candidate is almost as likely"})})
    links = extra["links"]
    possible = links[links["rule"].isin(["possible", "no candidate"])] if len(links) else links
    e2o = pd.DataFrame({"event": possible.get("event", []), "activity": possible.get("activity", []),
                        "missing_type": possible.get("type", []), "fitting_candidates": possible.get("n_candidates", []),
                        "reason": possible.get("rule", pd.Series(dtype=str)).map(
                            {"possible": "several objects fit; none is certain",
                             "no candidate": "no object of this type fits"})})
    dec = extra["o2o_decisions"]
    flagged = dec[dec["status"] == "flagged"] if len(dec) else dec
    o2o = pd.DataFrame({"source": flagged.get("source", []), "link_type": flagged.get("link_type", []),
                        "current_target": flagged.get("old_target", []),
                        "reason": "the objects share no event, and the right target is not determined"})
    return {"identity": identity, "e2o_links": e2o, "o2o_links": o2o}


def _report(tables, out, report, changes, review):
    rel, ident, o2o = report["relations"], report["identity"], report["o2o"]
    untrusted = [a for a, info in rel["activities"].items() if not info["trusted"]]
    return {
        "input": {k: int(len(tables[k])) for k in KINDS},
        "output": {k: int(len(out[k])) for k in KINDS},
        "changed": {
            "activity labels": int(len(changes["labels"])),
            "timestamps": int(len(changes["timestamps"])),
            "objects merged into another ID": int(len(changes["merged_objects"])),
            "event-to-object links added": int(len(changes["added_links"])),
            "object-to-object links repaired": int(len(changes["repaired_o2o"]))},
        "left alone (see review files)": {
            "possible identity matches not merged": int(len(review["identity"])),
            "missing event-to-object links not added": int(len(review["e2o_links"])),
            "unsupported object-to-object links not changed": int(len(review["o2o_links"])),
            "activities whose usual object types could not be trusted": untrusted},
        "details": {"timestamp repair": report["timestamps"]["status"],
                    "object types with a learned lifecycle": sorted(ident["lifecycles"]),
                    "object-to-object groups checked": sum(g["verifiable"] for g in o2o["groups"])},
    }


def _markdown(rep):
    lines = ["# Repair report", "", "## Changed", ""]
    lines += [f"- {k}: {v}" for k, v in rep["changed"].items()]
    lines += ["", "## Left alone, and why", ""]
    for k, v in rep["left alone (see review files)"].items():
        lines.append(f"- {k}: {', '.join(v) if isinstance(v, list) and v else (v if not isinstance(v, list) else 'none')}")
    lines += ["", "Reasons are given per row in the review_*.csv files.", "", "## Sizes", "",
              "| table | input rows | output rows |", "|---|---|---|"]
    lines += [f"| {k} | {rep['input'][k]} | {rep['output'][k]} |" for k in KINDS]
    lines += ["", "## Details", ""] + [f"- {k}: {v}" for k, v in rep["details"].items()]
    return "\n".join(lines) + "\n"


def reconstruct(config, out_dir, formats=("sqlite",)):
    """Run the toolkit on the configured tables and write the log, the report, the changes and the review lists."""
    tables = load_tables(config)
    out, report, extra = run_complete_toolkit(tables)
    os.makedirs(out_dir, exist_ok=True)
    for fmt in formats:
        write(out, os.path.join(out_dir, f"log.{fmt}"), fmt)
    changes, review = _changes(tables, out, extra), _review(extra)
    for name, df in changes.items():
        df.to_csv(os.path.join(out_dir, f"changes_{name}.csv"), index=False)
    for name, df in review.items():
        df.to_csv(os.path.join(out_dir, f"review_{name}.csv"), index=False)
    rep = _report(tables, out, report, changes, review)
    with open(os.path.join(out_dir, "repair_report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    with open(os.path.join(out_dir, "repair_report.md"), "w", encoding="utf-8") as f:
        f.write(_markdown(rep))
    return rep


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reconstruct an OCEL 2.0 log from four messy tables.")
    parser.add_argument("--config", required=True, help="JSON file naming the input files and their columns")
    parser.add_argument("--out", required=True, help="output folder")
    parser.add_argument("--formats", nargs="+", default=["sqlite"], choices=list(FORMATS))
    args = parser.parse_args(argv)
    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)
    rep = reconstruct(config, args.out, args.formats)
    print(_markdown(rep))


if __name__ == "__main__":
    main()
