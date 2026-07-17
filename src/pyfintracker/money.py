"""Money dataclass — validated Decimal + currency pair.

``Money`` is a frozen dataclass that wraps ``validate_amount`` and
``validate_currency`` in its ``__post_init__``, producing a validated,
quantized monetary value that is safe for bookkeeping.

Usage::

    from pyfintracker.money import Money

    salary = Money("5000000", "COP")   # quantized to 0 dp
    tax    = Money("1234.56", "USD")   # quantized to 2 dp
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from pyfintracker.validation import validate_amount, validate_currency


@dataclass(frozen=True)
class Money:
    """A validated monetary amount paired with a currency code.

    Attributes:
        value:  Quantized Decimal amount (per-currency precision).
        currency:  ISO 4217 uppercase currency code (default COP).

    Raises:
        InvalidAmount: if ``value`` is float, NaN, Inf, or non-numeric.
        InvalidCurrency: if ``currency`` is not in the supported set.
    """

    value: Decimal | str | int
    currency: str = "COP"

    def __post_init__(self) -> None:
        """Validate and quantize the amount in place.

        Uses ``object.__setattr__`` because the dataclass is frozen.
        """
        currency = validate_currency(self.currency)
        amount = validate_amount(self.value, currency)
        object.__setattr__(self, "value", amount)
        object.__setattr__(self, "currency", currency)

    def __str__(self) -> str:
        """Locale-style formatted amount with currency suffix.

        Uses ``{:,}`` for thousands separators and per-currency decimal
        precision (0 dp for COP/JPY, 2 dp for USD/EUR/GBP).
        """
        from pyfintracker.validation import PER_CURRENCY_DECIMALS

        precision = PER_CURRENCY_DECIMALS[self.currency]
        formatted = f"{self.value:,.{precision}f}"
        return f"{formatted} {self.currency}"


__all__ = ["Money"]
