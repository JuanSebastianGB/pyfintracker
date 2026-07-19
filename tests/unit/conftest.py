"""Shared fixtures for the split report test files.

Exposes:
- ``reports_engine`` — in-memory SQLite with accounts/transactions/postings tables.
- ``seed_simple_month`` — 3 single-currency (COP) transactions.
- ``reports_engine_with_rates`` — extends ``reports_engine`` with the rates table.
- ``seed_mixed_month`` — COP + USD postings with FX rates seeded.
"""

from __future__ import annotations

from datetime import UTC, date
from decimal import Decimal

import pytest
from sqlalchemy import text

from pyfintracker.db import get_session, make_test_engine
from pyfintracker.models import Posting, Transaction


@pytest.fixture
def reports_engine():
    """In-memory engine with accounts, transactions, postings tables."""
    eng = make_test_engine()
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    currency TEXT NOT NULL DEFAULT 'COP',
                    depth INTEGER NOT NULL DEFAULT 0,
                    kind TEXT NOT NULL,
                    is_archived INTEGER NOT NULL DEFAULT 0
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT ''
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE postings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id INTEGER NOT NULL REFERENCES transactions(id),
                    account_id INTEGER NOT NULL REFERENCES accounts(id),
                    amount TEXT NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'COP'
                )
                """
            )
        )
    yield eng
    eng.dispose()


@pytest.fixture
def seed_simple_month(reports_engine):
    """Seed data for a simple month: income + expense transaction.

    Returns a dict mapping account names to their IDs.
    """
    with reports_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Checking', 'COP', 1, 'Assets')"
            ),
        )
        conn.execute(
            text(
                "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Income:Salary', 'COP', 1, 'Income')"
            ),
        )
        conn.execute(
            text(
                "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Expenses:Rent', 'COP', 1, 'Expenses')"
            ),
        )
        conn.execute(
            text(
                "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Expenses:Food:Groceries', 'COP', 2, 'Expenses')"
            ),
        )
        rows = conn.execute(text("SELECT id, name FROM accounts ORDER BY id")).fetchall()
    accounts = {r.name: r.id for r in rows}

    from pyfintracker.repository import create_transaction_with_postings

    txn1 = Transaction(date=date(2024, 1, 3), description="Rent payment")
    postings1 = [
        Posting(account_id=accounts["Expenses:Rent"], amount=Decimal("1200000"), currency="COP"),
        Posting(account_id=accounts["Assets:Checking"], amount=Decimal("-1200000"), currency="COP"),
    ]
    with get_session(reports_engine) as conn:
        create_transaction_with_postings(conn, txn1, postings1)

    txn2 = Transaction(date=date(2024, 1, 15), description="Salary")
    postings2 = [
        Posting(account_id=accounts["Income:Salary"], amount=Decimal("-3000000"), currency="COP"),
        Posting(account_id=accounts["Assets:Checking"], amount=Decimal("3000000"), currency="COP"),
    ]
    with get_session(reports_engine) as conn:
        create_transaction_with_postings(conn, txn2, postings2)

    txn3 = Transaction(date=date(2024, 1, 20), description="Groceries")
    postings3 = [
        Posting(
            account_id=accounts["Expenses:Food:Groceries"], amount=Decimal("250000"), currency="COP"
        ),
        Posting(account_id=accounts["Assets:Checking"], amount=Decimal("-250000"), currency="COP"),
    ]
    with get_session(reports_engine) as conn:
        create_transaction_with_postings(conn, txn3, postings3)

    return accounts


@pytest.fixture
def reports_engine_with_rates(reports_engine):
    """Extends reports_engine with a rates table."""
    from datetime import datetime

    eng = reports_engine
    with eng.begin() as conn:
        conn.execute(
            text("""
                CREATE TABLE IF NOT EXISTS rates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    base_currency TEXT NOT NULL,
                    target_currency TEXT NOT NULL,
                    rate TEXT NOT NULL,
                    date TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'frankfurter',
                    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(base_currency, target_currency, date)
                )
            """)
        )
        conn.execute(
            text("""
                INSERT OR IGNORE INTO rates (base_currency, target_currency, rate, date, source, fetched_at)
                VALUES ('COP', 'USD', '0.00025', '2026-07-05', 'frankfurter', :now)
            """),
            {"now": datetime.now(UTC).isoformat()},
        )
        conn.execute(
            text("""
                INSERT OR IGNORE INTO rates (base_currency, target_currency, rate, date, source, fetched_at)
                VALUES ('COP', 'USD', '0.000238', '2026-07-10', 'frankfurter', :now)
            """),
            {"now": datetime.now(UTC).isoformat()},
        )
        conn.execute(
            text("""
                INSERT OR IGNORE INTO rates (base_currency, target_currency, rate, date, source, fetched_at)
                VALUES ('USD', 'COP', '4200', '2026-07-10', 'frankfurter', :now)
            """),
            {"now": datetime.now(UTC).isoformat()},
        )
        conn.execute(
            text("""
                INSERT OR IGNORE INTO rates (base_currency, target_currency, rate, date, source, fetched_at)
                VALUES ('USD', 'COP', '4000', '2026-07-05', 'frankfurter', :now)
            """),
            {"now": datetime.now(UTC).isoformat()},
        )
    yield eng


@pytest.fixture
def seed_mixed_month(reports_engine_with_rates):
    """Seed data with mixed COP + USD postings in 2026-07.

    Returns the engine for test use.
    """
    eng = reports_engine_with_rates
    with eng.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Checking', 'COP', 1, 'Assets')"
            ),
        )
        conn.execute(
            text(
                "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:UsdAccount', 'USD', 1, 'Assets')"
            ),
        )
        conn.execute(
            text(
                "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Income:Salary', 'COP', 1, 'Income')"
            ),
        )
        conn.execute(
            text(
                "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Income:Freelance', 'USD', 1, 'Income')"
            ),
        )
        conn.execute(
            text(
                "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Expenses:Rent', 'COP', 1, 'Expenses')"
            ),
        )
        rows = conn.execute(text("SELECT id, name FROM accounts ORDER BY id")).fetchall()
    accounts = {r.name: r.id for r in rows}

    from pyfintracker.repository import create_transaction_with_postings

    txn1 = Transaction(date=date(2026, 7, 5), description="Salary")
    postings1 = [
        Posting(account_id=accounts["Income:Salary"], amount=Decimal("-50000"), currency="COP"),
        Posting(account_id=accounts["Assets:Checking"], amount=Decimal("50000"), currency="COP"),
    ]
    with get_session(eng) as conn:
        create_transaction_with_postings(conn, txn1, postings1)

    txn2 = Transaction(date=date(2026, 7, 10), description="Freelance payment")
    postings2 = [
        Posting(account_id=accounts["Income:Freelance"], amount=Decimal("-15"), currency="USD"),
        Posting(account_id=accounts["Assets:UsdAccount"], amount=Decimal("15"), currency="USD"),
    ]
    with get_session(eng) as conn:
        create_transaction_with_postings(conn, txn2, postings2)

    txn3 = Transaction(date=date(2026, 7, 10), description="Rent")
    postings3 = [
        Posting(account_id=accounts["Expenses:Rent"], amount=Decimal("1200"), currency="COP"),
        Posting(account_id=accounts["Assets:Checking"], amount=Decimal("-1200"), currency="COP"),
    ]
    with get_session(eng) as conn:
        create_transaction_with_postings(conn, txn3, postings3)

    return eng
