"""Property test (FX-4 claim 2): convert-then-aggregate algebraic identity.

For any posting set, converting each posting then summing equals summing per
currency then converting — within per-currency precision tolerance (each
postings' quantization introduces up to 1 ULP rounding noise).

Hypothesis strategies never pass through float — amounts are Decimal.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from pyfintracker.fx import convert
from pyfintracker.validation import PER_CURRENCY_DECIMALS

CCYS: tuple[str, ...] = tuple(PER_CURRENCY_DECIMALS.keys())


@st.composite
def _posting(draw: st.DrawFn) -> tuple[Decimal, str]:
    """Generate (amount, currency) where amount is in currency's natural precision."""
    ccy = draw(st.sampled_from(CCYS))
    precision = PER_CURRENCY_DECIMALS[ccy]
    if precision == 0:
        amount = draw(st.integers(min_value=-1000, max_value=1000))
        return (Decimal(amount), ccy)
    cents = draw(st.integers(min_value=-1_000_000, max_value=1_000_000))
    return (Decimal(cents) / Decimal(100), ccy)


@st.composite
def _rates_map(draw: st.DrawFn) -> dict[tuple[str, str], Decimal]:
    """Generate a fixed-point rate table to avoid cross-rate precision noise."""
    rates: dict[tuple[str, str], Decimal] = {}
    for ccy in CCYS:
        # Use a Decimal rate that survives the chain — no cross-conversion
        rate = draw(
            st.decimals(
                min_value=Decimal("1"),
                max_value=Decimal("100"),
                allow_nan=False,
                allow_infinity=False,
                places=4,
            )
        )
        # Identity + direct rates only
        rates[(ccy, ccy)] = Decimal("1")
        rates[(ccy, "COP")] = rate
        rates[(ccy, "USD")] = rate / Decimal("4000")
    return rates


def _ulp(ccy: str) -> Decimal:
    precision = PER_CURRENCY_DECIMALS[ccy]
    return Decimal("1").scaleb(-precision)


@settings(max_examples=200, deadline=None)
@given(
    postings=st.lists(_posting(), min_size=1, max_size=10),
    target=st.sampled_from(["COP", "USD"]),
    rates=_rates_map(),
)
def test_convert_then_sum_equals_sum_then_convert(
    postings: list[tuple[Decimal, str]],
    target: str,
    rates: dict[tuple[str, str], Decimal],
) -> None:
    """convert-then-sum ≈ sum-of-converted within per-ccy grouping tolerance.

    Path A rounds each posting independently; Path B rounds each per-ccy
    subtotal. The difference is bounded by ``max_postings_per_ccy * ULP``.
    """
    # Path A: convert each posting individually, then sum
    converted: list[Decimal] = []
    for a, c in postings:
        rate = rates.get((c, target), Decimal("1"))
        converted.append(convert(a, c, target, rate=rate))
    path_a = sum(converted, Decimal("0"))

    # Path B: group by currency, sum each group, then convert
    by_ccy: dict[str, Decimal] = {}
    for a, c in postings:
        by_ccy[c] = by_ccy.get(c, Decimal("0")) + a
    path_b_total = Decimal("0")
    for c, subtotal in by_ccy.items():
        rate = rates.get((c, target), Decimal("1"))
        path_b_total += convert(subtotal, c, target, rate=rate)

    ulp = _ulp(target)
    # ponytail: bound by max postings per ccy (each contributing ≤1 ULP noise)
    max_per_ccy = max(
        (sum(1 for _, cc in postings if cc == cur_ccy) for cur_ccy in by_ccy),
        default=1,
    )
    tol = ulp * max_per_ccy
    assert abs(path_a - path_b_total) <= tol, (
        f"convert-then-sum={path_a} vs sum-then-convert={path_b_total} "
        f"diff={abs(path_a - path_b_total)} > {tol} "
        f"(max_per_ccy={max_per_ccy}, ULP={ulp})"
    )


@settings(max_examples=200, deadline=None)
@given(
    rate=st.decimals(
        min_value=Decimal("0.01"),
        max_value=Decimal("100"),
        allow_nan=False,
        allow_infinity=False,
        places=4,
    ),
    target=st.sampled_from(CCYS),
)
def test_convert_zero_amount_always_zero(
    rate: Decimal,
    target: str,
) -> None:
    """convert(0, any, any) == 0 (zero must not introduce noise)."""
    result = convert(Decimal("0"), target, target, rate=rate)
    assert result == Decimal("0")
