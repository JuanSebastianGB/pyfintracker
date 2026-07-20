"""Unit tests for Budget repository logic — period boundaries and spending.

Tests ``get_budget_spending`` with various period scenarios using
an in-memory SQLite database with migrations applied.
"""

from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.fixture(scope="function")
def budget_connection() -> object:
    """Create an in-memory connection with full schema."""
    import alembic.command
    import alembic.config

    from pyfintracker.db import make_test_engine

    engine = make_test_engine()
    conn = engine.connect()
    alembic_cfg = alembic.config.Config("alembic.ini")
    alembic_cfg.attributes["connection"] = conn
    alembic.command.upgrade(alembic_cfg, "head")
    yield conn
    conn.close()


def _seed_accounts(conn: object) -> dict[str, int]:
    """Insert test accounts and return id mapping.

    Uses names guaranteed to NOT conflict with starter chart accounts
    (Expenses:Transport, Expenses:Food:Groceries, etc. are seeded by 0001).
    """
    from sqlalchemy import text

    ids: dict[str, int] = {}
    for name in ("Expenses:FoodDelivery", "Expenses:RideShare", "Income:Bonus"):
        row = conn.execute(
            text(
                "INSERT INTO accounts (name, currency, depth, kind) "
                "VALUES (:name, 'COP', 1, :kind) RETURNING id"
            ),
            {"name": name, "kind": name.split(":")[0]},
        ).fetchone()
        assert row is not None
        ids[name] = row[0]
    return ids


def _seed_transaction(conn: object, txn_date: str, account_id: int, amount: str) -> int:
    """Insert a transaction with one posting. Returns the transaction id."""
    from sqlalchemy import text

    row = conn.execute(
        text("INSERT INTO transactions (date, description) VALUES (:d, :desc) RETURNING id"),
        {"d": txn_date, "desc": "test"},
    ).fetchone()
    assert row is not None
    txn_id = row[0]
    conn.execute(
        text(
            "INSERT INTO postings (transaction_id, account_id, amount, currency) "
            "VALUES (:tid, :aid, :amt, 'COP')"
        ),
        {"tid": txn_id, "aid": account_id, "amt": amount},
    )
    return txn_id


def _seed_tag(conn: object, name: str = "food") -> int:
    """Create a tag and return its id."""
    from sqlalchemy import text

    row = conn.execute(
        text("INSERT INTO tags (name) VALUES (:n) RETURNING id"),
        {"n": name},
    ).fetchone()
    assert row is not None
    return row[0]


def _tag_txn(conn: object, txn_id: int, tag_id: int) -> None:
    """Attach a tag to a transaction."""
    from sqlalchemy import text

    conn.execute(
        text("INSERT OR IGNORE INTO transaction_tags (transaction_id, tag_id) VALUES (:tid, :tg)"),
        {"tid": txn_id, "tg": tag_id},
    )


# ── Monthly period tests ──────────────────────────────────────────────────


def test_budget_spending_monthly_match(budget_connection: object) -> None:
    """Monthly budget includes postings in the same YYYY-MM."""
    from pyfintracker.models import Budget
    from pyfintracker.repository import create_budget, get_budget_spending

    conn: object = budget_connection
    accounts = _seed_accounts(conn)
    _seed_transaction(conn, "2026-07-15", accounts["Expenses:FoodDelivery"], "50000")

    budget = create_budget(
        conn,
        Budget(
            name="Food Jul",
            amount=Decimal("200000"),
            period="monthly",
            account_id=accounts["Expenses:FoodDelivery"],
            start_date="2026-07-01",
        ),
    )
    spent = get_budget_spending(conn, budget, "2026-07-20")
    assert spent == Decimal("50000"), f"Expected 50000, got {spent}"


def test_budget_spending_monthly_excludes_other_month(budget_connection: object) -> None:
    """Monthly budget only counts postings from the same month."""
    from pyfintracker.models import Budget
    from pyfintracker.repository import create_budget, get_budget_spending

    conn: object = budget_connection
    accounts = _seed_accounts(conn)
    _seed_transaction(conn, "2026-06-15", accounts["Expenses:FoodDelivery"], "50000")
    _seed_transaction(conn, "2026-07-15", accounts["Expenses:FoodDelivery"], "30000")

    budget = create_budget(
        conn,
        Budget(
            name="Food Jul",
            amount=Decimal("200000"),
            period="monthly",
            account_id=accounts["Expenses:FoodDelivery"],
            start_date="2026-07-01",
        ),
    )
    spent = get_budget_spending(conn, budget, "2026-07-20")
    assert spent == Decimal("30000"), f"Expected 30000, got {spent}"


def test_budget_spending_abs_value(budget_connection: object) -> None:
    """Spending sums absolute values of postings."""
    from pyfintracker.models import Budget
    from pyfintracker.repository import create_budget, get_budget_spending

    conn: object = budget_connection
    accounts = _seed_accounts(conn)
    # negative amount posting
    _seed_transaction(conn, "2026-07-10", accounts["Expenses:FoodDelivery"], "-50000")
    _seed_transaction(conn, "2026-07-15", accounts["Expenses:FoodDelivery"], "30000")

    budget = create_budget(
        conn,
        Budget(
            name="Food Jul",
            amount=Decimal("200000"),
            period="monthly",
            account_id=accounts["Expenses:FoodDelivery"],
            start_date="2026-07-01",
        ),
    )
    spent = get_budget_spending(conn, budget, "2026-07-20")
    assert spent == Decimal("80000"), f"Expected 80000, got {spent}"


# ── Yearly period tests ───────────────────────────────────────────────────


def test_budget_spending_yearly(budget_connection: object) -> None:
    """Yearly budget includes all postings from the same year."""
    from pyfintracker.models import Budget
    from pyfintracker.repository import create_budget, get_budget_spending

    conn: object = budget_connection
    accounts = _seed_accounts(conn)
    _seed_transaction(conn, "2026-01-15", accounts["Expenses:FoodDelivery"], "100000")
    _seed_transaction(conn, "2026-07-15", accounts["Expenses:FoodDelivery"], "50000")

    budget = create_budget(
        conn,
        Budget(
            name="Food 2026",
            amount=Decimal("500000"),
            period="yearly",
            account_id=accounts["Expenses:FoodDelivery"],
            start_date="2026-01-01",
        ),
    )
    spent = get_budget_spending(conn, budget, "2026-07-20")
    assert spent == Decimal("150000"), f"Expected 150000, got {spent}"


def test_budget_spending_yearly_excludes_other_year(budget_connection: object) -> None:
    """Yearly budget excludes postings from other years."""
    from pyfintracker.models import Budget
    from pyfintracker.repository import create_budget, get_budget_spending

    conn: object = budget_connection
    accounts = _seed_accounts(conn)
    _seed_transaction(conn, "2025-12-31", accounts["Expenses:FoodDelivery"], "999999")
    _seed_transaction(conn, "2026-01-01", accounts["Expenses:FoodDelivery"], "50000")

    budget = create_budget(
        conn,
        Budget(
            name="Food 2026",
            amount=Decimal("500000"),
            period="yearly",
            account_id=accounts["Expenses:FoodDelivery"],
            start_date="2026-01-01",
        ),
    )
    spent = get_budget_spending(conn, budget, "2026-07-20")
    assert spent == Decimal("50000"), f"Expected 50000, got {spent}"


# ── Tag-scoped budget tests ───────────────────────────────────────────────


def test_budget_spending_tag_scope(budget_connection: object) -> None:
    """Budget with tag_id only counts tagged transactions."""
    from pyfintracker.models import Budget
    from pyfintracker.repository import create_budget, get_budget_spending

    conn: object = budget_connection
    accounts = _seed_accounts(conn)
    tag_id = _seed_tag(conn, "food")

    txn1 = _seed_transaction(conn, "2026-07-10", accounts["Expenses:FoodDelivery"], "50000")
    _seed_transaction(conn, "2026-07-15", accounts["Expenses:FoodDelivery"], "30000")
    _tag_txn(conn, txn1, tag_id)
    # second txn is NOT tagged

    budget = create_budget(
        conn,
        Budget(
            name="Tagged Food",
            amount=Decimal("200000"),
            period="monthly",
            tag_id=tag_id,
            start_date="2026-07-01",
        ),
    )
    spent = get_budget_spending(conn, budget, "2026-07-20")
    assert spent == Decimal("50000"), f"Expected 50000 (only tagged), got {spent}"


# ── All-accounts budget tests ─────────────────────────────────────────────


def test_budget_spending_all_accounts(budget_connection: object) -> None:
    """Budget with no account_id counts spending across all accounts."""
    from pyfintracker.models import Budget
    from pyfintracker.repository import create_budget, get_budget_spending

    conn: object = budget_connection
    accounts = _seed_accounts(conn)
    _seed_transaction(conn, "2026-07-10", accounts["Expenses:FoodDelivery"], "50000")
    _seed_transaction(conn, "2026-07-15", accounts["Expenses:RideShare"], "30000")

    budget = create_budget(
        conn,
        Budget(
            name="Total Jul",
            amount=Decimal("200000"),
            period="monthly",
            start_date="2026-07-01",
        ),
    )
    spent = get_budget_spending(conn, budget, "2026-07-20")
    assert spent == Decimal("80000"), f"Expected 80000, got {spent}"


def test_budget_spending_empty(budget_connection: object) -> None:
    """Budget with no matching postings returns zero."""
    from pyfintracker.models import Budget
    from pyfintracker.repository import create_budget, get_budget_spending

    conn: object = budget_connection
    accounts = _seed_accounts(conn)
    _seed_transaction(conn, "2026-08-10", accounts["Expenses:FoodDelivery"], "50000")

    budget = create_budget(
        conn,
        Budget(
            name="Empty Jul",
            amount=Decimal("200000"),
            period="monthly",
            account_id=accounts["Expenses:FoodDelivery"],
            start_date="2026-07-01",
        ),
    )
    spent = get_budget_spending(conn, budget, "2026-07-20")
    assert spent == Decimal("0"), f"Expected 0, got {spent}"
