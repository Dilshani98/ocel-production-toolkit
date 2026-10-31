import os, sys, json
import pandas as pd

# Checks that clones cannot be found from ID text, ID numbers, row position, missing attributes or
# decimal precision, that event IDs do not name the activity, and that no ID is dangling.
# Ground truth is used here (test code) only to know which IDs are clones.

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "messy")
TAGS = ["sev0_05", "sev0_15", "sev0_3"]


def auc(scores, is_positive):
    """Chance that a random positive scores higher than a random negative (0.5 = no signal)."""
    ranks = pd.Series(scores).rank().values
    pos = pd.Series(is_positive).values.astype(bool)
    n1, n2 = pos.sum(), (~pos).sum()
    return (ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n2)


def template(ids):
    return ids.astype(str).str.replace(r"\d", "#", regex=True)


def number(ids):
    return ids.astype(str).str.extract(r"(\d+)$")[0]


def check(tag, data=DATA):
    ev = pd.read_csv(os.path.join(data, f"messy_events_{tag}.csv"), usecols=["record_id", "activity_name"])
    ob = pd.read_csv(os.path.join(data, f"messy_objects_{tag}.csv"), dtype=str)   # keep values as written
    rel = pd.read_csv(os.path.join(data, f"messy_relations_{tag}.csv"))
    o2o = pd.read_csv(os.path.join(data, f"messy_o2o_{tag}.csv"))
    gt = json.load(open(os.path.join(data, f"ground_truth_{tag}.json")))
    clones = {g["details"]["clone_id"] for g in gt if g["change_type"] == "clone_created"}
    results = {}

    # 1. No dangling or duplicate IDs
    assert ev["record_id"].is_unique and ob["item_id"].is_unique, "duplicate IDs"
    assert rel["record_id"].isin(ev["record_id"]).all(), "relation points to unknown event"
    assert rel["item_id"].isin(ob["item_id"]).all(), "relation points to unknown object"
    assert o2o["item_id"].isin(ob["item_id"]).all(), "o2o source is unknown"
    assert o2o["linked_item_id"].isin(ob["item_id"]).all(), "o2o target is unknown"
    assert clones <= set(ob["item_id"]), "a ground-truth clone is missing from objects"
    gt_ids = {g["target_id"] for g in gt if g["pattern"] in ("timestamp_drift", "label_distortion")}
    assert gt_ids <= set(ev["record_id"]), "ground truth names events that are not in the messy data"

    # 2. ID text: clones use the same templates and digit lengths as real objects of their type
    is_clone = ob["item_id"].isin(clones)
    for typ in ob.loc[is_clone, "item_category"].unique():
        same_type = ob["item_category"] == typ
        c, r = ob.loc[same_type & is_clone, "item_id"], ob.loc[same_type & ~is_clone, "item_id"]
        assert set(template(c)) <= set(template(r)), f"{typ}: clone ID format differs from real IDs"
        lc = number(c).str.len().value_counts(normalize=True)
        lr = number(r).str.len().value_counts(normalize=True)
        gap = lc.sub(lr, fill_value=0).abs().max()
        assert gap < 0.05, f"{typ}: digit-length mix differs by {gap:.3f}"

        # 3. ID numbers: inside the real range, and no threshold separates them
        nc, nr = number(c).astype(int), number(r).astype(int)
        assert nc.min() >= nr.min() and nc.max() <= nr.max(), f"{typ}: clone numbers outside real range"
        a = auc(number(ob.loc[same_type, "item_id"]).astype(int), is_clone[same_type])
        results[f"{typ} number AUC"] = round(a, 3)
        assert 0.4 <= a <= 0.6, f"{typ}: ID number separates clones (AUC {a:.3f})"

        # 4. Row position in the objects file
        pos = pd.Series(range(len(ob)))[same_type.values]
        a = auc(pos, is_clone[same_type].values)
        results[f"{typ} objects position AUC"] = round(a, 3)
        assert 0.4 <= a <= 0.6, f"{typ}: object row position separates clones (AUC {a:.3f})"

    # 4b. Row position of link rows (relations and O2O) among rows of the same object type
    clone_types = set(ob.loc[is_clone, "item_category"])
    typ_of = ob.set_index("item_id")["item_category"]
    r_mask = rel["item_category"].isin(clone_types).values
    a = auc(pd.Series(range(len(rel)))[r_mask], rel["item_id"].isin(clones).values[r_mask])
    results["relations position AUC"] = round(a, 3)
    assert 0.4 <= a <= 0.6, f"relation row position separates clone links (AUC {a:.3f})"
    o_mask = (o2o["item_id"].map(typ_of).isin(clone_types) | o2o["linked_item_id"].map(typ_of).isin(clone_types)).values
    o_clone = (o2o["item_id"].isin(clones) | o2o["linked_item_id"].isin(clones)).values
    assert o_clone[o_mask].any(), "no O2O row names a clone"
    a = auc(pd.Series(range(len(o2o)))[o_mask], o_clone[o_mask])
    results["o2o position AUC"] = round(a, 3)
    assert 0.4 <= a <= 0.6, f"o2o row position separates clone links (AUC {a:.3f})"

    # 5. Numbers shared between event and object IDs
    same_num = (number(rel["record_id"]) == number(rel["item_id"])).mean()
    results["E2O rows with equal event/object number"] = round(same_num, 4)
    assert same_num < 0.01, f"event and object IDs share numbers in {same_num:.1%} of E2O rows"
    ss = rel[rel["item_category"].isin(clone_types)].assign(n=lambda d: number(d["record_id"]))
    shared = ss.groupby("item_id")["n"].agg(lambda s: s.duplicated().any()).mean()
    results["objects whose events share a number"] = round(shared, 4)
    assert shared < 0.01, f"{shared:.1%} of objects have events sharing a number"

    # 5b. Event IDs do not name the activity: one shared prefix, and no activity word in any ID
    prefixes = set(ev["record_id"].str.replace(r"\d+$", "", regex=True))
    assert len(prefixes) == 1, f"event IDs use {len(prefixes)} prefixes: {sorted(prefixes)[:5]}"
    words = {w.lower() for label in ev["activity_name"].unique()
             for w in pd.Series([label]).str.findall(r"[A-Z]?[a-z]+")[0] if len(w) >= 3}
    ids_lower = ev["record_id"].str.lower()
    named = sorted(w for w in words if ids_lower.str.contains(w, regex=False).any())
    assert not named, f"event IDs contain activity words: {named}"

    # 7. Attribute noise: missingness and decimal precision do not separate clones from real objects
    for typ in clone_types:
        rows = ob[ob["item_category"] == typ]
        clone_rows = rows["item_id"].isin(clones).values
        used = [col for col in rows.columns if col not in ("item_id", "item_category") and rows[col].notna().any()]
        a = auc(rows[used].isna().sum(axis=1).values, clone_rows)
        results[f"{typ} missing-attribute AUC"] = round(a, 3)
        assert 0.4 <= a <= 0.6, f"{typ}: number of blank attributes separates clones (AUC {a:.3f})"
        for col in used:
            present = rows[col].notna().values
            if not pd.to_numeric(rows.loc[present, col], errors="coerce").notna().all():
                continue                                  # not a numeric column
            decimals = rows.loc[present, col].map(lambda v: len(v.split(".")[1]) if "." in v else 0).values
            a = auc(decimals, clone_rows[present])
            results[f"{typ} {col} decimals AUC"] = round(a, 3)
            assert 0.4 <= a <= 0.6, f"{typ}: decimal precision of {col} separates clones (AUC {a:.3f})"

    # 6. Ground-truth format: one rename table and the clone settings
    renames = [g for g in gt if g["change_type"] == "ids_renamed"]
    assert len(renames) == 1, "expected exactly one ids_renamed record"
    for pattern in ("object_clones", "attribute_noise"):
        assert any(g["change_type"] == "settings" and g["pattern"] == pattern for g in gt), \
            f"{pattern} settings missing from ground truth"
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ID and position realism checks on the messy data.")
    parser.add_argument("tags", nargs="*", default=TAGS)
    parser.add_argument("--data", default=DATA, help="folder with the messy files (default: seed 42)")
    parser.add_argument("--seed", type=int, default=42, help="seed of that folder, written to the CSV")
    parser.add_argument("--csv", help="also save every AUC as rows (seed, severity, check, auc)")
    args = parser.parse_args()
    failed, rows = 0, []
    for tag in args.tags:
        try:
            res = check(tag, args.data)
            rows += [(args.seed, float(tag[3:].replace("_", ".")), k, v) for k, v in res.items() if k.endswith("AUC")]
            print(f"PASS {tag}")
            for k, v in res.items():
                print(f"   {k}: {v}")
        except AssertionError as e:
            failed += 1
            rows.append((args.seed, float(tag[3:].replace("_", ".")), f"FAILED: {e}", float("nan")))
            print(f"FAIL {tag} - {e}")
    if args.csv:                                          # saved before the final assert, failures included
        new = pd.DataFrame(rows, columns=["seed", "severity", "check", "auc"])
        if os.path.exists(args.csv):                      # replace this seed's rows, keep the others
            old = pd.read_csv(args.csv)
            new = pd.concat([old[old.seed != args.seed], new]).sort_values(["seed", "severity"], kind="stable")
        new.to_csv(args.csv, index=False, lineterminator="\n")
        print(f"saved {len(rows)} rows for seed {args.seed} to {args.csv}")
    assert failed == 0, f"{failed} of {len(args.tags)} severities failed"
    print("ALL ID REALISM TESTS PASSED")
