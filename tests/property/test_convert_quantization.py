"""Property test (FX-3 claim 1): convert quantizes to target precision per pair.

For any Decimal amount and any 12-currency allowlisted pair, the result of
``fx.convert`` has exactly ``PER_CURRENCY_DECIMALS[to_ccy]`` decimal places.

Hypothesis strategies never pass through float — amounts are Decimal.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from pyfintracker.fx import convert
from pyfintracker.validation import PER_CURRENCY_DECIMALS

# ponytail: derive from PER_CURRENCY_DECIMALS so we don't drift
CCYS: tuple[str, ...] = tuple(PER_CURRENCY_DECIMALS.keys())


@given(
    amount=st.decimals(
        min_value=Decimal("-999999999"),
        max_value=Decimal("999999999"),
        allow_nan=False,
        allow_infinity=False,
        places=4,
    ),
    from_ccy=st.sampled_from(CCYS),
    to_ccy=st.sampled_from(CCYS),
    rate=st.decimals(
        min_value=Decimal("0.0001"),
        max_value=Decimal("99999"),
        allow_nan=False,
        allow_infinity=False,
        places=6,
    ),
)
@settings(max_examples=300, deadline=None)
def test_convert_quantizes_to_target_precision(
    amount: Decimal,
    from_ccy: str,
    to_ccy: str,
    rate: Decimal,
) -> None:
    """convert(amount, from→to, rate) has exactly to_ccy precision decimal places."""
    result = convert(amount, from_ccy, to_ccy, rate=rate)

    expected_places = PER_CURRENCY_DECIMALS[to_ccy]
    assert -result.as_tuple().exponent == expected_places, (
        f"Expected {expected_places} dp for {to_ccy}, "
        f"got exponent {result.as_tuple().exponent} (value={result})"
    )


@given(
    ccy=st.sampled_from(CCYS),
    rate=st.decimals(
        min_value=Decimal("0.0001"),
        max_value=Decimal("99999"),
        allow_nan=False,
        allow_infinity=False,
        places=6,
    ),
)
@settings(max_examples=200, deadline=None)
def test_convert_same_currency_quantizes(
    ccy: str,
    rate: Decimal,
) -> None:
    """When from==to, convert quantizes the input to the target's precision."""
    amount = Decimal("1234.5678")
    result = convert(amount, ccy, ccy, rate=rate)
    expected_places = PER_CURRENCY_DECIMALS[ccy]
    assert -result.as_tuple().exponent == expected_places
