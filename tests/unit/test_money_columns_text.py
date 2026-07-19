"""Verify money columns are stored as TEXT in SQLite schema.

Reads the initial migration to ensure all money-related columns
are declared as TEXT to preserve Decimal precision.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).parents[2] / "migrations" / "versions" / "0001_initial_schema.py"
)

# (table, column) pairs that must be TEXT
MONEY_COLUMNS: list[tuple[str, str]] = [
    ("accounts", "currency"),
    ("postings", "amount"),
    ("postings", "currency"),
    ("rates", "rate"),
    ("rates", "base_currency"),
    ("rates", "target_currency"),
]


def _extract_sql_text(tree: ast.AST) -> str:
    """Return the combined SQL string from all op.execute calls with CREATE TABLE."""
    texts: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value.strip().upper().startswith("CREATE TABLE")
        ):
            texts.append(node.args[0].value)
    return "\n\n".join(texts)


def _parse_columns(sql: str, table: str) -> dict[str, str]:
    """Return {column_name: type_affinity} for a CREATE TABLE statement."""
    # Normalise SQL: collapse multi-line column defs (split on comma, not newline)
    lines = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.upper() in ("", "CREATE", "TABLE", "IF", "NOT", "EXISTS"):
            continue
        lines.append(stripped)
    body = " ".join(lines)

    # Find the right CREATE TABLE
    import re

    m = re.search(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{re.escape(table)}\s*\((.*)\)",
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return {}

    raw_cols = m.group(1)
    cols: dict[str, str] = {}
    for part in raw_cols.split(","):
        part = part.strip()
        tokens = part.split()
        if not tokens or not tokens[0].isidentifier():
            continue
        if (
            len(tokens) < 2
            or tokens[0].upper() in ("UNIQUE", "PRIMARY", "FOREIGN", "CHECK", "CONSTRAINT")
            or tokens[0].upper().startswith("UNIQUE(")
        ):
            continue
        col_name = tokens[0]
        col_type = tokens[1].upper() if len(tokens) > 1 else ""
        cols[col_name] = col_type
    return cols


@pytest.mark.unit
def test_money_columns_text() -> None:
    """All money-related columns in schema should be TEXT type."""
    migration_src = MIGRATION.read_text()
    tree = ast.parse(migration_src)
    sql_text = _extract_sql_text(tree)

    assert sql_text, "No CREATE TABLE SQL found in migration"

    for table, column in MONEY_COLUMNS:
        cols = _parse_columns(sql_text, table)
        assert column in cols, (
            f"Column '{table}.{column}' not found in migration"
        )
        assert cols[column] == "TEXT", (
            f"'{table}.{column}' is {cols[column]}, expected TEXT"
        )
