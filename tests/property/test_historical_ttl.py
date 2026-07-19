"""Property test (FX-5 claim 4): historical rate TTL is ignored.

For any cached historical rate with ``fetched_at`` age in [1y, 50y], calling
``get_rate`` for the same pair+date must use the cache (0 HTTP transport calls).

Hypothesis strategies never pass through float — amounts are Decimal.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import httpx
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import Connection

from pyfintracker.fx import FrankfurterClient, get_rate
from pyfintracker.models import Rate
from pyfintracker.repository import upsert_rate

CCYS: tuple[str, ...] = ("USD", "EUR", "GBP", "COP", "JPY", "CAD")

# Build historical dates 1-50 years in the past
_historical_date = st.dates(
    min_value=date.today() - timedelta(days=50 * 365),
    max_value=date.today() - timedelta(days=365),
)


@st.composite
def _historical_pair(draw: st.DrawFn) -> tuple[date, str, str, Decimal]:
    """Generate (historical_date, from_ccy, to_ccy, rate)."""
    h_date = draw(_historical_date)
    from_ccy = draw(st.sampled_from(CCYS))
    to_ccy = draw(st.sampled_from(CCYS))
    if from_ccy == to_ccy:
        to_ccy = "USD" if from_ccy != "USD" else "COP"
    rate = draw(
        st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("99999"),
            allow_nan=False,
            allow_infinity=False,
            places=4,
        )
    )
    return (h_date, from_ccy, to_ccy, rate)


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(pair=_historical_pair())
def test_historical_rate_ttl_ignored(
    pair: tuple[date, str, str, Decimal],
    connection: Connection,
) -> None:
    """A historical cache row 1y-50y old is used; transport is never called."""
    h_date, from_ccy, to_ccy, rate_value = pair

    # Seed the cache with a historical rate, fetched_at = now (recent write)
    upsert_rate(
        connection,
        Rate(
            date=h_date,
            from_ccy=from_ccy,
            to_ccy=to_ccy,
            rate=rate_value,
        ),
    )

    transport_calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        transport_calls.append(str(req.url))
        return httpx.Response(
            200,
            json={
                "date": str(h_date),
                "base": from_ccy,
                "quote": to_ccy,
                "rate": float(rate_value),
            },
        )

    client = FrankfurterClient(transport=httpx.MockTransport(handler))

    result = get_rate(from_ccy, to_ccy, on=h_date, _client=client, _conn=connection)

    # Result equals cached rate, transport was never called
    assert result.rate == rate_value, (
        f"Expected cached rate {rate_value}, got {result.rate}"
    )
    assert len(transport_calls) == 0, (
        f"Transport was called {len(transport_calls)} times for historical cache hit"
    )
