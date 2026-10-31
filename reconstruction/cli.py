"""The toolkit's command line, with input checks, a data health check, a dry run and progress lines.

    python -m reconstruction.cli --config mapping.json --out output_folder [--formats sqlite xml json]
    python -m reconstruction.cli --config mapping.json --profile-only     data health check only, nothing is run
    python -m reconstruction.cli --config mapping.json --dry-run          run and print the report, write nothing

Before anything runs, the config and the four tables are checked and every problem is printed as one line
(exit code 2). The output folder is the same as from python -m reconstruction.reconstruct (that command is
unchanged). The optional config section "settings" sets the toolkit's settings, for example
    "settings": {"identity": {"match_threshold": 0.95}, "missing_links": {"min_events": 50},
                 "o2o": {"min_support": 0.6}}
Settings that are not given keep their defaults (the defaults are the evaluated design).
"""
import argparse
import json
import os
import sys

from reconstruction.mapping import SchemaMapping, apply_mapping
from reconstruction.checks import check_config, read_tables, check_columns, check_tables, parse_settings, path_of
from reconstruction.orchestrate import run_steps, STEPS
from reconstruction.profiling import build_profile_report
from reconstruction.reconstruct import KINDS, _changes, _review, _report, _markdown
from reconstruction.export import write, FORMATS


def load_config(path):
    """Returns (config, problems)."""
    if not os.path.isfile(path):
        return None, [f"config file not found: {path}"]
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), []
    except json.JSONDecodeError as e:
        return None, [f"{path}: not valid JSON (line {e.lineno}, column {e.colno}: {e.msg})"]


def prepare(config):
    """Returns (mapped tables, settings, problems). Stops at the first stage that has problems, listing all of
    that stage's problems: config, then files and columns, then table contents."""
    problems = check_config(config)
    if problems:
        return None, None, problems
    raw, problems = read_tables(config)
    problems += check_columns(raw, config)
    if problems:
        return None, None, problems
    mapping = SchemaMapping(**config["columns"])
    tables = {k: apply_mapping(raw[k], mapping, k) for k in KINDS}
    problems = check_tables(tables, {k: path_of(config, k) for k in KINDS})
    settings, _ = parse_settings(config.get("settings", {}))
    return tables, settings, problems


def health_text(tables):
    r = build_profile_report(tables["events"], tables["objects"], tables["relations"], tables["o2o"])
    order = r["out_of_order_records"]
    lines = ["Data health check", "",
             f"- events: {r['n_events']}, objects: {r['n_items']}, event-to-object links: {r['n_links']}, "
             f"object-to-object links: {r['n_item_to_item_links']}",
             f"- duplicate object-to-object links: {r['duplicate_item_to_item_links']}",
             f"- events linked to no object: {r['unlinked_records']}",
             f"- events earlier than the row before them (file order): {order['out_of_order_records']} "
             f"({order['share_out_of_order']:.2%})",
             f"- rare activity names that look like a typo of a common one: {len(r['label_suspects'])}"]
    lines += [f"    {s.label} ({s.count} events) -> {s.likely_intended} (similarity {s.similarity})"
              for s in r["label_suspects"].itertuples()]
    return "\n".join(lines) + "\n"


def write_outputs(tables, out, changes, review, rep, out_dir, formats):
    """The same files, written the same way, as reconstruction.reconstruct.reconstruct()."""
    os.makedirs(out_dir, exist_ok=True)
    for fmt in formats:
        write(out, os.path.join(out_dir, f"log.{fmt}"), fmt)
    for name, df in changes.items():
        df.to_csv(os.path.join(out_dir, f"changes_{name}.csv"), index=False)
    for name, df in review.items():
        df.to_csv(os.path.join(out_dir, f"review_{name}.csv"), index=False)
    with open(os.path.join(out_dir, "repair_report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    with open(os.path.join(out_dir, "repair_report.md"), "w", encoding="utf-8") as f:
        f.write(_markdown(rep))


def fail(problems, code=2):
    print(f"Found {len(problems)} problem{'s' if len(problems) != 1 else ''} in the input; nothing was run:",
          file=sys.stderr)
    for p in problems:
        print(f"  - {p}", file=sys.stderr)
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m reconstruction.cli",
                                     description="Reconstruct an OCEL 2.0 log from four messy tables.")
    parser.add_argument("--config", required=True, help="JSON file naming the input files and their columns")
    parser.add_argument("--out", help="output folder (not needed with --profile-only or --dry-run)")
    parser.add_argument("--formats", nargs="+", default=["sqlite"], choices=list(FORMATS))
    parser.add_argument("--profile-only", action="store_true", help="print a data health check and stop")
    parser.add_argument("--dry-run", action="store_true", help="run the toolkit and print the report; write nothing")
    args = parser.parse_args(argv)
    if not args.out and not (args.profile_only or args.dry_run):
        parser.error("--out is needed (or use --profile-only or --dry-run)")

    config, problems = load_config(args.config)
    if problems:
        return fail(problems)
    tables, settings, problems = prepare(config)
    if problems:
        return fail(problems)
    if args.profile_only:
        print(health_text(tables), end="")
        return 0

    progress = lambda i, name, s: print(f"[{i}/{len(STEPS)}] {name}: {s:.1f} s", flush=True)
    out, report, extra, info = run_steps(tables, settings["identity"], settings["missing_links"], settings["o2o"],
                                         progress=progress)
    changes, review = _changes(tables, out, extra), _review(extra)
    rep = _report(tables, out, report, changes, review)
    if args.dry_run:
        print(_markdown(rep), end="")
        print("Dry run: nothing was written.")
        return 0
    try:
        write_outputs(tables, out, changes, review, rep, args.out, args.formats)
    except ValueError as e:                                # the export refuses to lose data; its message says why
        print(f"Export stopped: {e}", file=sys.stderr)
        return 1
    print(_markdown(rep), end="")
    print(f"Written to {args.out}: {', '.join(f'log.{f}' for f in args.formats)}, repair report, changes and "
          f"review files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
