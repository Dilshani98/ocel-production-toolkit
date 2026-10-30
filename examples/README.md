# Examples

## `synthetic/`: a small made-up factory (committed)

Four CSV files with their own column names, a `mapping.json` for the command, and `damage_log.json` listing every
damaged value (the toolkit never reads it; the tests use it to check every change). Built by
`python examples/make_synthetic.py`; the same seed always gives the same files.

The factory: 12 coils are split into 240 steel sheets; each sheet is heated and formed into a part, and each part is
inspected. The damage: 5 misspelled activity names, 40 heat events recorded 120 s late, 24 sheets whose later steps
were logged under a second ID, 18 removed links, and 12 parts pointing to the wrong sheet.

Run from the project root:

```bash
python -m reconstruction.reconstruct --config examples/synthetic/mapping.json --out output
```

Expected repair report: 5 labels, 40 timestamps, 24 merges, 18 links added, 12 object-to-object links repaired, and
nothing left for review. `tests/test_example_end_to_end.py` checks every one of these changes against
`damage_log.json`.

This example is deliberately easy: the timings are very regular and the damage is light. It shows how the command
works; it is not evidence of how well the toolkit performs. The evaluation results are in `report_assets/`.

## `socel_subset/`: a cut of the damaged sOCEL 2.0 data (generated locally, not committed)

About 5% of the damaged hinge-production data (seed 42, 15% damage): the events between 10% and 17% of the file
that involve objects whose events all lie in that window, with every object and link on those events. Built by
`python examples/make_socel_subset.py` after `python tests/generate_datasets.py`.

The window overlaps the start of the drifted timestamp block, so the demo shows every kind of repair and also leaves
items for review. It is derived from the sOCEL 2.0 log, so it is committed only once the dataset's licence allows
redistribution. Source and licence: see "Data source and citation" in the main README.
