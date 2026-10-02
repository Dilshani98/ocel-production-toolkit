from dataclasses import dataclass

@dataclass
class SchemaMapping:
    #For the toolkit to get input as which column in the raw source files
    record_id_col: str      # which column is the unique record/event ID
    activity_col: str       # which column is the activity name
    timestamp_col: str      # which column is the event time
    item_id_col: str        # which column is the object/item ID
    item_type_col: str      # which column is the object type


def apply_mapping(df, mapping: SchemaMapping, kind: str):
    #Renames the columns the user specified into a single consistent internal naming scheme
    rename_map = {}
    if kind == "events":
        rename_map = {mapping.record_id_col: "_record_id",
                      mapping.activity_col: "_activity",
                      mapping.timestamp_col: "_timestamp"}
    elif kind == "objects":
        rename_map = {mapping.item_id_col: "_item_id",
                      mapping.item_type_col: "_item_type"}
    elif kind == "relations":
        rename_map = {mapping.record_id_col: "_record_id",
                      mapping.item_id_col: "_item_id"}

    missing = [c for c in rename_map if c not in df.columns]
    if missing:
        raise ValueError(f"Mapping error: columns not found in data: {missing}")

    return df.rename(columns=rename_map)