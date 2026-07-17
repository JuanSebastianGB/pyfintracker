"""Domain validators and exception tree."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

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

ACCOUNT_NAME_RE: re.Pattern[str] = re.compile(
    r"^[A-Z][a-z]+:[A-Z][\w-]+(:[A-Z][\w-]+)?$"
)

VALID_CURRENCIES: frozenset[str] = frozenset({"COP", "USD", "EUR", "GBP", "JPY"})

# Per-currency decimal precision (from proposal — contract f)
# Currencies with 0 decimals: COP, JPY
# Currencies with 2 decimals: USD, EUR, GBP
PER_CURRENCY_DECIMALS: dict[str, int] = {
    "COP": 0,
    "JPY": 0,
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
}


def validate_account_name(name: str) -> str:
    """Validate and canonicalize an account name.

    Rules:
    - Must match regex: ^[A-Z][a-z]+:[A-Z][\\w-]+(:[A-Z][\\w-]+)?$
    - First component must be a valid root type (no enforcement here —
      kind check separate)
    - Returns the name unchanged (caller normalizes at CLI boundary)

    Raises:
        InvalidAccountName: if the name doesn't match the pattern
    """
    if not ACCOUNT_NAME_RE.match(name):
        raise InvalidAccountName(
            f"Invalid account name: '{name}'. "
            f"Must match pattern: Type:Subname[:Subname] "
            f"(e.g., Assets:Checking, Expenses:Food:Groceries)"
        )
    return name


def validate_currency(code: str) -> str:
    """Validate a currency ISO 4217 code (Wave 1: COP/USD/EUR/GBP/JPY only)."""
    upper = code.upper()
    if upper not in VALID_CURRENCIES:
        raise InvalidCurrency(
            f"Unsupported currency: '{code}'. "
            f"Wave 1 supports: {', '.join(sorted(VALID_CURRENCIES))}"
        )
    return upper


def validate_date(d: str | date) -> date:
    """Validate and parse a date string in ISO format YYYY-MM-DD.

    Accepts:
    - str in ISO format
    - datetime.date objects (pass-through)

    Raises:
        InvalidDate: if the value can't be parsed or is not a valid calendar date
    """
    if isinstance(d, date):
        return d

    if not isinstance(d, str) or d.strip() == "":
        raise InvalidDate(f"Invalid date: '{d}'. Must be YYYY-MM-DD format.")

    d_stripped = d.strip()
    try:
        parsed = date.fromisoformat(d_stripped)
    except (ValueError, TypeError):
        raise InvalidDate(f"Invalid date: '{d}'. Must be YYYY-MM-DD format.") from None

    return parsed


def quantize_for_currency(amount: Decimal, currency: str) -> Decimal:
    """Round a Decimal amount to per-currency precision using ROUND_HALF_UP.

    Args:
        amount: Decimal amount to quantize (can be any precision).
        currency: ISO 4217 currency code (must be in PER_CURRENCY_DECIMALS).

    Returns:
        Quantized Decimal with per-currency precision.

    Raises:
        InvalidCurrency: if currency not in PER_CURRENCY_DECIMALS.
    """
    if currency not in PER_CURRENCY_DECIMALS:
        raise InvalidCurrency(f"Unknown currency: {currency}")

    precision = PER_CURRENCY_DECIMALS[currency]
    # Build quantizer: 1 (0 dp), 0.01 (2 dp), 0.001 (3 dp), etc.
    quantizer = Decimal("1").scaleb(-precision)
    return amount.quantize(quantizer, rounding=ROUND_HALF_UP)


def validate_amount(value: object, currency: str) -> Decimal:
    """Validate and convert a monetary amount to a quantized Decimal.

    Accepts: Decimal, str, int.
    REJECTS: float, None, NaN, Infinity, -Infinity, non-numeric strings.

    Quantizes per currency precision (e.g., COP rounds to integer, USD to 2 dp).

    Raises:
        InvalidAmount: if the value is not a valid money amount.
        InvalidCurrency: if the currency is not in PER_CURRENCY_DECIMALS.
    """
    if value is None:
        raise InvalidAmount("Amount cannot be None.")

    if isinstance(value, float):
        raise InvalidAmount(
            "Float values are not allowed for monetary amounts. Use Decimal or string."
        )

    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise InvalidAmount("Amount string cannot be empty.")

    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise InvalidAmount(f"Cannot convert '{value!r}' to Decimal.") from None

    if not amount.is_finite():
        raise InvalidAmount(f"Amount must be finite, got '{amount}'.")

    return quantize_for_currency(amount, currency)


def validate_posting(posting: Posting, account: Account) -> None:
    """Verify posting currency matches account currency (D6)."""
    if posting.currency != account.currency:
        raise CurrencyMismatchError(
            f"Posting currency '{posting.currency}' doesn't match account "
            f"'{account.name}' currency '{account.currency}'"
        )


def validate_transaction(txn: Transaction, postings: Sequence[Posting]) -> None:
    """Validate a transaction's postings in fail-fast order.

    Order: count >= 2 -> no zero-amount -> single currency -> sum=0.
    """
    if len(postings) < 2:
        raise TooFewPostings(
            f"Transaction needs at least 2 postings, got {len(postings)}"
        )

    for p in postings:
        if p.amount == Decimal("0"):
            raise ZeroAmountPosting(
                f"Posting for account_id={p.account_id} has zero amount"
            )

    currencies = {p.currency for p in postings}
    if len(currencies) > 1:
        raise CurrencyMismatchError(
            f"All postings must share the same currency, got {currencies}"
        )

    total = sum(p.amount for p in postings)
    if total != Decimal("0"):
        raise UnbalancedTransaction(
            f"Postings sum to {total}, must sum to 0"
        )


def validate_description(desc: str) -> str:
    """Validate description length."""
    if len(desc) > 256:
        raise InvalidDescription(f"Description too long: {len(desc)} chars (max 256)")
    return desc


__all__ = [
    "ACCOUNT_NAME_RE",
    "PER_CURRENCY_DECIMALS",
    "VALID_CURRENCIES",
    "quantize_for_currency",
    "validate_account_name",
    "validate_amount",
    "validate_currency",
    "validate_date",
    "validate_description",
    "validate_posting",
    "validate_transaction",
]
