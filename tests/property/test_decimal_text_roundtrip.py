"""Property tests: Decimal → str → Decimal roundtrip — T-3.8.

Verifies that str() serialization followed by Decimal() reconstruction is an
identity for any finite Decimal, simulating the SQLite TEXT persistence path
used by DecimalAsText.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import assume, given
from hypothesis import strategies as st


@given(
    integer_part=st.integers(min_value=-999999999999999, max_value=999999999999999),
    fractional_part=st.integers(min_value=0, max_value=999999999999999),
    fractional_digits=st.integers(min_value=0, max_value=15),
)
def test_decimal_str_roundtrip(
    integer_part: int,
    fractional_part: int,
    fractional_digits: int,
) -> None:
    """For any finite Decimal, str() → Decimal() is an identity."""
    sign = -1 if integer_part < 0 else 1
    int_str = str(abs(integer_part))
    if fractional_digits > 0:
        frac_str = str(fractional_part).zfill(fractional_digits)[:fractional_digits]
        amount = Decimal(f"{'-' if sign == -1 else ''}{int_str}.{frac_str}")
    else:
        amount = Decimal(f"{'-' if sign == -1 else ''}{int_str}")

    assume(amount.is_finite())

    # str() produces canonical form (e.g. '1.10' → '1.1')
    text = str(amount)
    restored = Decimal(text)

    # Must be byte-exact: str(restored) == text
    assert str(restored) == text
    assert restored == amount


@given(
    integer_part=st.integers(min_value=-999999999, max_value=999999999),
    fractional_part=st.integers(min_value=0, max_value=99999999),
    fractional_digits=st.integers(min_value=0, max_value=8),
)
def test_decimal_text_storage_normalization(
    integer_part: int,
    fractional_part: int,
    fractional_digits: int,
) -> None:
    """Decimal → str → Decimal via str() = SQLite TEXT path."""
    sign = -1 if integer_part < 0 else 1
    int_str = str(abs(integer_part))
    if fractional_digits > 0:
        frac_str = str(fractional_part).zfill(fractional_digits)[:fractional_digits]
        amount = Decimal(f"{'-' if sign == -1 else ''}{int_str}.{frac_str}")
    else:
        amount = Decimal(f"{'-' if sign == -1 else ''}{int_str}")

    assume(amount.is_finite())

    # Simulate the DecimalAsText path: str(value) → TEXT → Decimal(value)
    as_text = str(amount)
    from_text = Decimal(as_text)

    assert from_text == amount
    # After normalization (e.g. Decimal('1.10') → str '1.1'), re-parsing gives the same value
    assert str(from_text) == as_text
