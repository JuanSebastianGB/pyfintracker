"""Property: Synthetic opening balance transaction always sums to 0.

T-4.10 — Opening balance creates a debit + credit pair that validates
as a balanced transaction for any positive amount and supported currency.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from pyfintracker.models import Posting, Transaction
from pyfintracker.validation import validate_transaction


@given(
    amount=st.decimals(
        min_value=Decimal("0.01"),
        max_value=Decimal("999999999999"),
        allow_nan=False,
        allow_infinity=False,
    ),
    currency=st.sampled_from(["COP", "USD", "EUR", "GBP", "JPY"]),
)
def test_opening_balance_zero_sum(amount: Decimal, currency: str) -> None:
    """The synthetic opening balance (debit + credit) always sums to 0."""
    txn = Transaction(date=date.today(), description="Opening balance test", currency=currency)
    postings = [
        Posting(account_id=1, amount=amount, currency=currency),
        Posting(account_id=2, amount=-amount, currency=currency),
    ]
    validate_transaction(txn, postings)  # should pass for any positive amount
