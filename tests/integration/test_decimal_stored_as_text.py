"""Integration tests verifying Decimal is stored as TEXT in SQLite.

The migration defines postings.amount and rates.rate as TEXT columns.
This ensures Decimal roundtrips without precision loss that would
occur with NUMERIC/REAL types.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import Connection, text


@pytest.mark.integration
class TestDecimalStoredAsText:
    """T-3.6: DecimalAsText roundtrip via raw SQL."""

    def test_posting_amount_stored_as_text(self, connection: Connection) -> None:
        """Insert a posting with Decimal and verify TEXT storage."""
        # Create a transaction first
        tx_id = connection.execute(
            text(
                "INSERT INTO transactions (date, description) VALUES ('2026-07-17', 'Test') RETURNING id"
            ),
        ).scalar()

        # Get an account id from the starter chart
        acct_id = connection.execute(
            text("SELECT id FROM accounts WHERE name = 'Assets:Checking'"),
        ).scalar()

        # Insert a posting with a Decimal amount (must be high-precision to test roundtrip)
        original = Decimal("123.456789")
        connection.execute(
            text(
                "INSERT INTO postings (transaction_id, account_id, amount, currency) VALUES (:tid, :aid, :amt, :cur)"
            ),
            {"tid": tx_id, "aid": acct_id, "amt": str(original), "cur": "COP"},
        )

        # Read it back — raw column value from SQLite
        row = connection.execute(
            text("SELECT amount, typeof(amount) FROM postings WHERE transaction_id = :tid"),
            {"tid": tx_id},
        ).fetchone()

        assert row is not None
        raw_text, type_name = row[0], row[1]
        # Verify it's stored as TEXT, not REAL or NUMERIC
        assert type_name == "text", f"Expected 'text' type, got '{type_name}'"
        # Verify the text reads back exactly
        assert raw_text == "123.456789"
        # Verify it roundtrips to Decimal with full precision
        assert Decimal(raw_text) == original

    def test_rate_stored_as_text(self, connection: Connection) -> None:
        """Insert a rate with Decimal and verify TEXT storage."""
        original = Decimal("4385.50")
        connection.execute(
            text(
                "INSERT INTO rates (base_currency, target_currency, rate, date, source) "
                "VALUES (:base, :target, :rate, :date, :source)"
            ),
            {
                "base": "USD",
                "target": "COP",
                "rate": str(original),
                "date": "2026-07-17",
                "source": "Test",
            },
        )

        row = connection.execute(
            text(
                "SELECT rate, typeof(rate) FROM rates WHERE base_currency = 'USD' AND target_currency = 'COP'"
            ),
        ).fetchone()

        assert row is not None
        raw_text, type_name = row[0], row[1]
        assert type_name == "text", f"Expected 'text' type, got '{type_name}'"
        assert raw_text == "4385.50"
        assert Decimal(raw_text) == original

    def test_decimal_high_precision_roundtrip(self, connection: Connection) -> None:
        """Very high precision Decimal survives roundtrip unchanged."""
        tx_id = connection.execute(
            text(
                "INSERT INTO transactions (date, description) VALUES ('2026-07-17', 'Precision') RETURNING id"
            ),
        ).scalar()
        acct_id = connection.execute(
            text("SELECT id FROM accounts WHERE name = 'Assets:Checking'"),
        ).scalar()

        # A 20-decimal-place value
        high_precision = Decimal("999999999.12345678901234567890")
        connection.execute(
            text(
                "INSERT INTO postings (transaction_id, account_id, amount, currency) VALUES (:tid, :aid, :amt, :cur)"
            ),
            {"tid": tx_id, "aid": acct_id, "amt": str(high_precision), "cur": "USD"},
        )

        row = connection.execute(
            text("SELECT amount FROM postings WHERE transaction_id = :tid"),
            {"tid": tx_id},
        ).fetchone()
        assert row is not None
        assert Decimal(row[0]) == high_precision
