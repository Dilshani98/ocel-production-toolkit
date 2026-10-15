import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
import pandas as pd
from reconstruction.cleaning import clean_activity_labels
from injection.label_variants import distort_labels

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data", "messy")
TAG = "sev0_15"

raw = pd.read_csv(os.path.join(DATA, f"messy_events_{TAG}.csv"))
gt = json.load(open(os.path.join(DATA, f"ground_truth_{TAG}.json")))

# Rebuild the clean labels (ground truth is used HERE, in the test only).
orig = {g["target_id"]: g["details"]["original_label"] for g in gt if g["pattern"] == "label_distortion"}
clean_labels = pd.Series([orig.get(e, a) for e, a in zip(raw["record_id"], raw["activity_name"])])


def score(cleaned, clean_truth, corrupted_pos):
    after = cleaned["_activity"].values
    before = corrupted_series.values
    is_corr = np.zeros(len(after), dtype=bool)
    is_corr[list(corrupted_pos)] = True
    changed = after != before
    fixed = after == clean_truth.values
    prec = (changed & fixed).sum() / changed.sum() if changed.sum() else 1.0
    rec = (is_corr & fixed).sum() / is_corr.sum() if is_corr.sum() else 1.0
    return prec, rec, int((changed & ~is_corr).sum())


rows = []
for target_name, only in [("HeatSteelSheet only", "HeatSteelSheet"), ("all activities", None)]:
    for mode in ["deletion", "transposition", "substitution", "case_spacing"]:
        corrupted_series, truth = distort_labels(clean_labels, 0.15, 42, mode, only)
        ev = pd.DataFrame({"_activity": corrupted_series})
        for sim in [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]:
            for rare in [0.005, 0.01, 0.02, 0.05]:
                cleaned, _ = clean_activity_labels(ev, rare_share=rare, similarity=sim)
                p, r, w = score(cleaned, clean_labels, truth.keys())
                rows.append({"target": target_name, "mode": mode, "similarity": sim,
                             "rare_share": rare, "precision": round(p, 3),
                             "recall": round(r, 3), "clean_labels_wrongly_changed": w})

res = pd.DataFrame(rows)
res.to_csv(os.path.join(HERE, "label_sensitivity_results.csv"), index=False)
print("Default settings (similarity 0.85, rare 0.02):")
print(res[(res.similarity == 0.85) & (res.rare_share == 0.02)].to_string(index=False))
print("\nWorst case per similarity (rare_share 0.02):")
print(res[res.rare_share == 0.02].groupby("similarity").agg(
    min_precision=("precision", "min"), min_recall=("recall", "min"),
    max_wrong=("clean_labels_wrongly_changed", "max")).to_string())
print("\nWorst case per rare_share (similarity 0.85):")
print(res[res.similarity == 0.85].groupby("rare_share").agg(
    min_precision=("precision", "min"), min_recall=("recall", "min"),
    max_wrong=("clean_labels_wrongly_changed", "max")).to_string())