"""OCEL 2.0 export (stage 11): writes the toolkit's output as an OCEL 2.0 log with pm4py and reads it back.

pm4py's SQLite writer creates the OCEL 2.0 tables without declaring any primary or foreign keys. The OCEL 2.0
relational specification requires them, so add_keys() rebuilds each table with its keys declared and with
SQLite enforcing them: a duplicate link, or a link to an event or object that does not exist, makes it fail.

pm4py's writers also silently drop links that point to an unknown event or object (in every format), so
write() checks the references itself first and refuses to write instead of losing links.

pm4py's writers keep only objects that appear in an event-to-object link, so objects with no links at all are
dropped, although OCEL 2.0 allows objects without events. Amendment 26 Oct: write() adds such objects back
after pm4py has written the file, in pm4py's own structure for each format (restore_isolated_objects()).

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
    restore_isolated_objects(tables, path, fmt)
    if fmt == "sqlite" and keys:
        add_keys(path)
    return path


_INITIAL_TIME = "1970-01-01T00:00:00Z"      # pm4py's time for an object's initial attribute values


def _attributes(row):
    return {k: v for k, v in row.items() if k not in ("_item_id", "_item_type") and not pd.isna(v)}


def _typed(value, declared):
    """Attribute value as pm4py writes it in JSON: numbers for float/integer attributes, text otherwise."""
    if declared == "float":
        return float(value)
    if declared == "integer":
        return int(value)
    return str(value)


def restore_isolated_objects(tables, path, fmt):
    """Add back the objects pm4py did not write (objects with no event-to-object link). Returns how many.
    Refuses if such an object's type is not declared in the file, instead of inventing a declaration."""
    objects = tables["objects"].drop_duplicates("_item_id")
    if fmt == "sqlite":
        con = sqlite3.connect(path)
        try:
            cur = con.cursor()
            written = {r[0] for r in cur.execute("SELECT ocel_id FROM object")}
            missing = objects[~objects["_item_id"].isin(written)]
            type_map = dict(cur.execute("SELECT ocel_type, ocel_type_map FROM object_map_type").fetchall())
            for _, row in missing.iterrows():
                t = row["_item_type"]
                if t not in type_map:
                    raise ValueError(f"object {row['_item_id']!r} has type {t!r}, which no written object has")
                table = f"object_{type_map[t]}"
                attrs = _attributes(row)
                cols = {r[1] for r in cur.execute(f'PRAGMA table_info("{table}")')}
                for name in attrs.keys() - cols:
                    cur.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" TEXT')
                cur.execute("INSERT INTO object (ocel_id, ocel_type) VALUES (?, ?)", (row["_item_id"], t))
                names = ["ocel_id"] + list(attrs)
                cur.execute(f'INSERT INTO "{table}" ({", ".join(chr(34) + n + chr(34) for n in names)}) '
                            f'VALUES ({", ".join("?" for _ in names)})',
                            [row["_item_id"]] + [v if isinstance(v, (int, float)) else str(v) for v in attrs.values()])
            con.commit()
        finally:
            con.close()
        return int(len(missing))
    if fmt == "json":
        import json
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        written = {o["id"] for o in doc["objects"]}
        missing = objects[~objects["_item_id"].isin(written)]
        types = {t["name"]: t for t in doc["objectTypes"]}
        for _, row in missing.iterrows():
            t = row["_item_type"]
            if t not in types:
                raise ValueError(f"object {row['_item_id']!r} has type {t!r}, which no written object has")
            declared = {a["name"]: a["type"] for a in types[t]["attributes"]}
            attrs = _attributes(row)
            for name in attrs.keys() - declared.keys():
                types[t]["attributes"].append({"name": name, "type": "string"})
                declared[name] = "string"
            doc["objects"].append({"id": row["_item_id"], "type": t,
                                   "attributes": [{"name": n, "time": _INITIAL_TIME, "value": _typed(v, declared[n])}
                                                  for n, v in attrs.items()]})
        if len(missing):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2)
        return int(len(missing))
    if fmt == "xml":
        from lxml import etree
        tree = etree.parse(path)
        root = tree.getroot()
        top_objects = root.find("objects")
        written = {o.get("id") for o in top_objects.findall("object")}
        missing = objects[~objects["_item_id"].isin(written)]
        types = {t.get("name"): t for t in root.find("object-types").findall("object-type")}
        for _, row in missing.iterrows():
            t = row["_item_type"]
            if t not in types:
                raise ValueError(f"object {row['_item_id']!r} has type {t!r}, which no written object has")
            decl = types[t].find("attributes")
            if decl is None:
                decl = etree.SubElement(types[t], "attributes")
            declared = {a.get("name") for a in decl.findall("attribute")}
            attrs = _attributes(row)
            for name in attrs.keys() - declared:
                etree.SubElement(decl, "attribute", name=name, type="string")
            obj = etree.SubElement(top_objects, "object", id=row["_item_id"], type=t)
            holder = etree.SubElement(obj, "attributes")
            for n, v in attrs.items():
                etree.SubElement(holder, "attribute", name=n, time=_INITIAL_TIME).text = str(v)
        if len(missing):
            etree.indent(tree, space="  ")
            tree.write(path, xml_declaration=True, encoding="UTF-8")
        return int(len(missing))
    raise ValueError(f"unknown format {fmt!r}; use one of {FORMATS}")


def read(path, fmt):
    """Read an OCEL 2.0 file with pm4py. pm4py's readers also drop objects with no event-to-object link
    (amendment 26 Oct), so those objects are read straight from the file and added back."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; use one of {FORMATS}")
    tables = from_ocel(_READERS[fmt](path))
    in_file = file_objects(path, fmt)
    missing = in_file[~in_file["_item_id"].isin(set(tables["objects"]["_item_id"]))]
    if len(missing):
        tables["objects"] = pd.concat([tables["objects"], missing], ignore_index=True)
    return tables


def file_objects(path, fmt):
    """Every object stored in an OCEL 2.0 file (id, type, initial attributes), read directly, without pm4py."""
    rows = []
    if fmt == "sqlite":
        con = sqlite3.connect(path)
        try:
            for t, m in con.execute("SELECT ocel_type, ocel_type_map FROM object_map_type").fetchall():
                df = pd.read_sql_query(f'SELECT * FROM "object_{m}"', con)
                df = df.drop(columns=[c for c in ("ocel_time", "ocel_changed_field") if c in df.columns])
                df = df.drop_duplicates("ocel_id").rename(columns={"ocel_id": "_item_id"}).assign(_item_type=t)
                rows.append(df)
            ids = pd.read_sql_query("SELECT ocel_id AS _item_id, ocel_type AS _item_type FROM object", con)
        finally:
            con.close()
        typed = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["_item_id", "_item_type"])
        return ids.merge(typed.drop(columns=["_item_type"]), on="_item_id", how="left")
    if fmt == "json":
        import json
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        for o in doc["objects"]:
            rows.append({"_item_id": o["id"], "_item_type": o["type"],
                         **{a["name"]: a["value"] for a in o.get("attributes", [])}})
        return pd.DataFrame(rows)
    if fmt == "xml":
        from lxml import etree
        root = etree.parse(path).getroot()
        for o in root.find("objects").findall("object"):
            attrs = o.find("attributes")
            rows.append({"_item_id": o.get("id"), "_item_type": o.get("type"),
                         **({a.get("name"): a.text for a in attrs.findall("attribute")} if attrs is not None else {})})
        return pd.DataFrame(rows)
    raise ValueError(f"unknown format {fmt!r}; use one of {FORMATS}")


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
