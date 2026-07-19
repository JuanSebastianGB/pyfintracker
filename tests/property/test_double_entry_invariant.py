"""Property: For any balanced set of postings, validate_transaction succeeds.
For any unbalanced set, it raises UnbalancedTransaction.

T-4.9 — double-entry bookkeeping invariant (sum-zero).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from hypothesis import assume, given
from hypothesis import strategies as st

from pyfintracker.exceptions import UnbalancedTransaction
from pyfintracker.models import Posting, Transaction
from pyfintracker.validation import validate_transaction

# Generate pairs of amounts that sum to zero
BALANCED = st.builds(
    lambda a: (a, -a),
    st.decimals(
        min_value=Decimal("0.01"),
        max_value=Decimal("999999"),
        allow_nan=False,
        allow_infinity=False,
    ),
)


@given(pair=BALANCED)
def test_balanced_two_postings_succeeds(pair: tuple[Decimal, Decimal]) -> None:
    """When two amounts sum to zero, validation always passes."""
    a, b = pair
    assume(a != Decimal("0"))
    assume(b != Decimal("0"))

    txn = Transaction(date=date(2024, 1, 1), description="prop test", currency="COP")
    postings = [
        Posting(account_id=1, amount=a, currency="COP"),
        Posting(account_id=2, amount=b, currency="COP"),
    ]
    validate_transaction(txn, postings)  # should not raise


@given(
    a=st.decimals(
        min_value=Decimal("-999"),
        max_value=Decimal("999"),
        allow_nan=False,
        allow_infinity=False,
    ),
    b=st.decimals(
        min_value=Decimal("-999"),
        max_value=Decimal("999"),
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_unbalanced_two_postings_raises(a: Decimal, b: Decimal) -> None:
    """When two amounts do NOT sum to zero, UnbalancedTransaction is raised."""
    assume(a != Decimal("0"))
    assume(b != Decimal("0"))
    assume(a + b != Decimal("0"))

    txn = Transaction(date=date(2024, 1, 1), description="prop test", currency="COP")
    postings = [
        Posting(account_id=1, amount=a, currency="COP"),
        Posting(account_id=2, amount=b, currency="COP"),
    ]
    try:
        validate_transaction(txn, postings)
        raise AssertionError(f"Expected UnbalancedTransaction for {a} + {b} = {a + b}")
    except UnbalancedTransaction:
        pass
