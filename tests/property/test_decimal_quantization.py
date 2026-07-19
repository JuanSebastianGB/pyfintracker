"""Property-based tests for per-currency decimal quantization — T-3.7.

Verifies that ``quantize_for_currency`` always produces:
1. A finite Decimal with the correct per-currency precision.
2. A rounding error strictly less than 1 unit in the last place.
3. Unknown currencies are rejected.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from pyfintracker.exceptions import InvalidCurrency
from pyfintracker.validation import PER_CURRENCY_DECIMALS, quantize_for_currency


@given(
    integer_part=st.integers(min_value=-999999999, max_value=999999999),
    fractional_part=st.integers(min_value=0, max_value=9999999999),
    fractional_digits=st.integers(min_value=0, max_value=10),
)
def test_quantization_per_currency(
    integer_part: int,
    fractional_part: int,
    fractional_digits: int,
) -> None:
    """For any finite Decimal, quantize_for_currency produces the correct
    precision and rounding error < 1 unit in the last place."""
    sign = -1 if integer_part < 0 else 1
    int_str = str(abs(integer_part))
    if fractional_digits > 0:
        frac_str = str(fractional_part).zfill(fractional_digits)[:fractional_digits]
        amount = Decimal(f"{'-' if sign == -1 else ''}{int_str}.{frac_str}")
    else:
        amount = Decimal(f"{'-' if sign == -1 else ''}{int_str}")

    assume(amount.is_finite())

    for currency in ["COP", "USD", "EUR", "GBP", "JPY"]:
        result = quantize_for_currency(amount, currency)
        assert result.is_finite()
        expected_places = PER_CURRENCY_DECIMALS[currency]
        assert result.as_tuple().exponent == -expected_places, (
            f"Expected {expected_places} dp for {currency}, "
            f"got exponent {result.as_tuple().exponent}"
        )
        # Rounding error < 1 unit in the last place
        ulp = Decimal("1").scaleb(-expected_places)
        assert abs(result - amount) < ulp, (
            f"Rounding error {abs(result - amount)} >= 1 ulp ({ulp}) for {amount} in {currency}"
        )


@given(amount=st.decimals(allow_nan=False, allow_infinity=False, places=10))
def test_quantization_unknown_currency_rejected(amount: Decimal) -> None:
    """Unknown currency raises InvalidCurrency."""
    with pytest.raises(InvalidCurrency):
        quantize_for_currency(amount, "XXX")
