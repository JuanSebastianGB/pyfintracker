"""FX rate module — Frankfurter v2 client + cache orchestrator.

Provides:
    FrankfurterClient — HTTP client for Frankfurter.dev v2 API.
    get_rate — cache-first rate lookup with TTL, inverse, fallback.
    list_supported_currencies — the 12-currency allowlist.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

import httpx

from pyfintracker.exceptions import (
    FxUnavailableError,
    InvalidCurrencyError,
    RateNotFoundError,
)
from pyfintracker.models import Rate
from pyfintracker.repository import get_cached_rate, upsert_rate
from pyfintracker.validation import PER_CURRENCY_DECIMALS

if TYPE_CHECKING:

    from sqlalchemy import Connection

DEFAULT_TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0)


class FrankfurterClient:
    """HTTP client for the Frankfurter v2 FX rate API.

    Base URL is pinned to v2 (no env override). Transport injectable for tests.
    """

    BASE_URL: str = "https://api.frankfurter.dev/v2"

    def __init__(
        self,
        *,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            timeout=timeout,
            transport=transport,
        )

    def fetch_latest(self, from_ccy: str, to_ccy: str) -> Rate:
        """Fetch the latest rate for a currency pair.

        GET /v2/rate/{from}/{to}

        Raises:
            RateNotFoundError: on 404 or missing/zero/negative rate.
            InvalidCurrencyError: on 422 invalid currency.
            FxUnavailableError: on network errors or 5xx.
        """
        return self._fetch("rate", from_ccy, to_ccy)

    def fetch_historical(self, from_ccy: str, to_ccy: str, on: date) -> Rate:
        """Fetch a historical rate for a currency pair on a specific date.

        GET /v2/rate/{from}/{to}?date={on}

        Raises:
            RateNotFoundError: on 404, empty response, or missing/zero/negative rate.
            InvalidCurrencyError: on 422 invalid currency.
            FxUnavailableError: on network errors or 5xx.
        """
        return self._fetch("rate", from_ccy, to_ccy, date=on)

    def list_currencies(self) -> dict[str, str]:
        """Fetch all available currencies from Frankfurter.

        GET /v2/currencies
        """
        # ponytail: no retry for listing — one-shot, caller handles errors
        try:
            resp = self._client.get("/currencies")
            resp.raise_for_status()
            return dict(resp.json())
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 422:
                raise InvalidCurrencyError(str(exc.response.json().get("message", ""))) from None
            raise FxUnavailableError(str(exc)) from None
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise FxUnavailableError(str(exc)) from None

    def _fetch(
        self,
        endpoint: str,
        from_ccy: str,
        to_ccy: str,
        date: date | None = None,
    ) -> Rate:
        """Internal: perform GET and parse response to Rate."""
        params: dict[str, str] = {"base": from_ccy, "quote": to_ccy}
        if date is not None:
            params["date"] = str(date)

        try:
            resp = self._client.get(f"/{endpoint}/{from_ccy}/{to_ccy}", params=params if date else {})
            # ponytail: single call, no retry for normal errors
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            try:
                msg = exc.response.json().get("message", "")
            except Exception:
                msg = ""
            if status == 404:
                raise RateNotFoundError(msg) from None
            if status == 422:
                # Check if it's an invalid currency vs invalid date
                if "invalid currency" in msg.lower():
                    raise InvalidCurrencyError(msg) from None
                raise RateNotFoundError(msg) from None
            raise FxUnavailableError(msg or str(exc)) from None
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise FxUnavailableError(str(exc)) from None

        return _parse_rate_response(data, from_ccy, to_ccy)


def _parse_rate_response(data: dict[str, object], from_ccy: str, to_ccy: str) -> Rate:
    """Parse Frankfurter JSON response into a Rate dataclass."""
    raw_rate = data.get("rate")
    # ponytail: rate may be 0, empty list, or missing — all are "not found"
    if raw_rate is None or raw_rate == [] or raw_rate == 0 or raw_rate == "0":
        raise RateNotFoundError(f"No rate found for {from_ccy}→{to_ccy}")

    effective_date = data.get("date", "")
    try:
        parsed_date = date.fromisoformat(effective_date) if isinstance(effective_date, str) else date.today()
    except (ValueError, TypeError):
        parsed_date = date.today()

    if isinstance(raw_rate, list):
        raise RateNotFoundError(f"No rate found for {from_ccy}→{to_ccy}")

    rate_val = Decimal(str(raw_rate))
    if rate_val <= 0:
        raise RateNotFoundError(f"Invalid (non-positive) rate: {raw_rate}")

    return Rate(
        date=parsed_date,
        from_ccy=from_ccy,
        to_ccy=to_ccy,
        rate=rate_val,
        source="frankfurter",
    )


def list_supported_currencies() -> frozenset[str]:
    """Return the curated allowlist of supported currency ISO codes."""
    return frozenset(PER_CURRENCY_DECIMALS)


def get_rate(
    from_ccy: str,
    to_ccy: str,
    on: date | None = None,
    *,
    _client: FrankfurterClient | None = None,
    _conn: Connection | None = None,
) -> Rate:
    """Get an FX rate with cache-first orchestration.

    Orchestration order:
        1. Same-currency identity (no I/O).
        2. Cache lookup (direct then inverse).
        3. Fetch from Frankfurter (if latest and TTL expired or not cached).
        4. Stale-fallback: if fetch fails and cache exists, return cache + warning.

    Args:
        from_ccy: Source currency ISO code.
        to_ccy: Target currency ISO code.
        on: Effective date (None = latest). Historical dates use cache regardless of age.
        _client: Injected FrankfurterClient (for testing).
        _conn: Injected DB connection (for testing). If None, uses a default engine.

    Returns:
        Rate with the exchange rate.

    Raises:
        RateNotFoundError: if rate not found for pair/date (exit 4).
        InvalidCurrencyError: if currency not supported by Frankfurter (exit 5).
        FxUnavailableError: if network unavailable and no cache fallback (exit 6).
    """
    # ponytail: import here to avoid circular at module level
    from pyfintracker.db import make_engine

    conn = _conn
    if conn is None:
        # Default engine — only used outside tests
        from pyfintracker.config import load_settings

        settings = load_settings()
        engine = make_engine(f"sqlite:///{settings.db_path}")

        conn = engine.connect()

    client = _client or FrankfurterClient()
    now = datetime.now(UTC)
    today = date.today()

    # ── helpers ───────────────────────────────────────────────────────────_
    # ponytail: return as int seconds — float stays out of the money pipeline
    def _rate_age(cached_rate: Rate) -> int | None:
        """Return age in seconds, handling naive/aware datetime mismatch."""
        ft = cached_rate.fetched_at
        if ft is None:
            return None
        # SQLite stores naive UTC — treat as UTC if no tz
        if ft.tzinfo is None:
            ft = ft.replace(tzinfo=UTC)
        return int((now - ft).total_seconds())

    # --- 1. Same-currency identity ---
    if from_ccy == to_ccy:
        return Rate(date=today, from_ccy=from_ccy, to_ccy=to_ccy, rate=Decimal("1"), source="identity")

    # --- 2. Future date rejection ---
    if on is not None and on > today:
        raise RateNotFoundError(f"No rate available for future date {on}")

    # --- 3. Cache lookup (direct) ---
    lookup_date = on or today
    cached = get_cached_rate(conn, from_ccy, to_ccy, lookup_date)

    # --- 4. Inverse cache lookup ---
    if cached is None:
        inverse = get_cached_rate(conn, to_ccy, from_ccy, lookup_date)
        if inverse is not None and inverse.rate > 0:
            inverse_rate = Decimal("1") / inverse.rate
            from pyfintracker.validation import PER_CURRENCY_DECIMALS
            precision = PER_CURRENCY_DECIMALS.get(from_ccy, 2)
            quantizer = Decimal("1").scaleb(-precision)
            inverted = inverse_rate.quantize(quantizer, rounding=ROUND_HALF_UP)
            # Return as-if direct (from_ccy→to_ccy)
            cached = Rate(
                date=inverse.date,
                from_ccy=from_ccy,
                to_ccy=to_ccy,
                rate=inverted,
                source=inverse.source,
                fetched_at=inverse.fetched_at,
            )

    # --- 5. Historical: cached forever ---
    if on is not None and cached is not None:
        return cached

    # --- 6. Latest: TTL check ---
    if on is None and cached is not None:
        age_sec = _rate_age(cached)
        if age_sec is not None and age_sec < 24 * 3600:
            return cached

    # --- 7. Try to fetch from Frankfurter ---
    try:
        if on is not None:
            fresh = client.fetch_historical(from_ccy, to_ccy, on)
        else:
            fresh = client.fetch_latest(from_ccy, to_ccy)
    except (FxUnavailableError, httpx.ConnectError, httpx.TimeoutException):
        # Network failure — fall back to stale cache if available
        if cached is not None:
            _warn_stale(cached)
            return cached
        raise FxUnavailableError(
            f"FX service unavailable and no cached rate for {from_ccy}→{to_ccy}"
        ) from None

    # --- 8. Upsert cache ---
    upsert_rate(conn, fresh)

    return fresh


def convert(
    amount: Decimal,
    from_ccy: str,
    to_ccy: str,
    *,
    on: date | None = None,
    rate: Decimal | None = None,
    _client: FrankfurterClient | None = None,
    _conn: Connection | None = None,
) -> Decimal:
    """Convert an amount from one currency to another.

    Same-currency fast-path (no I/O). Cross-currency calls ``get_rate``
    (which may hit cache or Frankfurter), multiplies, quantizes to target
    precision via ``ROUND_HALF_UP``.

    Args:
        amount: Decimal amount to convert.
        from_ccy: Source currency ISO code.
        to_ccy: Target currency ISO code.
        on: Effective date (None = latest).
        rate: Pre-resolved rate (for testing — bypasses get_rate).
        _client: Injected FrankfurterClient (for testing).
        _conn: Injected DB connection (for testing).

    Returns:
        Decimal amount in ``to_ccy``, quantized to per-currency precision.
    """
    from pyfintracker.validation import quantize_for_currency

    # Same-currency fast path — no rate needed
    if from_ccy == to_ccy:
        return quantize_for_currency(amount, to_ccy)

    # Use explicit rate (for testing) or fetch via get_rate
    if rate is None:
        r = get_rate(from_ccy, to_ccy, on=on, _client=_client, _conn=_conn)
        rate_val = r.rate
    else:
        rate_val = rate

    converted = amount * rate_val
    return quantize_for_currency(converted, to_ccy)


def _warn_stale(cached: Rate) -> None:
    """Emit a stderr warning about using a stale cached rate."""
    ts = cached.fetched_at
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "unknown"
    print(f"warning: using cached rate from {ts_str} (network unavailable)", file=sys.stderr)


__all__ = [
    "DEFAULT_TIMEOUT",
    "FrankfurterClient",
    "convert",
    "get_rate",
    "list_supported_currencies",
]
