from dataclasses import dataclass

@dataclass
class SchemaMapping:
    record_id_col: str        # unique record/event ID
    activity_col: str         # activity name
    timestamp_col: str        # event time
    item_id_col: str          # object/item ID
    item_type_col: str        # object type
    linked_item_id_col: str   # the other item in an item-to-item link
    link_type_col: str        # kind of item-to-item link
    role_col: str             # role an item plays in a record


def apply_mapping(df, mapping: SchemaMapping, kind: str):
    if kind == "events":
        rename_map = {mapping.record_id_col: "_record_id",
                      mapping.activity_col: "_activity",
                      mapping.timestamp_col: "_timestamp"}
    elif kind == "objects":
        rename_map = {mapping.item_id_col: "_item_id",
                      mapping.item_type_col: "_item_type"}
    elif kind == "relations":
        rename_map = {mapping.record_id_col: "_record_id",
                      mapping.item_id_col: "_item_id",
                      mapping.item_type_col: "_item_type",
                      mapping.role_col: "_role"}
    elif kind == "o2o":
        rename_map = {mapping.item_id_col: "_item_id",
                      mapping.linked_item_id_col: "_linked_item_id",
                      mapping.link_type_col: "_link_type"}
    else:
        raise ValueError(f"Unknown data kind: '{kind}'")

    missing = [c for c in rename_map if c not in df.columns]
    if missing:
        raise ValueError(f"Mapping error: columns not found in data: {missing}")

    return df.rename(columns=rename_map)