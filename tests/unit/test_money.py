"""Tests for the Money dataclass — T-3.5.

Money is a frozen dataclass pairing a validated Decimal amount with
a currency code.  It wraps validate_amount + validate_currency.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from pyfintracker.exceptions import InvalidAmount, InvalidCurrency
from pyfintracker.money import Money


@pytest.mark.unit
class TestMoney:
    """T-3.5: Money(value, currency) frozen dataclass."""

    def test_valid(self) -> None:
        """Basic valid Money with Decimal value."""
        m = Money(value=Decimal("50000"), currency="COP")
        assert m.value == Decimal("50000")
        assert m.currency == "COP"

    def test_default_currency(self) -> None:
        """Default currency is COP."""
        m = Money(value=Decimal("50000"))
        assert m.currency == "COP"

    def test_accepts_string_value(self) -> None:
        """String value is converted to Decimal."""
        m = Money(value="50000", currency="COP")
        assert m.value == Decimal("50000")

    def test_accepts_int_value(self) -> None:
        """Int value is converted to Decimal."""
        m = Money(value=50000, currency="COP")
        assert m.value == Decimal("50000")

    def test_quantizes_cop(self) -> None:
        """COP rounds to integer (0 dp)."""
        m = Money(value=Decimal("99.7"), currency="COP")
        assert m.value == Decimal("100")

    def test_quantizes_usd(self) -> None:
        """USD rounds to 2 decimal places."""
        m = Money(value=Decimal("99.456"), currency="USD")
        assert m.value == Decimal("99.46")

    def test_rejects_float(self) -> None:
        """Float values raise InvalidAmount."""
        with pytest.raises(InvalidAmount):
            Money(value=50000.50, currency="COP")

    def test_rejects_nan(self) -> None:
        """Decimal('NaN') raises InvalidAmount."""
        with pytest.raises(InvalidAmount):
            Money(value=Decimal("NaN"), currency="COP")

    def test_rejects_infinity(self) -> None:
        """Decimal('Infinity') raises InvalidAmount."""
        with pytest.raises(InvalidAmount):
            Money(value=Decimal("Infinity"), currency="COP")

    def test_rejects_unknown_currency(self) -> None:
        """Unknown currency code raises InvalidCurrency."""
        with pytest.raises(InvalidCurrency):
            Money(value=Decimal("50000"), currency="XXX")

    def test_rejects_invalid_currency(self) -> None:
        """Lowercase currency code raises InvalidCurrency."""
        with pytest.raises(InvalidCurrency):
            Money(value=Decimal("50000"), currency="ars")

    def test_str_cop(self) -> None:
        """COP Money displays without decimals."""
        m = Money(value=Decimal("50000"), currency="COP")
        assert str(m) == "50,000 COP"

    def test_str_usd(self) -> None:
        """USD Money displays with 2 decimals."""
        m = Money(value=Decimal("1234.56"), currency="USD")
        assert str(m) == "1,234.56 USD"

    def test_str_negative(self) -> None:
        """Negative COP displays with leading minus."""
        m = Money(value=Decimal("-100000"), currency="COP")
        assert str(m) == "-100,000 COP"

    def test_frozen(self) -> None:
        """Frozen dataclass raises AttributeError on mutation."""
        m = Money(value=Decimal("100"), currency="COP")
        with pytest.raises(AttributeError):
            m.value = Decimal("200")  # type: ignore[misc]
