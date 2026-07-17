"""Tests for domain validators."""

from __future__ import annotations

from datetime import date

import pytest

from pyfintracker.exceptions import InvalidAccountName, InvalidCurrency, InvalidDate
from pyfintracker.validation import validate_account_name, validate_currency, validate_date


@pytest.mark.unit
class TestValidateAccountName:
    """T-2.3: validate_account_name(name) -> str."""

    def test_valid_assets_checking(self) -> None:
        """Assets:Checking is valid."""
        result = validate_account_name("Assets:Checking")
        assert result == "Assets:Checking"

    def test_valid_three_levels(self) -> None:
        """Expenses:Food:Groceries (3 levels) is valid."""
        result = validate_account_name("Expenses:Food:Groceries")
        assert result == "Expenses:Food:Groceries"

    def test_valid_income_salary(self) -> None:
        """Income:Salary is valid."""
        result = validate_account_name("Income:Salary")
        assert result == "Income:Salary"

    def test_invalid_empty(self) -> None:
        """Empty string is invalid."""
        with pytest.raises(InvalidAccountName):
            validate_account_name("")

    def test_invalid_no_colon(self) -> None:
        """Single component without colon is invalid (no root)."""
        with pytest.raises(InvalidAccountName):
            validate_account_name("Assets")

    def test_invalid_lowercase_root(self) -> None:
        """Root type must start uppercase."""
        with pytest.raises(InvalidAccountName):
            validate_account_name("assets:Checking")

    def test_invalid_lowercase_subname(self) -> None:
        """Subname must start uppercase."""
        with pytest.raises(InvalidAccountName):
            validate_account_name("Assets:checking")

    def test_invalid_four_levels(self) -> None:
        """More than 3 levels is invalid."""
        with pytest.raises(InvalidAccountName):
            validate_account_name("Assets:Checking:More:Extra")

    def test_invalid_subname_starting_with_digits(self) -> None:
        """Subname starting with digits is invalid (must start [A-Z])."""
        with pytest.raises(InvalidAccountName):
            validate_account_name("Assets:123")

    def test_invalid_subname_with_special_chars(self) -> None:
        """Subname with special chars beyond hyphen is invalid."""
        with pytest.raises(InvalidAccountName):
            validate_account_name("Assets:Checking@Bank")

    def test_returns_canonical(self) -> None:
        """Returns canonical form (unchanged for already-valid)."""
        result = validate_account_name("Income:Freelance")
        assert result == "Income:Freelance"


@pytest.mark.unit
class TestValidateCurrency:
    """T-2.4: validate_currency(code) -> str."""

    def test_valid_cop(self) -> None:
        """COP is valid."""
        result = validate_currency("COP")
        assert result == "COP"

    def test_valid_usd(self) -> None:
        """USD is valid."""
        result = validate_currency("USD")
        assert result == "USD"

    def test_valid_eur(self) -> None:
        """EUR is valid."""
        result = validate_currency("EUR")
        assert result == "EUR"

    def test_valid_gbp(self) -> None:
        """GBP is valid."""
        result = validate_currency("GBP")
        assert result == "GBP"

    def test_valid_jpy(self) -> None:
        """JPY is valid."""
        result = validate_currency("JPY")
        assert result == "JPY"

    def test_returns_uppercase(self) -> None:
        """Returns uppercase even if input is lowercase."""
        result = validate_currency("cop")
        assert result == "COP"

    def test_invalid_lowercase(self) -> None:
        """Lowercase 'ars' raises InvalidCurrency."""
        with pytest.raises(InvalidCurrency):
            validate_currency("ars")

    def test_invalid_btc(self) -> None:
        """BTC is not in the supported list."""
        with pytest.raises(InvalidCurrency):
            validate_currency("BTC")

    def test_invalid_too_short(self) -> None:
        """Two-letter code raises InvalidCurrency."""
        with pytest.raises(InvalidCurrency):
            validate_currency("US")

    def test_invalid_empty(self) -> None:
        """Empty string raises InvalidCurrency."""
        with pytest.raises(InvalidCurrency):
            validate_currency("")


@pytest.mark.unit
class TestValidateDate:
    """T-2.5: validate_date(d) -> date."""

    def test_valid_iso_string(self) -> None:
        """YYYY-MM-DD string parses to correct date."""
        result = validate_date("2026-07-15")
        assert result == date(2026, 7, 15)

    def test_valid_date_object_pass_through(self) -> None:
        """date object passes through unchanged."""
        d = date(2026, 7, 15)
        result = validate_date(d)
        assert result is d

    def test_invalid_empty_string(self) -> None:
        """Empty string raises InvalidDate."""
        with pytest.raises(InvalidDate):
            validate_date("")

    def test_invalid_wrong_format(self) -> None:
        """DD-MM-YYYY format raises InvalidDate."""
        with pytest.raises(InvalidDate):
            validate_date("15-07-2026")

    def test_invalid_not_a_date(self) -> None:
        """Non-date string raises InvalidDate."""
        with pytest.raises(InvalidDate):
            validate_date("not-a-date")

    def test_invalid_impossible_date(self) -> None:
        """Impossible date like Feb 30 raises InvalidDate."""
        with pytest.raises(InvalidDate):
            validate_date("2026-02-30")

    def test_future_date_allowed(self) -> None:
        """Future date is allowed per design D5."""
        result = validate_date("2099-12-31")
        assert result == date(2099, 12, 31)
