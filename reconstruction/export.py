"""OCEL 2.0 export (stage 11): writes the toolkit's output as an OCEL 2.0 log with pm4py and reads it back.

pm4py's SQLite writer creates the OCEL 2.0 tables without declaring any primary or foreign keys. The OCEL 2.0
relational specification requires them, so add_keys() rebuilds each table with its keys declared and with
SQLite enforcing them: a duplicate link, or a link to an event or object that does not exist, makes it fail.

pm4py's writers also silently drop links that point to an unknown event or object (in every format), so
write() checks the references itself first and refuses to write instead of losing links.

Formats are named without a leading dot ("sqlite", "xml", "json"); the caller chooses the file path.
"""
import os
import sqlite3

import pandas as pd
import pm4py
from pm4py.objects.ocel.obj import OCEL

FORMATS = ("sqlite", "xml", "json")
_TO_OCEL = {"_record_id": "ocel:eid", "_activity": "ocel:activity", "_timestamp": "ocel:timestamp",
            "_item_id": "ocel:oid", "_item_type": "ocel:type", "_role": "ocel:qualifier"}
_O2O = {"_item_id": "ocel:oid", "_linked_item_id": "ocel:oid_2", "_link_type": "ocel:qualifier"}


def to_ocel(tables):
    """Toolkit tables (internal column names) -> pm4py OCEL object."""
    events = tables["events"].rename(columns=_TO_OCEL)
    events["ocel:timestamp"] = pd.to_datetime(events["ocel:timestamp"], utc=True, format="mixed")
    objects = tables["objects"].rename(columns=_TO_OCEL)
    relations = tables["relations"][["_record_id", "_item_id", "_role"]].rename(columns=_TO_OCEL)
    relations = relations.merge(events[["ocel:eid", "ocel:activity", "ocel:timestamp"]], on="ocel:eid", how="left")
    relations = relations.merge(objects[["ocel:oid", "ocel:type"]], on="ocel:oid", how="left")
    o2o = tables["o2o"][list(_O2O)].rename(columns=_O2O)
    return OCEL(events=events, objects=objects, relations=relations, o2o=o2o)


def from_ocel(ocel):
    """pm4py OCEL object -> toolkit tables (internal column names)."""
    back = {v: k for k, v in _TO_OCEL.items()}
    events = ocel.events.rename(columns=back)
    objects = ocel.objects.rename(columns=back)
    relations = ocel.relations[["ocel:eid", "ocel:oid", "ocel:type", "ocel:qualifier"]].rename(columns=back)
    o2o = ocel.o2o[list(_O2O.values())].rename(columns={v: k for k, v in _O2O.items()})
    return {"events": events, "objects": objects, "relations": relations, "o2o": o2o}


_WRITERS = {"sqlite": pm4py.write_ocel2_sqlite, "xml": pm4py.write_ocel2_xml, "json": pm4py.write_ocel2_json}
_READERS = {"sqlite": pm4py.read_ocel2_sqlite, "xml": pm4py.read_ocel2_xml, "json": pm4py.read_ocel2_json}


def check_references(tables):
    """Raise ValueError if any link points to an event or object that is not in the log."""
    events, objects = set(tables["events"]["_record_id"]), set(tables["objects"]["_item_id"])
    problems = {"E2O links to unknown events": int((~tables["relations"]["_record_id"].isin(events)).sum()),
                "E2O links to unknown objects": int((~tables["relations"]["_item_id"].isin(objects)).sum()),
                "O2O links from unknown objects": int((~tables["o2o"]["_item_id"].isin(objects)).sum()),
                "O2O links to unknown objects": int((~tables["o2o"]["_linked_item_id"].isin(objects)).sum())}
    found = {k: v for k, v in problems.items() if v}
    if found:
        raise ValueError(f"refusing to export, links would be lost: {found}")


def write(tables, path, fmt, keys=True):
    """Write the toolkit output as OCEL 2.0. For SQLite, the specification's keys are added (keys=True)."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; use one of {FORMATS}")
    check_references(tables)
    if os.path.exists(path):
        os.remove(path)
    _WRITERS[fmt](to_ocel(tables), path)
    if fmt == "sqlite" and keys:
        add_keys(path)
    return path


def read(path, fmt):
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; use one of {FORMATS}")
    return from_ocel(_READERS[fmt](path))


def add_keys(path):
    """Rebuild every OCEL 2.0 table of a pm4py-written SQLite file with its primary and foreign keys declared.
    SQLite enforces them while the rows are copied, so duplicates or dangling references raise
    sqlite3.IntegrityError. Returns the number of foreign-key violations found afterwards (always 0 on success)."""
    con = sqlite3.connect(path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        cur = con.cursor()
        event_maps = [r[0] for r in cur.execute("SELECT ocel_type_map FROM event_map_type")]
        object_maps = [r[0] for r in cur.execute("SELECT ocel_type_map FROM object_map_type")]
        plan = [("event_map_type", ["ocel_type"], []),
                ("object_map_type", ["ocel_type"], []),
                ("event", ["ocel_id"], [("ocel_type", "event_map_type", "ocel_type")]),
                ("object", ["ocel_id"], [("ocel_type", "object_map_type", "ocel_type")]),
                ("event_object", ["ocel_event_id", "ocel_object_id", "ocel_qualifier"],
                 [("ocel_event_id", "event", "ocel_id"), ("ocel_object_id", "object", "ocel_id")]),
                ("object_object", ["ocel_source_id", "ocel_target_id", "ocel_qualifier"],
                 [("ocel_source_id", "object", "ocel_id"), ("ocel_target_id", "object", "ocel_id")])]
        plan += [(f"event_{m}", ["ocel_id"], [("ocel_id", "event", "ocel_id")]) for m in event_maps]
        # Object type tables may hold several rows per object (attribute changes over time): foreign key only
        plan += [(f"object_{m}", [], [("ocel_id", "object", "ocel_id")]) for m in object_maps]
        for table, pk, fks in plan:
            cols = [(r[1], r[2]) for r in cur.execute(f'PRAGMA table_info("{table}")')]
            defs = [f'"{c}" {t}' for c, t in cols]
            if pk:
                defs.append("PRIMARY KEY (" + ", ".join(f'"{c}"' for c in pk) + ")")
            defs += [f'FOREIGN KEY ("{a}") REFERENCES "{t}" ("{b}")' for a, t, b in fks]
            names = ", ".join(f'"{c}"' for c, _ in cols)
            cur.execute(f'ALTER TABLE "{table}" RENAME TO "{table}__unkeyed"')
            cur.execute(f'CREATE TABLE "{table}" ({", ".join(defs)})')
            cur.execute(f'INSERT INTO "{table}" ({names}) SELECT {names} FROM "{table}__unkeyed"')
            cur.execute(f'DROP TABLE "{table}__unkeyed"')
        con.commit()
        violations = cur.execute("PRAGMA foreign_key_check").fetchall()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    if violations:
        raise sqlite3.IntegrityError(f"{len(violations)} foreign-key violations after adding keys")
    return 0
