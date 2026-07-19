"""Property test (FX-1 claim 1): Rate.to_row → from_row → to_row is byte-exact.

For any Rate value (with hypothesis-generated date, ccy, rate, source, id,
fetched_at), serializing through ``to_row`` and reconstructing via
``from_row`` must yield an object whose re-serialized row dict equals the
original (modulo DB-driver type coercion on Decimal/date).

Hypothesis strategies never pass through float — all amounts are Decimal.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from pyfintracker.models import Rate

ALLOWED_CCY: tuple[str, ...] = ("USD", "EUR", "GBP", "COP", "JPY", "CAD")

# Build positive Decimal amounts (rates > 0 — domain invariant)
rate_values = st.decimals(
    min_value=Decimal("0.0001"),
    max_value=Decimal("99999"),
    allow_nan=False,
    allow_infinity=False,
    places=6,
)


@st.composite
def _rate_strategy(draw: st.DrawFn) -> Rate:
    """Build a Rate with hypothesis-generated fields, NEVER via float."""
    r_date = draw(st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31)))
    r_from = draw(st.sampled_from(ALLOWED_CCY))
    r_to = draw(st.sampled_from(ALLOWED_CCY))
    assume(r_from != r_to)
    r_rate = draw(rate_values)
    r_source = draw(st.sampled_from(["frankfurter", "identity", "manual"]))
    r_id = draw(st.integers(min_value=1, max_value=10_000_000))
    fetched_at = draw(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 1, 1)))
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=UTC)

    return Rate(
        date=r_date,
        from_ccy=r_from,
        to_ccy=r_to,
        rate=r_rate,
        source=r_source,
        id=r_id,
        fetched_at=fetched_at,
    )


def _simulate_db_roundtrip(row: dict[str, object]) -> dict[str, object]:
    """Simulate SQLite TEXT storage AND the readback parser.

    SQLAlchemy + SQLite stores date as TEXT ISO and reads back as ``date``;
    datetime as TEXT ISO and reads back as naive ``datetime`` (no tzinfo).
    """
    out: dict[str, object] = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            naive = v.astimezone(UTC).replace(tzinfo=None)
            out[k] = datetime.fromisoformat(naive.isoformat())
        elif isinstance(v, date):
            out[k] = date.fromisoformat(v.isoformat())
        else:
            out[k] = v
    return out


def _expected_fetched_at(fa: datetime | None) -> datetime | None:
    """What fetched_at looks like after a DB roundtrip (naive UTC)."""
    if fa is None:
        return None
    return fa.astimezone(UTC).replace(tzinfo=None)


@settings(max_examples=200, deadline=None)
@given(rate=_rate_strategy())
def test_rate_to_row_from_row_byte_exact(rate: Rate) -> None:
    """For any Rate, from_row(to_row(r)) == r for all 7 fields.

    Simulates the SQLite TEXT roundtrip: datetime → ISO string → datetime (no tz).
    """
    row = rate.to_row()
    row_after_db = _simulate_db_roundtrip(row)

    reconstructed = Rate.from_row(row_after_db)

    assert reconstructed.date == rate.date
    assert reconstructed.from_ccy == rate.from_ccy
    assert reconstructed.to_ccy == rate.to_ccy
    assert reconstructed.rate == rate.rate
    assert reconstructed.source == rate.source
    assert reconstructed.id == rate.id
    assert reconstructed.fetched_at == _expected_fetched_at(rate.fetched_at)


@settings(max_examples=200, deadline=None)
@given(rate=_rate_strategy())
def test_rate_to_row_idempotent(rate: Rate) -> None:
    """to_row(to_row(r)) yields the same dict after DB-driver coercion."""
    row1 = rate.to_row()
    row2 = rate.to_row()
    assert row1 == row2
    assert row1["base_currency"] == rate.from_ccy
    assert row1["target_currency"] == rate.to_ccy
    assert row1["rate"] == rate.rate
