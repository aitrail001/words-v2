from __future__ import annotations

LEXICON_SCHEMA = "lexicon"
LEXICON_TABLE_ARGS = {"schema": LEXICON_SCHEMA}


def lexicon_fk(table_name: str, column_name: str = "id") -> str:
    return f"{LEXICON_SCHEMA}.{table_name}.{column_name}"


def lexicon_table_args(*constraints):
    if constraints:
        return (*constraints, {"schema": LEXICON_SCHEMA})
    return {"schema": LEXICON_SCHEMA}
