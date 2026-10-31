"""The complete toolkit: the frozen stage 9 pipeline (labels -> timestamps -> identity -> missing E2O),
then incorrect O2O repair. Kept separate so the frozen stage 8 and 9 files stay unchanged."""
from reconstruction.toolkit import run_full_toolkit
from reconstruction.o2o import repair_o2o

TABLES = ("events", "objects", "relations", "o2o")


def _with_o2o(tables, delete, **kwargs):
    out, report, extra = run_full_toolkit(tables, **kwargs)
    clusters = out.get("clusters")
    out, o2o_report, decisions = repair_o2o({k: out[k] for k in TABLES}, delete=delete)
    out["clusters"] = clusters
    report["o2o"] = o2o_report
    extra["o2o_decisions"] = decisions
    return out, report, extra


def run_complete_toolkit(tables, identity_settings=None, relation_settings=None):
    return _with_o2o(tables, delete=False, identity_settings=identity_settings, relation_settings=relation_settings)


def run_b5(tables):
    """B5: the complete toolkit, but unsupported O2O links are deleted instead of repaired."""
    return _with_o2o(tables, delete=True)
