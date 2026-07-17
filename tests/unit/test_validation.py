"""Tests for domain validators."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from pyfintracker.exceptions import (
    CurrencyMismatchError,
    InvalidAccountName,
    InvalidAmount,
    InvalidCurrency,
    InvalidDate,
    InvalidDescription,
    TooFewPostings,
    UnbalancedTransaction,
    ZeroAmountPosting,
)
from pyfintracker.models import Account, Posting, Transaction
from pyfintracker.validation import (
    PER_CURRENCY_DECIMALS,
    quantize_for_currency,
    validate_account_name,
    validate_amount,
    validate_currency,
    validate_date,
    validate_description,
    validate_posting,
    validate_transaction,
)


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


@pytest.mark.unit
class TestPerCurrencyDecimals:
    """T-3.2: PER_CURRENCY_DECIMALS precision constants."""

    def test_cop_zero(self) -> None:
        """COP has 0 decimal places."""
        assert PER_CURRENCY_DECIMALS["COP"] == 0

    def test_jpy_zero(self) -> None:
        """JPY has 0 decimal places."""
        assert PER_CURRENCY_DECIMALS["JPY"] == 0

    def test_usd_two(self) -> None:
        """USD has 2 decimal places."""
        assert PER_CURRENCY_DECIMALS["USD"] == 2

    def test_eur_two(self) -> None:
        """EUR has 2 decimal places."""
        assert PER_CURRENCY_DECIMALS["EUR"] == 2

    def test_gbp_two(self) -> None:
        """GBP has 2 decimal places."""
        assert PER_CURRENCY_DECIMALS["GBP"] == 2

    def test_unknown_currency_raises_key_error(self) -> None:
        """Unknown currency raises KeyError."""
        with pytest.raises(KeyError):
            PER_CURRENCY_DECIMALS["ARS"]


@pytest.mark.unit
class TestQuantizeForCurrency:
    """T-3.3: quantize_for_currency(amount, currency) -> Decimal."""

    def test_cop_rounds_up(self) -> None:
        """COP: Decimal('99.99') → Decimal('100') (rounds up to 0 decimals)."""
        result = quantize_for_currency(Decimal("99.99"), "COP")
        assert result == Decimal("100")

    def test_usd_no_rounding_needed(self) -> None:
        """USD: Decimal('99.49') → Decimal('99.49') (no rounding)."""
        result = quantize_for_currency(Decimal("99.49"), "USD")
        assert result == Decimal("99.49")

    def test_usd_round_half_up(self) -> None:
        """USD: Decimal('99.456') → Decimal('99.46') (ROUND_HALF_UP)."""
        result = quantize_for_currency(Decimal("99.456"), "USD")
        assert result == Decimal("99.46")

    def test_negative_preserves_sign(self) -> None:
        """Negative: Decimal('-99.456') → Decimal('-99.46')."""
        result = quantize_for_currency(Decimal("-99.456"), "USD")
        assert result == Decimal("-99.46")

    def test_cop_sub_unit_rounds_to_zero(self) -> None:
        """COP: Decimal('0.001') → Decimal('0') (sub-unit rounds to zero)."""
        result = quantize_for_currency(Decimal("0.001"), "COP")
        assert result == Decimal("0")

    def test_unknown_currency_raises(self) -> None:
        """Unknown currency raises InvalidCurrency."""
        with pytest.raises(InvalidCurrency):
            quantize_for_currency(Decimal("1.00"), "XYZ")


@pytest.mark.unit
class TestValidateAmount:
    """T-3.4: validate_amount(value, currency) -> Decimal."""

    def test_decimal_pass_through(self) -> None:
        """Decimal('123.45') in USD returns Decimal('123.45')."""
        result = validate_amount(Decimal("123.45"), "USD")
        assert result == Decimal("123.45")

    def test_string_accepted(self) -> None:
        """String '123.45' in USD converts to Decimal('123.45')."""
        result = validate_amount("123.45", "USD")
        assert result == Decimal("123.45")

    def test_rejects_float(self) -> None:
        """Float raises InvalidAmount (float is NOT safe for money)."""
        with pytest.raises(InvalidAmount):
            validate_amount(123.45, "USD")

    def test_int_accepted(self) -> None:
        """Int 123 in COP returns Decimal('123') (quantized to 0 dp)."""
        result = validate_amount(123, "COP")
        assert result == Decimal("123")

    def test_non_numeric_string_raises(self) -> None:
        """Non-numeric string 'abc' raises InvalidAmount."""
        with pytest.raises(InvalidAmount):
            validate_amount("abc", "USD")

    def test_none_raises(self) -> None:
        """None raises InvalidAmount."""
        with pytest.raises(InvalidAmount):
            validate_amount(None, "USD")

    def test_nan_raises(self) -> None:
        """Decimal('NaN') raises InvalidAmount."""
        with pytest.raises(InvalidAmount):
            validate_amount(Decimal("NaN"), "USD")

    def test_infinity_raises(self) -> None:
        """Decimal('Infinity') raises InvalidAmount."""
        with pytest.raises(InvalidAmount):
            validate_amount(Decimal("Infinity"), "USD")

    def test_negative_infinity_raises(self) -> None:
        """Decimal('-Infinity') raises InvalidAmount."""
        with pytest.raises(InvalidAmount):
            validate_amount(Decimal("-Infinity"), "USD")

    def test_quantizes_usd(self) -> None:
        """'99.456' in USD → Decimal('99.46') (quantized to 2 dp)."""
        result = validate_amount("99.456", "USD")
        assert result == Decimal("99.46")

    def test_quantizes_cop(self) -> None:
        """'99.7' in COP → Decimal('100') (rounded up to 0 dp)."""
        result = validate_amount("99.7", "COP")
        assert result == Decimal("100")

    def test_empty_string_raises(self) -> None:
        """Empty string raises InvalidAmount."""
        with pytest.raises(InvalidAmount):
            validate_amount("", "USD")

    def test_unknown_currency_raises_invalid_currency(self) -> None:
        """Unknown currency raises InvalidCurrency."""
        with pytest.raises(InvalidCurrency):
            validate_amount("100", "XYZ")


# ── T-3.9: validate_amount edge cases (float, NaN, Inf, etc.) ────────────────


@pytest.mark.parametrize("value,currency", [
    (1.5, "COP"),           # float
    (0.0, "COP"),           # float zero
    (-1.5, "COP"),          # negative float
    (Decimal("NaN"), "COP"),
    (Decimal("Infinity"), "COP"),
    (Decimal("-Infinity"), "COP"),
    (Decimal("snan"), "COP"),   # signaling NaN
    ("", "COP"),            # empty string
    ("   ", "COP"),         # whitespace
    ("abc", "COP"),         # non-numeric
    (None, "COP"),          # None
    ("12,34", "COP"),       # comma decimal (not period)
    ("12.34.56", "COP"),    # double dot
    ({}, "COP"),            # dict
    ([], "COP"),            # list
])
def test_validate_amount_rejects_invalid(value: object, currency: str) -> None:
    """Each bad input raises InvalidAmount."""
    with pytest.raises(InvalidAmount):
        validate_amount(value, currency)


@pytest.mark.parametrize("value,currency,expected", [
    ("123", "COP", Decimal("123")),
    ("123.456", "COP", Decimal("123")),  # COP rounds to 0 places
    ("123.456", "USD", Decimal("123.46")),  # USD rounds HALF_UP
    ("123.454", "USD", Decimal("123.45")),  # USD rounds HALF_UP
    (1, "COP", Decimal("1")),               # int accepted
    ("0.001", "COP", Decimal("0")),         # COP rounds to 0
    ("0.001", "JPY", Decimal("0")),
    ("99.9999", "USD", Decimal("100.00")),  # USD rounds HALF_UP
    ("0", "COP", Decimal("0")),
    ("-123.456", "USD", Decimal("-123.46")),
])
def test_validate_amount_accepts_valid(value: object, currency: str, expected: Decimal) -> None:
    """Valid inputs return quantized Decimal."""
    result = validate_amount(value, currency)
    assert result == expected
    assert isinstance(result, Decimal)


# ── T-3.10: quantize_for_currency parametrized per currency ──────────────────


@pytest.mark.parametrize("amount,currency,expected", [
    # COP (0 decimals)
    (Decimal("99.5"), "COP", Decimal("100")),
    (Decimal("99.4"), "COP", Decimal("99")),
    (Decimal("0.1"), "COP", Decimal("0")),
    (Decimal("999999.99"), "COP", Decimal("1000000")),
    (Decimal("-99.5"), "COP", Decimal("-100")),
    # JPY (0 decimals)
    (Decimal("99.5"), "JPY", Decimal("100")),
    (Decimal("99.4"), "JPY", Decimal("99")),
    # USD (2 decimals)
    (Decimal("99.456"), "USD", Decimal("99.46")),
    (Decimal("99.454"), "USD", Decimal("99.45")),
    (Decimal("99.5"), "USD", Decimal("99.50")),
    (Decimal("0.005"), "USD", Decimal("0.01")),
    (Decimal("-0.005"), "USD", Decimal("-0.01")),
    # EUR (2 decimals)
    (Decimal("123.456"), "EUR", Decimal("123.46")),
    (Decimal("123.454"), "EUR", Decimal("123.45")),
    # GBP (2 decimals)
    (Decimal("9.9999"), "GBP", Decimal("10.00")),
    # Perfect precision preserved
    (Decimal("100"), "COP", Decimal("100")),
    (Decimal("100.00"), "USD", Decimal("100.00")),
    (Decimal("100.00"), "COP", Decimal("100")),
])
def test_quantize_for_currency(amount: Decimal, currency: str, expected: Decimal) -> None:
    """Parametrized: quantize_for_currency per currency."""
    result = quantize_for_currency(amount, currency)
    assert result == expected
    assert isinstance(result, Decimal)


def test_quantize_for_currency_unknown() -> None:
    """Unknown currency XXX raises InvalidCurrency."""
    with pytest.raises(InvalidCurrency):
        quantize_for_currency(Decimal("100"), "XXX")


def test_quantize_for_currency_invalid_code() -> None:
    """Lowercase invalid code 'xyz' raises InvalidCurrency."""
    with pytest.raises(InvalidCurrency):
        quantize_for_currency(Decimal("100"), "xyz")


# ── T-4.4: validate_posting ────────────────────────────────────────────────────


@pytest.mark.unit
class TestValidatePosting:
    """T-4.4: validate_posting(posting, account) currency coherence."""

    def test_matching_currency_ok(self) -> None:
        account = Account(name="Assets:Cash", currency="COP", kind="Assets", depth=1)
        posting = Posting(account_id=1, amount=Decimal("100"), currency="COP")
        validate_posting(posting, account)

    def test_mismatch_raises(self) -> None:
        account = Account(name="Assets:Cash", currency="COP", kind="Assets", depth=1)
        posting = Posting(account_id=1, amount=Decimal("100"), currency="USD")
        with pytest.raises(CurrencyMismatchError):
            validate_posting(posting, account)


# ── T-4.5: validate_transaction fail-fast ─────────────────────────────────────


@pytest.mark.unit
class TestValidateTransaction:
    """T-4.5: validate_transaction(txn, postings) fail-fast order."""

    def test_valid_transaction(self) -> None:
        txn = Transaction(date=date(2024, 1, 15), description="Test")
        postings = [
            Posting(account_id=1, amount=Decimal("100"), currency="COP"),
            Posting(account_id=2, amount=Decimal("-100"), currency="COP"),
        ]
        validate_transaction(txn, postings)

    def test_too_few_postings(self) -> None:
        txn = Transaction(date=date(2024, 1, 15), description="Test")
        with pytest.raises(TooFewPostings):
            validate_transaction(txn, [Posting(account_id=1, amount=Decimal("100"), currency="COP")])

    def test_no_postings(self) -> None:
        txn = Transaction(date=date(2024, 1, 15), description="Test")
        with pytest.raises(TooFewPostings):
            validate_transaction(txn, [])

    def test_zero_amount_posting(self) -> None:
        txn = Transaction(date=date(2024, 1, 15), description="Test")
        postings = [
            Posting(account_id=1, amount=Decimal("0"), currency="COP"),
            Posting(account_id=2, amount=Decimal("0"), currency="COP"),
        ]
        with pytest.raises(ZeroAmountPosting):
            validate_transaction(txn, postings)

    def test_currency_mismatch(self) -> None:
        txn = Transaction(date=date(2024, 1, 15), description="Test")
        postings = [
            Posting(account_id=1, amount=Decimal("100"), currency="COP"),
            Posting(account_id=2, amount=Decimal("-100"), currency="USD"),
        ]
        with pytest.raises(CurrencyMismatchError):
            validate_transaction(txn, postings)

    def test_unbalanced(self) -> None:
        txn = Transaction(date=date(2024, 1, 15), description="Test")
        postings = [
            Posting(account_id=1, amount=Decimal("100"), currency="COP"),
            Posting(account_id=2, amount=Decimal("-50"), currency="COP"),
        ]
        with pytest.raises(UnbalancedTransaction):
            validate_transaction(txn, postings)

    def test_fail_fast_count(self) -> None:
        txn = Transaction(date=date(2024, 1, 15), description="Test")
        with pytest.raises(TooFewPostings):
            validate_transaction(txn, [Posting(account_id=1, amount=Decimal("0"), currency="COP")])


@pytest.mark.unit
class TestValidateDescription:
    """T-4.5: validate_description(desc) -> str."""

    def test_too_long(self) -> None:
        with pytest.raises(InvalidDescription):
            validate_description("a" * 257)

    def test_ok(self) -> None:
        assert validate_description("Buy coffee") == "Buy coffee"

    def test_empty_ok(self) -> None:
        assert validate_description("") == ""
