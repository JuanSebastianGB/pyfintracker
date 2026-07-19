"""Unit tests for repository operations — T-4.6 create_transaction_with_postings.

Self-contained (no conftest fixtures). Uses SQLite :memory: with StaticPool
so state is visible across connections within the same test.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from pyfintracker.db import get_session, make_test_engine
from pyfintracker.exceptions import UnbalancedTransaction
from pyfintracker.models import Posting, Transaction


@pytest.mark.unit
class TestCreateTransaction:
    """T-4.6: repository.create_transaction_with_postings(conn, txn, postings) -> int."""

    @pytest.fixture
    def engine(self):
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
                        description TEXT NOT NULL
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
    def seed_accounts(self, engine):
        with get_session(engine) as conn:
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Cash', 'COP', 1, 'Assets')"
                ),
            )
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Expenses:Food', 'COP', 1, 'Expenses')"
                ),
            )
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Income:Salary', 'COP', 1, 'Income')"
                ),
            )
        # Read back IDs
        with engine.begin() as conn:
            rows = conn.execute(text("SELECT id, name FROM accounts ORDER BY id")).fetchall()
        return {r.name: r.id for r in rows}

    def test_create_simple_transaction(self, engine, seed_accounts):
        """Happy path: creates a transaction with two postings, returns int ID."""
        from pyfintracker.repository import create_transaction_with_postings

        txn = Transaction(date=date(2024, 1, 15), description="Grocery run")
        postings = [
            Posting(
                account_id=seed_accounts["Expenses:Food"], amount=Decimal("50000"), currency="COP"
            ),
            Posting(
                account_id=seed_accounts["Assets:Cash"], amount=Decimal("-50000"), currency="COP"
            ),
        ]
        with get_session(engine) as conn:
            txn_id = create_transaction_with_postings(conn, txn, postings)
        assert txn_id is not None
        assert isinstance(txn_id, int)
        assert txn_id > 0

    def test_creates_two_postings(self, engine, seed_accounts):
        """After creating a txn, exactly 2 postings exist in the DB."""
        from pyfintracker.repository import create_transaction_with_postings

        txn = Transaction(date=date(2024, 1, 15), description="Grocery run")
        postings = [
            Posting(
                account_id=seed_accounts["Expenses:Food"], amount=Decimal("50000"), currency="COP"
            ),
            Posting(
                account_id=seed_accounts["Assets:Cash"], amount=Decimal("-50000"), currency="COP"
            ),
        ]
        with get_session(engine) as conn:
            create_transaction_with_postings(conn, txn, postings)

        with engine.begin() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM transactions")).scalar()
            assert count == 1
            count = conn.execute(text("SELECT COUNT(*) FROM postings")).scalar()
            assert count == 2

    def test_rollback_on_validation_failure(self, engine, seed_accounts):
        """Unbalanced transaction should not leave partial data."""
        from pyfintracker.repository import create_transaction_with_postings

        txn = Transaction(date=date(2024, 1, 15), description="Bad txn")
        postings = [
            Posting(
                account_id=seed_accounts["Expenses:Food"], amount=Decimal("50000"), currency="COP"
            ),
            Posting(
                account_id=seed_accounts["Assets:Cash"], amount=Decimal("-30000"), currency="COP"
            ),
        ]
        with pytest.raises(UnbalancedTransaction), get_session(engine) as conn:
            create_transaction_with_postings(conn, txn, postings)

        # Verify no transaction was saved (new session, same in-memory DB via StaticPool)
        with engine.begin() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM transactions")).scalar()
            assert count == 0
            count = conn.execute(text("SELECT COUNT(*) FROM postings")).scalar()
            assert count == 0
