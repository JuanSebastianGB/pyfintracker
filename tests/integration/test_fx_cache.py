"""Integration tests for fx.get_rate cache layer (T-B.6 through T-B.11).

Uses the shared ``connection`` fixture for a fully migrated in-memory SQLite.
FrankfurterClient injected via MockTransport for deterministic HTTP.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import Connection, text

from pyfintracker.exceptions import FxUnavailableError, RateNotFoundError
from pyfintracker.fx import FrankfurterClient, get_rate
from pyfintracker.models import Rate
from pyfintracker.repository import get_cached_rate, upsert_rate


def _rate_json(date_str: str, base: str, target: str, rate: float) -> dict:
    return {"date": date_str, "base": base, "quote": target, "rate": rate}


@pytest.mark.integration
class TestSameCurrencyAndCacheHit:
    """T-B.6: same-currency identity + cache-hit fast path."""

    def test_get_rate_same_currency_no_io(self, session: Connection) -> None:
        """from==to returns Rate(rate=Decimal('1')) with 0 transport calls."""
        transport_calls: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            transport_calls.append(str(req.url))
            return httpx.Response(200, json=_rate_json("2026-07-18", "USD", "USD", 1.0))

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        rate = get_rate("USD", "USD", _client=client, _conn=session)

        assert rate.rate == Decimal("1")
        assert rate.from_ccy == "USD"
        assert rate.to_ccy == "USD"
        assert len(transport_calls) == 0

    def test_get_rate_cache_hit_uses_stored_row(self, session: Connection) -> None:
        """Cache hit returns stored Rate, 0 transport calls."""
        upsert_rate(
            session,
            Rate(date=date.today(), from_ccy="USD", to_ccy="COP", rate=Decimal("3255.56")),
        )
        transport_calls: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            transport_calls.append(str(req.url))
            return httpx.Response(200, json=_rate_json("2026-07-18", "USD", "COP", 3300.0))

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        rate = get_rate("USD", "COP", _client=client, _conn=session)

        assert rate.rate == Decimal("3255.56")
        assert len(transport_calls) == 0


@pytest.mark.integration
class TestInverseLookup:
    """T-B.7: inverse lookup — 1/rate quantized to source precision."""

    def test_get_rate_inverse_lookup(self, session: Connection) -> None:
        """Inverse rate is 1/direct quantized to from_ccy precision."""
        upsert_rate(
            session,
            Rate(date=date.today(), from_ccy="COP", to_ccy="USD", rate=Decimal("0.000307")),
        )

        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_rate_json(str(date.today()), "USD", "COP", 3257.0))

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        rate = get_rate("USD", "COP", on=date.today(), _client=client, _conn=session)
        # 1 / 0.000307 ≈ 3257.328... → quantized to from_ccy (USD) precision (2) = 3257.33
        assert rate.rate == Decimal("3257.33")
        assert rate.from_ccy == "USD"
        assert rate.to_ccy == "COP"


@pytest.mark.integration
class TestCacheMissFetch:
    """T-B.8: cache miss → fetch via FrankfurterClient → upsert."""

    def test_get_rate_miss_calls_fetch_latest_and_caches(self, session: Connection) -> None:
        """Cache miss triggers fetch_latest exactly once and upserts."""
        transport_calls: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            transport_calls.append(str(req.url))
            return httpx.Response(
                200,
                json=_rate_json(str(date.today()), "USD", "COP", 3255.56),
            )

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        rate = get_rate("USD", "COP", _client=client, _conn=session)

        assert rate.rate == Decimal("3255.56")
        assert len(transport_calls) == 1

        # Verify cached in DB
        cached = get_cached_rate(session, "USD", "COP", date.today())
        assert cached is not None
        assert cached.rate == Decimal("3255.56")

    def test_get_rate_miss_transport_down(self, session: Connection) -> None:
        """Cache miss + transport down propagates FxUnavailableError."""
        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        with pytest.raises(FxUnavailableError):
            get_rate("USD", "COP", _client=client, _conn=session)


@pytest.mark.integration
class TestTTL:
    """T-B.8 (continued): TTL check via fetched_at."""

    def _set_fetched_at(self, session: Connection, age_hours: int) -> None:
        """Upsert a rate then manually set its fetched_at to n hours ago."""
        upsert_rate(
            session,
            Rate(date=date.today(), from_ccy="USD", to_ccy="COP", rate=Decimal("3255.56")),
        )
        ts = datetime.now(UTC) - timedelta(hours=age_hours)
        session.execute(
            text("UPDATE rates SET fetched_at = :ts WHERE base_currency='USD' AND target_currency='COP'"),
            {"ts": ts.isoformat()},
        )

    def test_get_rate_23h_old_cache_reused(self, session: Connection) -> None:
        """Cache < 24h old is reused (0 transport calls)."""
        self._set_fetched_at(session, 23)
        transport_calls: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            transport_calls.append(str(req.url))
            return httpx.Response(200, json=_rate_json("2026-07-18", "USD", "COP", 3300.0))

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        rate = get_rate("USD", "COP", _client=client, _conn=session)
        assert rate.rate == Decimal("3255.56")
        assert len(transport_calls) == 0

    def test_get_rate_25h_old_cache_refreshed(self, session: Connection) -> None:
        """Cache > 24h old triggers refresh via transport."""
        self._set_fetched_at(session, 25)
        transport_calls: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            transport_calls.append(str(req.url))
            return httpx.Response(
                200,
                json=_rate_json("2026-07-18", "USD", "COP", 3300.0),
            )

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        rate = get_rate("USD", "COP", _client=client, _conn=session)
        assert rate.rate == Decimal("3300.00")
        assert len(transport_calls) == 1


@pytest.mark.integration
class TestStaleFallback:
    """T-B.9: stale-fallback warning emission."""

    def _stale_rate(self, session: Connection, age_hours: int = 25) -> None:
        """Upsert a rate then set fetched_at to n hours ago."""
        upsert_rate(
            session,
            Rate(date=date.today(), from_ccy="USD", to_ccy="COP", rate=Decimal("3255.56")),
        )
        ts = datetime.now(UTC) - timedelta(hours=age_hours)
        session.execute(
            text("UPDATE rates SET fetched_at = :ts WHERE base_currency='USD' AND target_currency='COP'"),
            {"ts": ts.isoformat()},
        )

    def test_stale_cache_fallback_warns_on_stderr(self, session: Connection, capsys: pytest.CaptureFixture) -> None:
        """Cache hit + transport down returns cache and emits warning."""
        self._stale_rate(session)

        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        rate = get_rate("USD", "COP", _client=client, _conn=session)

        assert rate.rate == Decimal("3255.56")
        captured = capsys.readouterr()
        assert "warning: using cached rate from" in captured.err

    def test_stale_cache_fallback_format_regex(self, session: Connection, capsys: pytest.CaptureFixture) -> None:
        """Warning matches expected regex format."""
        import re

        self._stale_rate(session)

        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        get_rate("USD", "COP", _client=client, _conn=session)

        captured = capsys.readouterr()
        pattern = r"^warning: using cached rate from \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \(network unavailable\)$"
        assert re.match(pattern, captured.err.strip()), f"Warning '{captured.err.strip()}' doesn't match pattern"


@pytest.mark.integration
class TestHistoricalAndEdgeCases:
    """T-B.10: historical TTL-ignored + future-date + 5xx no-overwrite."""

    def test_historical_cache_used_regardless_of_age(self, session: Connection) -> None:
        """Historical row 5 years old is used without transport calls."""
        upsert_rate(
            session,
            Rate(date=date(2021, 1, 15), from_ccy="USD", to_ccy="COP", rate=Decimal("3500.00")),
        )
        transport_calls: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            transport_calls.append(str(req.url))
            return httpx.Response(200, json=_rate_json("2021-01-15", "USD", "COP", 4000.0))

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        rate = get_rate("USD", "COP", on=date(2021, 1, 15), _client=client, _conn=session)

        assert rate.rate == Decimal("3500.00")
        assert len(transport_calls) == 0

    def test_future_date_rejected_before_network(self, session: Connection) -> None:
        """on > date.today() raises RateNotFoundError before any network call."""
        transport_calls: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            transport_calls.append(str(req.url))
            return httpx.Response(200, json=_rate_json("2099-01-01", "USD", "COP", 0))

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        with pytest.raises(RateNotFoundError):
            get_rate("USD", "COP", on=date(2099, 1, 1), _client=client, _conn=session)
        assert len(transport_calls) == 0

    def test_5xx_does_not_overwrite_cache(self, session: Connection) -> None:
        """503 falls back to stale cache and does NOT overwrite DB row."""
        # Set stale cache (>24h old) so code attempts fetch
        upsert_rate(
            session,
            Rate(date=date.today(), from_ccy="USD", to_ccy="COP", rate=Decimal("3255.56")),
        )
        ts = datetime.now(UTC) - timedelta(hours=25)
        session.execute(
            text("UPDATE rates SET fetched_at = :ts WHERE base_currency='USD' AND target_currency='COP'"),
            {"ts": ts.isoformat()},
        )

        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"message": "service unavailable"})

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        rate = get_rate("USD", "COP", _client=client, _conn=session)

        # Falls back to stale cache (does not raise)
        assert rate.rate == Decimal("3255.56")

        # Cache unchanged (503 did NOT overwrite)
        cached = get_cached_rate(session, "USD", "COP", date.today())
        assert cached is not None
        assert cached.rate == Decimal("3255.56")

    def test_historical_cache_miss_network_down(self, session: Connection) -> None:
        """Historical miss + network down raises FxUnavailableError (never substitutes today)."""
        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        with pytest.raises(FxUnavailableError):
            get_rate("USD", "EUR", on=date(2023, 6, 1), _client=client, _conn=session)


@pytest.mark.integration
class TestEndToEnd:
    """T-B.11: end-to-end cache fill + reuse."""

    def test_get_rate_cache_fill_roundtrip(self, session: Connection) -> None:
        """First call: 1 transport hit, row in rates. Second call: 0 transport hits."""
        transport_calls: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            transport_calls.append(str(req.url))
            return httpx.Response(
                200,
                json=_rate_json(str(date.today()), "USD", "COP", 3255.56),
            )

        client = FrankfurterClient(transport=httpx.MockTransport(handler))

        # First call — cache miss
        rate1 = get_rate("USD", "COP", _client=client, _conn=session)
        assert rate1.rate == Decimal("3255.56")
        assert len(transport_calls) == 1

        # Verify row in DB
        rows = session.execute(
            text("SELECT count(*) FROM rates WHERE base_currency='USD' AND target_currency='COP'")
        ).scalar()
        assert rows == 1

        # Second call — cache hit
        rate2 = get_rate("USD", "COP", _client=client, _conn=session)
        assert rate2.rate == Decimal("3255.56")
        assert len(transport_calls) == 1  # no new calls

    def test_get_rate_cache_fill_historical_roundtrip(self, session: Connection) -> None:
        """First historical call: 1 transport, second: 0 transport."""
        transport_calls: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            transport_calls.append(str(req.url))
            return httpx.Response(
                200,
                json=_rate_json("2024-01-15", "USD", "COP", 3924.50),
            )

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        on = date(2024, 1, 15)

        rate1 = get_rate("USD", "COP", on=on, _client=client, _conn=session)
        assert rate1.rate == Decimal("3924.50")
        assert len(transport_calls) == 1

        rate2 = get_rate("USD", "COP", on=on, _client=client, _conn=session)
        assert rate2.rate == Decimal("3924.50")
        assert len(transport_calls) == 1
