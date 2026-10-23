"""The full toolkit: the frozen stage 8 pipeline (labels -> timestamps -> identity), then missing E2O recovery.
Kept separate from pipeline.py so the frozen stage 8 files stay unchanged."""
from reconstruction.pipeline import run_toolkit
from reconstruction.relations import recover_missing_links


def run_full_toolkit(tables, identity_settings=None, relation_settings=None):
    out, report, pairs = run_toolkit(tables, identity_settings)
    clusters = out.get("clusters")
    out, rel_report, links = recover_missing_links({k: out[k] for k in ("events", "objects", "relations", "o2o")},
                                                   relation_settings)
    out["clusters"] = clusters
    report["relations"] = rel_report
    return out, report, {"identity_pairs": pairs, "links": links}


def run_b4(tables):
    """B4: B3 (closest-in-time identity) plus eager link filling (nearest fitting orphan, one-to-one)."""
    out, report, pairs = run_toolkit(tables, identity_decision="closest")
    clusters = out.get("clusters")
    out, rel_report, links = recover_missing_links({k: out[k] for k in ("events", "objects", "relations", "o2o")},
                                                   eager=True)
    out["clusters"] = clusters
    report["relations"] = rel_report
    return out, report, {"identity_pairs": pairs, "links": links}
