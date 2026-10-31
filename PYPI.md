# OCEL Production Toolkit

Rebuilds an **OCEL 2.0** object-centric event log from messy, fragmented production data. It fixes misspelled
activity names, shifted timestamps, objects recorded twice under different IDs, missing event-to-object links and
wrong object-to-object links. What it is not sure about it leaves alone, and lists it for review.

Master of Software Engineering capstone project, Yoobee College of Creative Innovation, Auckland.
Full documentation, the evaluation and the example data: https://github.com/Dilshani98/ocel-production-toolkit

## Install

```bash
pip install ocel-production-toolkit
```

Python 3.11 or newer (tested on 3.11 and 3.14). The published evaluation results were produced with the exact
versions in the repository's `requirements.txt`.

## Use

Your data is four CSV files: events, objects, event-to-object links and object-to-object links, with any column
names. A small JSON config says which file and column is which:

```json
{"folder": "my_data",
 "files": {"events": "events.csv", "objects": "objects.csv", "relations": "relations.csv", "o2o": "o2o.csv"},
 "columns": {"record_id_col": "event_id", "activity_col": "activity", "timestamp_col": "time",
             "item_id_col": "object_id", "item_type_col": "object_type", "linked_item_id_col": "linked_object_id",
             "link_type_col": "link_type", "role_col": "role"}}
```

```bash
ocel-reconstruct --config mapping.json --profile-only    # data health check, nothing is changed
ocel-reconstruct --config mapping.json --dry-run         # run and print the report, write nothing
ocel-reconstruct --config mapping.json --out results --formats sqlite xml json
```

Every input problem (a missing column, an unreadable date, a link to an object that does not exist) is listed in
one plain line before anything runs. The output folder holds:

- `log.sqlite` / `log.xml` / `log.json`: the rebuilt OCEL 2.0 log
- `repair_report.md` / `.json`: what was changed, and what was left alone and why
- `changes_*.csv`: every single change
- `review_*.csv`: decisions left to a person, each with a reason

A ready-made example dataset is in the repository's `examples/synthetic/` folder.

## Limits

The toolkit was evaluated on one simulated, idealised production process (the sOCEL 2.0 hinge-production log),
with damage injected on purpose. On other data it repairs only what it is sure about; read the review files.
Results and limitations: https://github.com/Dilshani98/ocel-production-toolkit#results-in-short

## Licence

MIT. The toolkit installs pm4py, which is licensed separately under AGPL-3.0.
