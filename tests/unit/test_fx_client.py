"""Unit tests for FrankfurterClient + fx module (T-B.1 through T-B.5)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest

from pyfintracker.exceptions import (
    FxUnavailableError,
    InvalidCurrencyError,
    RateNotFoundError,
)
from pyfintracker.fx import FrankfurterClient, list_supported_currencies


@pytest.mark.unit
class TestFrankfurterClientSkeleton:
    """T-B.1: FrankfurterClient skeleton."""

    def test_base_url_pinned_to_v2(self) -> None:
        """FrankfurterClient.BASE_URL is pinned to v2."""
        assert FrankfurterClient.BASE_URL == "https://api.frankfurter.dev/v2"

    def test_transport_injectable(self) -> None:
        """Transport is injectable via __init__."""
        transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
        client = FrankfurterClient(transport=transport)
        assert client is not None


@pytest.mark.unit
class TestFetchLatest:
    """T-B.2: FrankfurterClient.fetch_latest."""

    def test_fetch_latest_parses_decimal(self) -> None:
        """fetch_latest returns Rate with Decimal rate (not float)."""
        def handler(req: httpx.Request) -> httpx.Response:
            assert "/v2/rate/USD/COP" in str(req.url)
            return httpx.Response(
                200,
                json={"date": "2026-07-18", "base": "USD", "quote": "COP", "rate": 3255.56},
            )

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        rate = client.fetch_latest("USD", "COP")

        assert rate.from_ccy == "USD"
        assert rate.to_ccy == "COP"
        assert rate.date == date(2026, 7, 18)
        assert isinstance(rate.rate, Decimal)
        assert rate.rate == Decimal("3255.56")
        assert rate.source == "frankfurter"

    def test_fetch_latest_404_raises_RateNotFoundError(self) -> None:
        """404 response raises RateNotFoundError with code=4."""
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"message": "not found"})

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        with pytest.raises(RateNotFoundError) as exc:
            client.fetch_latest("USD", "XYZ")
        assert exc.value.code == 4

    def test_fetch_latest_422_invalid_currency_raises_InvalidCurrencyError(self) -> None:
        """422 with invalid currency raises InvalidCurrencyError with code=5."""
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(422, json={"message": "invalid currency: XYZ"})

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        with pytest.raises(InvalidCurrencyError) as exc:
            client.fetch_latest("USD", "XYZ")
        assert exc.value.code == 5

    def test_fetch_latest_connect_error_raises_FxUnavailableError(self) -> None:
        """httpx.ConnectError raises FxUnavailableError with code=6."""
        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        with pytest.raises(FxUnavailableError) as exc:
            client.fetch_latest("USD", "COP")
        assert exc.value.code == 6

    def test_fetch_latest_5xx_raises_FxUnavailableError(self) -> None:
        """5xx response raises FxUnavailableError with code=6."""
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"message": "service unavailable"})

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        with pytest.raises(FxUnavailableError) as exc:
            client.fetch_latest("USD", "COP")
        assert exc.value.code == 6

    def test_fetch_latest_malformed_json_raises_FxUnavailableError(self) -> None:
        """Malformed JSON (missing rate key) raises RateNotFoundError."""
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"date": "2026-07-18", "base": "USD"})

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        with pytest.raises(RateNotFoundError):
            client.fetch_latest("USD", "COP")

    def test_fetch_latest_zero_rate_raises_RateNotFoundError(self) -> None:
        """Zero or negative rate from provider raises RateNotFoundError."""
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"date": "2026-07-18", "base": "USD", "quote": "COP", "rate": 0},
            )

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        with pytest.raises(RateNotFoundError):
            client.fetch_latest("USD", "COP")


@pytest.mark.unit
class TestFetchHistorical:
    """T-B.3: FrankfurterClient.fetch_historical."""

    def test_fetch_historical_uses_effective_date(self) -> None:
        """fetch_historical returns Rate with the API's effective date."""
        def handler(req: httpx.Request) -> httpx.Response:
            assert "/2026-07-15" in str(req.url) or "date=2026-07-15" in str(req.url)
            return httpx.Response(
                200,
                json={"date": "2026-07-14", "base": "USD", "quote": "COP", "rate": 3924.50},
            )

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        rate = client.fetch_historical("USD", "COP", date(2026, 7, 15))
        # Effective date from API, not requested date
        assert rate.date == date(2026, 7, 14)
        assert rate.rate == Decimal("3924.50")

    def test_fetch_historical_empty_array_raises_RateNotFoundError(self) -> None:
        """200 with empty array (future date) raises RateNotFoundError, not FxUnavailableError."""
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"date": "2099-01-01", "base": "USD", "quote": "COP", "rate": []})

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        with pytest.raises(RateNotFoundError):
            client.fetch_historical("USD", "COP", date(2099, 1, 1))


@pytest.mark.unit
class TestListCurrencies:
    """T-B.4: FrankfurterClient.list_currencies."""

    def test_list_currencies_returns_dict(self) -> None:
        """list_currencies returns dict[str, str] from /currencies."""
        def handler(req: httpx.Request) -> httpx.Response:
            assert "/currencies" in str(req.url)
            return httpx.Response(
                200,
                json={"USD": "United States Dollar", "COP": "Colombian Peso"},
            )

        client = FrankfurterClient(transport=httpx.MockTransport(handler))
        result = client.list_currencies()
        assert result == {"USD": "United States Dollar", "COP": "Colombian Peso"}


@pytest.mark.unit
class TestListSupportedCurrencies:
    """T-B.5: fx.list_supported_currencies."""

    def test_list_supported_currencies_is_frozenset_of_12(self) -> None:
        """list_supported_currencies returns frozenset of exactly 12 ISO codes."""
        result = list_supported_currencies()
        assert isinstance(result, frozenset)
        assert len(result) == 12
        expected = {"COP", "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "MXN", "BRL", "INR", "CNY"}
        assert result == expected
