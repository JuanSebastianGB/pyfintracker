"""Integration tests for ``create_transaction_with_postings`` — T-4.13 through T-4.15.

Verifies:
- Balanced transactions are created with correct postings
- Unbalanced transactions are rejected atomically (no partial DB state)
- Currency mismatches between postings are rejected
- Too-few-postings and zero-postings are rejected
- Zero-amount postings are rejected
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import Connection, text

from pyfintracker.exceptions import (
    CurrencyMismatchError,
    TooFewPostings,
    UnbalancedTransaction,
    ZeroAmountPosting,
)
from pyfintracker.models import Posting, Transaction
from pyfintracker.repository import (
    create_transaction_with_postings,
    get_account_by_name,
)


@pytest.mark.integration
class TestRepoCreateTransaction:
    """T-4.13, T-4.14, T-4.15: ``create_transaction_with_postings`` integration.

    Note: Alembic migration creates the schema + 11 starter accounts but
    does NOT create any seed transactions.  All transaction/postings counts
    start at 0.
    """

    # ── T-4.13: unbalanced rejected ───────────────────────────────────────

    def test_balanced_creates(self, connection: Connection) -> None:
        """Two postings summing to zero creates 1 transaction + 2 postings."""
        cash = get_account_by_name(connection, "Assets:Checking")
        food = get_account_by_name(connection, "Expenses:Food:Groceries")
        assert cash is not None and cash.id is not None
        assert food is not None and food.id is not None

        txn = Transaction(date=date(2024, 1, 15), description="Groceries")
        postings = [
            Posting(account_id=food.id, amount=Decimal("85000"), currency="COP"),
            Posting(account_id=cash.id, amount=Decimal("-85000"), currency="COP"),
        ]

        txn_id = create_transaction_with_postings(connection, txn, postings)
        assert txn_id is not None
        assert isinstance(txn_id, int)
        assert txn_id > 0

        # Verify DB state
        count = connection.execute(
            text("SELECT COUNT(*) FROM transactions"),
        ).scalar()
        assert count == 1, f"Expected 1 transaction, got {count}"

        posting_count = connection.execute(
            text("SELECT COUNT(*) FROM postings"),
        ).scalar()
        assert posting_count == 2, f"Expected 2 postings, got {posting_count}"

        # Verify double-entry invariant
        rows = connection.execute(
            text("SELECT amount FROM postings WHERE transaction_id = :tid"),
            {"tid": txn_id},
        ).fetchall()
        total = sum(Decimal(r[0]) for r in rows)
        assert total == Decimal("0"), f"Postings sum to {total}, expected 0"

    def test_unbalanced_rejected(self, connection: Connection) -> None:
        """Postings that don't sum to zero raise UnbalancedTransaction."""
        cash = get_account_by_name(connection, "Assets:Checking")
        food = get_account_by_name(connection, "Expenses:Food:Groceries")
        assert cash is not None and cash.id is not None
        assert food is not None and food.id is not None

        txn = Transaction(date=date(2024, 1, 15), description="Unbalanced")
        postings = [
            Posting(account_id=cash.id, amount=Decimal("100"), currency="COP"),
            Posting(account_id=food.id, amount=Decimal("-30"), currency="COP"),
        ]

        with pytest.raises(UnbalancedTransaction):
            create_transaction_with_postings(connection, txn, postings)

        # DB should be unchanged — no partial inserts
        count = connection.execute(
            text("SELECT COUNT(*) FROM transactions"),
        ).scalar()
        assert count == 0, f"Expected 0 transactions, got {count}"

        posting_count = connection.execute(
            text("SELECT COUNT(*) FROM postings"),
        ).scalar()
        assert posting_count == 0, f"Expected 0 postings, got {posting_count}"

    # ── T-4.14: currency mismatch ─────────────────────────────────────────

    def test_currency_mismatch_rejected(self, connection: Connection) -> None:
        """Postings with different currencies raise CurrencyMismatchError."""
        cash = get_account_by_name(connection, "Assets:Checking")
        food = get_account_by_name(connection, "Expenses:Food:Groceries")
        assert cash is not None and cash.id is not None
        assert food is not None and food.id is not None

        txn = Transaction(date=date(2024, 1, 15), description="Mixed currency")
        postings = [
            Posting(account_id=cash.id, amount=Decimal("100"), currency="COP"),
            Posting(account_id=food.id, amount=Decimal("-100"), currency="USD"),
        ]

        with pytest.raises(CurrencyMismatchError):
            create_transaction_with_postings(connection, txn, postings)

        # DB unchanged
        count = connection.execute(
            text("SELECT COUNT(*) FROM transactions"),
        ).scalar()
        assert count == 0, "Expected no transactions"
        posting_count = connection.execute(
            text("SELECT COUNT(*) FROM postings"),
        ).scalar()
        assert posting_count == 0, "Expected no postings"

    # ── T-4.15: too few postings ──────────────────────────────────────────

    def test_one_posting_rejected(self, connection: Connection) -> None:
        """Single posting raises TooFewPostings."""
        cash = get_account_by_name(connection, "Assets:Checking")
        assert cash is not None and cash.id is not None

        txn = Transaction(date=date(2024, 1, 15), description="Single posting")
        postings = [
            Posting(account_id=cash.id, amount=Decimal("100"), currency="COP"),
        ]

        with pytest.raises(TooFewPostings):
            create_transaction_with_postings(connection, txn, postings)

        count = connection.execute(
            text("SELECT COUNT(*) FROM transactions"),
        ).scalar()
        assert count == 0, "Expected no new transactions"

    def test_zero_postings_rejected(self, connection: Connection) -> None:
        """Empty postings list raises TooFewPostings."""
        txn = Transaction(date=date(2024, 1, 15), description="No postings")

        with pytest.raises(TooFewPostings):
            create_transaction_with_postings(connection, txn, [])

        count = connection.execute(
            text("SELECT COUNT(*) FROM transactions"),
        ).scalar()
        assert count == 0, "Expected no new transactions"

    def test_zero_amount_posting_rejected(self, connection: Connection) -> None:
        """Posting with zero amount raises ZeroAmountPosting."""
        cash = get_account_by_name(connection, "Assets:Checking")
        food = get_account_by_name(connection, "Expenses:Food:Groceries")
        assert cash is not None and cash.id is not None
        assert food is not None and food.id is not None

        txn = Transaction(date=date(2024, 1, 15), description="Zero amount")
        postings = [
            Posting(account_id=cash.id, amount=Decimal("0"), currency="COP"),
            Posting(account_id=food.id, amount=Decimal("0"), currency="COP"),
        ]

        with pytest.raises(ZeroAmountPosting):
            create_transaction_with_postings(connection, txn, postings)

        count = connection.execute(
            text("SELECT COUNT(*) FROM transactions"),
        ).scalar()
        assert count == 0, "Expected no new transactions"
