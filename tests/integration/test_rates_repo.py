"""Integration tests for rate repository functions (T-A.4).

Tests use the shared ``connection`` fixture from conftest.py which provides a
fully migrated in-memory SQLite database with the 0001 schema + starter chart.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import Connection, text

from pyfintracker.models import Rate
from pyfintracker.repository import get_cached_rate, list_cached_rates, upsert_rate


@pytest.mark.integration
class TestUpsertRate:
    """T-A.4: upsert_rate idempotency."""

    def test_upsert_idempotent(self, session: Connection) -> None:
        """Upsert twice with same (date, from_ccy, to_ccy) = 1 row."""
        r = Rate(date=date(2026, 7, 18), from_ccy="USD", to_ccy="COP", rate=Decimal("3255.56"))

        first = upsert_rate(session, r)
        second = upsert_rate(session, r)

        # Same logical result (ids may differ due to RETURNING)
        assert first.date == second.date
        assert first.from_ccy == second.from_ccy
        assert first.to_ccy == second.to_ccy
        assert first.rate == second.rate

        # Only 1 row in DB
        rows = session.execute(
            text(
                "SELECT count(*) FROM rates WHERE base_currency='USD' AND target_currency='COP' AND date='2026-07-18'"
            )
        ).scalar()
        assert rows == 1

    def test_upsert_updates_rate(self, session: Connection) -> None:
        """Upsert with different rate on same key updates existing row."""
        r1 = Rate(date=date(2026, 7, 18), from_ccy="USD", to_ccy="COP", rate=Decimal("3255.56"))
        r2 = Rate(date=date(2026, 7, 18), from_ccy="USD", to_ccy="COP", rate=Decimal("3300.00"))

        upsert_rate(session, r1)
        result = upsert_rate(session, r2)

        assert result.rate == Decimal("3300.00")
        rows = session.execute(
            text(
                "SELECT count(*) FROM rates WHERE base_currency='USD' AND target_currency='COP' AND date='2026-07-18'"
            )
        ).scalar()
        assert rows == 1

    def test_upsert_returns_db_id(self, session: Connection) -> None:
        """Returned Rate carries the DB-assigned id (≥1), not None.

        Regression: catches _row_to_rate mutmut_28/35/43/44 which drop or
        mangle ``id=r.get("id")`` — none of the surrounding tests observed
        the id, so those mutations stayed alive.
        """
        r = Rate(date=date(2026, 7, 18), from_ccy="USD", to_ccy="COP", rate=Decimal("3255.56"))
        returned = upsert_rate(session, r)

        assert returned.id is not None
        assert returned.id >= 1

        cached = get_cached_rate(session, "USD", "COP", date(2026, 7, 18))
        assert cached is not None
        assert cached.id == returned.id


@pytest.mark.integration
class TestGetCachedRate:
    """T-A.4: get_cached_rate lookup."""

    def test_get_cached_rate_hit(self, session: Connection) -> None:
        """get_cached_rate returns stored Rate."""
        r = Rate(date=date(2026, 7, 18), from_ccy="USD", to_ccy="COP", rate=Decimal("3255.56"))
        upsert_rate(session, r)

        cached = get_cached_rate(session, "USD", "COP", date(2026, 7, 18))
        assert cached is not None
        assert cached.rate == Decimal("3255.56")
        assert cached.from_ccy == "USD"
        assert cached.to_ccy == "COP"

    def test_get_cached_rate_miss(self, session: Connection) -> None:
        """get_cached_rate returns None for missing pair."""
        cached = get_cached_rate(session, "USD", "EUR", date(2026, 7, 18))
        assert cached is None

    def test_inverse_lookup_via_direct_only(self, session: Connection) -> None:
        """get_cached_rate only does direct lookup (no auto-inverse)."""
        # Only store COP→USD, then try USD→COP — should miss
        r = Rate(date=date(2026, 7, 18), from_ccy="COP", to_ccy="USD", rate=Decimal("0.000307"))
        upsert_rate(session, r)

        cached = get_cached_rate(session, "USD", "COP", date(2026, 7, 18))
        assert cached is None, "Repo should NOT auto-invert — caller does inversion"


@pytest.mark.integration
class TestListCachedRates:
    """T-A.4: list_cached_rates."""

    def test_list_cached_rates_empty(self, session: Connection) -> None:
        """list_cached_rates returns empty list when no rates."""
        rates = list_cached_rates(session)
        assert rates == []

    def test_list_cached_rates(self, session: Connection) -> None:
        """list_cached_rates returns all stored rates."""
        upsert_rate(
            session,
            Rate(date=date(2026, 7, 18), from_ccy="USD", to_ccy="COP", rate=Decimal("3255.56")),
        )
        upsert_rate(
            session,
            Rate(date=date(2026, 7, 18), from_ccy="EUR", to_ccy="COP", rate=Decimal("4200.00")),
        )

        rates = list_cached_rates(session)
        assert len(rates) == 2

    def test_list_cached_rates_since(self, session: Connection) -> None:
        """list_cached_rates(since=date) filters by date."""
        upsert_rate(
            session,
            Rate(date=date(2026, 7, 1), from_ccy="USD", to_ccy="COP", rate=Decimal("3000.00")),
        )
        upsert_rate(
            session,
            Rate(date=date(2026, 7, 18), from_ccy="USD", to_ccy="COP", rate=Decimal("3255.56")),
        )

        rates = list_cached_rates(session, since=date(2026, 7, 15))
        assert len(rates) == 1
        assert rates[0].date == date(2026, 7, 18)
