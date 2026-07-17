"""Domain validators and exception tree."""

from __future__ import annotations

import re
from datetime import date

from pyfintracker.exceptions import InvalidAccountName, InvalidCurrency, InvalidDate

ACCOUNT_NAME_RE: re.Pattern[str] = re.compile(
    r"^[A-Z][a-z]+:[A-Z][\w-]+(:[A-Z][\w-]+)?$"
)

VALID_CURRENCIES: frozenset[str] = frozenset({"COP", "USD", "EUR", "GBP", "JPY"})


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


__all__ = [
    "ACCOUNT_NAME_RE",
    "VALID_CURRENCIES",
    "validate_account_name",
    "validate_currency",
    "validate_date",
]
