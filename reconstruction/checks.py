"""Input checks for the command line: every problem as one plain line, all problems listed at once.

check_config(config)        the config's keys, folder, files and settings
read_tables(config)         the four CSV files (empty or unreadable files are problems, not tracebacks)
check_columns(raw, config)  the mapped columns exist in each file
check_tables(tables)        mapped tables: empty tables, duplicate event IDs, missing or unreadable timestamps,
                            links to events or objects that do not exist
parse_settings(settings)    the optional "settings" section, turned into the toolkit's settings objects
An empty object-to-object table is allowed (a log may have no such links).
"""
import dataclasses
import os

import pandas as pd

from reconstruction.identity import IdentitySettings
from reconstruction.relations import RelationSettings
from reconstruction.o2o import O2OSettings

KINDS = ("events", "objects", "relations", "o2o")
COLUMN_KEYS = ("record_id_col", "activity_col", "timestamp_col", "item_id_col", "item_type_col",
               "linked_item_id_col", "link_type_col", "role_col")
NEEDED = {"events": ("record_id_col", "activity_col", "timestamp_col"),
          "objects": ("item_id_col", "item_type_col"),
          "relations": ("record_id_col", "item_id_col", "item_type_col", "role_col"),
          "o2o": ("item_id_col", "linked_item_id_col", "link_type_col")}
SETTINGS = {"identity": IdentitySettings, "missing_links": RelationSettings, "o2o": O2OSettings}


def _eg(values, n=3):
    values = list(dict.fromkeys(str(v) for v in values))
    return ", ".join(values[:n]) + (", ..." if len(values) > n else "")


def path_of(config, kind):
    return os.path.join(config.get("folder", "."), config["files"][kind])


def check_config(config):
    if not isinstance(config, dict):
        return ["the config must be a JSON object with the keys \"files\" and \"columns\""]
    problems = []
    files, columns = config.get("files"), config.get("columns")
    if not isinstance(files, dict):
        problems.append("config key \"files\" is missing (it names the events, objects, relations and o2o files)")
    else:
        problems += [f"config key \"files.{k}\" is missing" for k in KINDS if k not in files]
    if not isinstance(columns, dict):
        problems.append("config key \"columns\" is missing (it names the column that holds each field)")
    else:
        problems += [f"config key \"columns.{k}\" is missing" for k in COLUMN_KEYS if k not in columns]
        problems += [f"config key \"columns.{k}\" is not known (expected: {', '.join(COLUMN_KEYS)})"
                     for k in columns if k not in COLUMN_KEYS]
    folder = config.get("folder", ".")
    if not os.path.isdir(folder):
        problems.append(f"input folder not found: {folder}")
    elif isinstance(files, dict):
        problems += [f"input file not found: {path_of(config, k)} (files.{k})" for k in KINDS
                     if k in files and not os.path.isfile(path_of(config, k))]
    if "settings" in config:
        problems += parse_settings(config["settings"])[1]
    return problems


def read_tables(config):
    """Returns (raw tables, problems). Reads every file even after a problem, so all problems are reported."""
    raw, problems = {}, []
    for kind in KINDS:
        path = path_of(config, kind)
        try:
            raw[kind] = pd.read_csv(path, low_memory=False)
        except pd.errors.EmptyDataError:
            problems.append(f"{path}: the file is empty (not even a header row)")
        except (pd.errors.ParserError, UnicodeDecodeError) as e:
            problems.append(f"{path}: cannot be read as CSV ({str(e).splitlines()[0]})")
    return raw, problems


def check_columns(raw, config):
    problems = []
    for kind, df in raw.items():
        for key in NEEDED[kind]:
            col = config["columns"][key]
            if col not in df.columns:
                problems.append(f"{path_of(config, kind)}: column \"{col}\" (columns.{key}) not found; "
                                f"the file has: {', '.join(map(str, df.columns))}")
    return problems


def check_tables(tables, names=None):
    """tables: mapped tables (internal column names). names: kind -> file name used in the messages."""
    names = names or {k: k for k in KINDS}
    problems = [f"{names[k]}: the table has no rows" for k in ("events", "objects", "relations") if tables[k].empty]
    ev, rel, o2o = tables["events"], tables["relations"], tables["o2o"]
    dup = ev["_record_id"][ev["_record_id"].duplicated()]
    if len(dup):
        problems.append(f"{names['events']}: {len(dup)} duplicate event IDs (e.g. {_eg(dup)})")
    blank = ev["_timestamp"].isna() | (ev["_timestamp"].astype(str).str.strip() == "")
    if blank.any():
        problems.append(f"{names['events']}: {int(blank.sum())} events have no timestamp "
                        f"(e.g. {_eg(ev['_record_id'][blank])})")
    parsed = pd.to_datetime(ev["_timestamp"].where(~blank), utc=True, format="mixed", errors="coerce")
    bad = parsed.isna() & ~blank
    if bad.any():
        problems.append(f"{names['events']}: {int(bad.sum())} timestamps cannot be read as dates "
                        f"(e.g. {_eg(ev['_timestamp'][bad])})")
    events, objects = set(ev["_record_id"]), set(tables["objects"]["_item_id"])
    for table, col, known, what in ((rel, "_record_id", events, "events"), (rel, "_item_id", objects, "objects"),
                                    (o2o, "_item_id", objects, "objects"), (o2o, "_linked_item_id", objects, "objects")):
        unknown = table[col][~table[col].isin(known)]
        if len(unknown):
            kind = "relations" if table is rel else "o2o"
            side = {"_linked_item_id": " (target)", "_item_id": " (source)" if kind == "o2o" else ""}.get(col, "")
            problems.append(f"{names[kind]}: {len(unknown)} links point to {what} that do not exist{side} "
                            f"(e.g. {_eg(unknown)})")
    return problems


def parse_settings(settings):
    """Returns ({"identity": IdentitySettings | None, ...}, problems). Unknown sections and keys are named;
    a value must have the type of the setting's default (a whole number is accepted for a decimal setting)."""
    out, problems = {k: None for k in SETTINGS}, []
    if not isinstance(settings, dict):
        return out, ["config key \"settings\" must be an object with the sections: " + ", ".join(SETTINGS)]
    for section, values in settings.items():
        cls = SETTINGS.get(section)
        if cls is None:
            problems.append(f"config key \"settings.{section}\" is not known (expected: {', '.join(SETTINGS)})")
            continue
        fields = {f.name: f for f in dataclasses.fields(cls)}
        kept = {}
        for key, value in (values or {}).items():
            if key not in fields:
                problems.append(f"config key \"settings.{section}.{key}\" is not known "
                                f"(expected: {', '.join(fields)})")
                continue
            default = fields[key].default
            ok = (isinstance(value, (int, float)) and not isinstance(value, bool)) if isinstance(default, float) \
                else (isinstance(value, int) and not isinstance(value, bool))
            if not ok:
                kind = "a number" if isinstance(default, float) else "a whole number"
                problems.append(f"config key \"settings.{section}.{key}\" must be {kind}, not {value!r}")
                continue
            kept[key] = float(value) if isinstance(default, float) else value
        out[section] = cls(**kept)
    return out, problems
