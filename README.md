# OCEL Production Toolkit

An open-source toolkit that rebuilds an **OCEL 2.0** object-centric event log from messy, fragmented production
data, and an experiment that measures how well it does so against a known right answer.

Master of Software Engineering capstone project (MSE907), Yoobee College of Creative Innovation, Auckland.
Title: *An Open-Source Toolkit for Object-Centric Event Log Extraction from Production Systems.*

## What the toolkit does

You give it four tables, in any column names: **events**, **objects**, **event-to-object links (E2O)** and
**object-to-object links (O2O)**. It repairs them in five steps and writes a valid OCEL 2.0 log:

1. **Activity labels**: a rare label that is very similar to one common label (a typo) is changed to that label.
   If two common labels are equally close, nothing is changed.
2. **Timestamps**: a block of events from one activity that was shifted in time (clock drift) is found from
   backward steps in the file order and shifted back.
3. **Object identity**: two records of the same physical object (for example a steel sheet logged by two
   systems) are found with Fellegi–Sunter record linkage and merged. Only confident matches are merged; the
   rest are listed for review.
4. **Missing E2O links**: a link is added only where the evidence points to exactly one object (for example
   the one machine every event of that activity uses). Everything else is listed for review.
5. **Incorrect O2O links**: a link that breaks a set rule seen in the data (for example "each part is created
   from exactly one sheet") is repaired when exactly one replacement fits, and otherwise only flagged.

The design rule throughout: **a missed fix is better than a wrong fix.** The toolkit never uses the text or
numbers inside IDs; IDs are only used as keys to join tables.

## Install

Python 3.14.3 was used. In a new virtual environment:

```bash
pip install -r requirements.txt
```

On Windows, install into a folder with a short path (for example `C:\venvs\ocel`). pm4py has very deep file
paths, and with a long folder name the install fails with "No such file or directory" unless Windows long
path support is turned on.

## Use the toolkit on your own data

```bash
python -m reconstruction.reconstruct --config mapping.json --out output_folder --formats sqlite xml json
```

`mapping.json` names the four input files and the column that holds each field:

```json
{"folder": "data/raw",
 "files": {"events": "events.csv", "objects": "objects.csv", "relations": "relations.csv", "o2o": "o2o.csv"},
 "columns": {"record_id_col": "record_id", "activity_col": "activity_name", "timestamp_col": "event_time",
             "item_id_col": "item_id", "item_type_col": "item_category", "linked_item_id_col": "linked_item_id",
             "link_type_col": "link_type", "role_col": "role"}}
```

The output folder then holds:

| File | What it is |
|---|---|
| `log.sqlite` / `log.xml` / `log.json` | the reconstructed OCEL 2.0 log (SQLite by default) |
| `repair_report.md` / `.json` | what was changed and how often, and what was left alone and why |
| `changes_*.csv` | every single change: labels, timestamps, merged objects, added links, repaired O2O links |
| `review_*.csv` | decisions the toolkit did not make (possible matches, links it could not place), each with a reason |

### Known export limitations (pm4py)

The log is written with pm4py 2.7.23.3. Its writers have four behaviours the export works around or reports:

- **No keys in SQLite.** pm4py's SQLite writer declares no primary or foreign keys. The OCEL 2.0 specification
  defines them, so the export adds them (24 key constraints) after writing.
- **Dangling links are dropped silently.** pm4py's writers leave out a link whose event or object does not
  exist. The export checks every reference first and refuses to write if one is dangling, so nothing is lost
  without a message.
- **Objects without events are dropped.** pm4py's writers and readers leave out objects that have no
  event-to-object link, although OCEL 2.0 allows them. The export writes them back into the file, and the
  toolkit's reader (`reconstruction.export.read`) reads them back.
- **A type with no events at all cannot be exported.** If no object of a type has an event, pm4py writes no
  declaration for that type. The export does not invent one; it stops with a message naming the object and
  the type, and saying how to fix the input (give one object of that type an event, or remove those objects).
  This does not happen in the dataset used here.

## Reproduce the experiment

The experiment damages a clean log on purpose (with a log of every change), runs the toolkit and six
baselines on the damaged tables, and scores every output against the clean log.

```bash
python tests/generate_datasets.py                                   # damaged tables, seed 42 (development)
python tests/generate_datasets.py --seed 7 --out data/seeds/seed7   # held-out seed
python tests/generate_datasets.py --seed 123 --out data/seeds/seed123
python evaluation/run_stage10.py      # all systems, 3 seeds x 3 severities -> results/scores_stage10.csv
python evaluation/run_stage11.py      # OCEL 2.0 export and round-trip checks -> results/export_validation.csv
python evaluation/run_experiments.py  # checks the design freezes, re-runs seed 42 and requires the saved
                                      # scores exactly, then builds report_assets/
```

`python evaluation/run_experiments.py --full` runs the stage 10 and 11 runners itself first (about 1.5 hours).

The detail tables and figures need the realism results, then their own builder:

```bash
python tests/test_id_realism.py --seed 42 --data data/messy --csv results/realism_auc.csv
python tests/test_id_realism.py --seed 7 --data data/seeds/seed7 --csv results/realism_auc.csv
python tests/test_id_realism.py --seed 123 --data data/seeds/seed123 --csv results/realism_auc.csv
python evaluation/make_report_details.py
```

### Where results land

- `results/` (not in git): every score, diagnostic file and exported log.
- `report_assets/` (in git): the tables and figures used in the report, and `numbers.md` with every reported
  number as text. Rebuilding them gives byte-identical files.

## How the evaluation is kept honest

- **Blind separation.** Code in `reconstruction/` never reads the clean log or the ground truth, and never
  imports the damage or scoring code. `tests/test_blind_separation.py` checks this.
- **Design freezes.** Each design was frozen (file hashes in `evaluation/toolkit_freeze*.json`) before it was
  run on the held-out seeds. Any later change is a dated amendment with its reason. The runners refuse to run if
  a frozen file has changed.
- **Development and held-out seeds.** Rules were explored on seed 42 only. Seeds 7 and 123 are held out and are
  the headline; seed 42 is reported separately.
- **Clean log.** The toolkit is also run on the undamaged log, where it must change nothing. It changed
  nothing: 0 labels, 0 timestamps, 0 merges, and E2O and O2O links identical to the clean log.
- **Baselines.** B0 (as-is), B1 (hygiene), B2 (exact-attribute merge), B3 (closest in time), B4 (B3 plus
  eager link filling) and B5 (the toolkit, deleting suspect O2O links instead of repairing them).

## Results in short

Held-out seeds 7 and 123 (mean over 2 seeds) at 5% / 15% / 30% damage. Full tables: `report_assets/numbers.md`.

| Measure | Toolkit | Damaged log as-is (B0) |
|---|---|---|
| Identity precision | 1.000 / 0.999 / 0.998 | – (no merges) |
| Identity recall | 0.959 / 0.779 / 0.654 | 0 |
| Wrong identity merges (pairs) | 0 / 1 / 2.5 | – |
| E2O links added that are wrong | 0 / 0 / 0 | – |
| O2O F1 | 0.9995 / 0.989 / 0.965 | 0.936 / 0.814 / 0.641 |
| Directly-follows edge F1 | 0.992 / 0.992 / 0.992 | 0.470 / 0.380 / 0.334 |

Two seeds is a small sample; the tables give the min and max next to every mean.

## Limitations

- The data is one simulated, idealised process (sOCEL 2.0 hinge production). Results may not carry over to
  real MES or ERP data.
- The damage is injected by this project, so the toolkit could be fitted to it. Held-out seeds, baselines, a
  label-variant experiment and threshold checks reduce this risk but do not remove it.
- The four "fragmented" tables come from one log with renamed columns, not from truly separate systems.
- Timestamp repair assumes one shifted block, a meaningful file order and events close in time.
- Identity resolution relies on this process's very regular timing and on each object being split into at
  most two records.
- Missing links are recovered mainly where one object serves an activity; part links are rarely recovered.
- The clean log's 8,825 object attribute changes over time never reach the damaged tables, so the rebuilt log
  has none.
- Usefulness is measured with directly-follows edges and object counts, not a full conformance check.
- The realism check found one chance failure: on seed 7 at 5%, one clone holds the highest SteelSheet ID
  number, so the "inside the real range" rule fails, although the ID number has no signal (AUC 0.485).

## Tests

Every test is a plain script with `assert`s; run it directly, for example
`python reconstruction/tests/test_identity.py`. Tests are in `reconstruction/tests/`, `evaluation/tests/` and
`tests/`.

## Data source and citation

> **[PLACEHOLDER: dataset citation and licence.]** The clean log `socel2_hinge.xml` is the sOCEL 2.0
> hinge-production log published on Zenodo. Its citation and licence are to be checked on the Zenodo record and
> filled in here before release.

## Licence

> **[PLACEHOLDER: licence to be chosen.]** pm4py, which this toolkit uses, is licensed under AGPL-3.0.
