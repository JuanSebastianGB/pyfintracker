"""FinanceError exception tree for pyfintracker.

Every public exception has a ``.code`` attribute mapping to the CLI exit code
(design §4, spec B2):

- 0 = ok
- 1 = validation / invariant error
- 2 = runtime error
- 3 = configuration error
- 130 = abort (not used here, handled in CLI)
"""

# ruff: noqa: N818 — exception names match design doc (no Error suffix)

from __future__ import annotations


class FinanceError(Exception):
    """Base exception for all pyfintracker errors."""

    code: int = 1

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self._default_message()
        super().__init__(self.message)

    @classmethod
    def _default_message(cls) -> str:
        return cls.__name__


# ── Validation errors (exit 1) ────────────────────────────────────────────


class ValidationError(FinanceError):
    """Base for input-validation errors."""


class InvalidAccountName(ValidationError):
    """Account name fails regex or PascalCase normalization."""


class InvalidCurrency(ValidationError):
    """Currency code is not a valid ISO 4217 3-letter code."""


class InvalidDate(ValidationError):
    """Date string is not valid ISO YYYY-MM-DD."""


class InvalidAmount(ValidationError):
    """Amount is float, NaN, Inf, or otherwise invalid."""


class CurrencyMismatchError(ValidationError):
    """Posting currency does not match its account's currency."""


class TooFewPostings(ValidationError):
    """A transaction needs at least 2 postings."""


class ZeroAmountPosting(ValidationError):
    """A posting must have a non-zero amount."""


class InvalidDescription(ValidationError):
    """Description exceeds maximum length."""


class UnbalancedTransaction(ValidationError):
    """Sum of postings does not equal zero."""


# ── Identity / lookup errors (exit 1) ─────────────────────────────────────


class AccountNotFoundError(FinanceError):
    """Referenced account does not exist."""


# ── Initialization errors (exit 3) ────────────────────────────────────────


class NotInitializedError(FinanceError):
    """Operation requires an initialized database."""

    code = 3


class ConfigError(FinanceError):
    """Configuration error (file, env, or flag)."""

    code = 3


# ── FX errors (exit 4/5/6) ──────────────────────────────────────────────────


class RateNotFoundError(FinanceError):
    """FX rate not found for requested currency pair or date."""

    code = 4


class InvalidCurrencyError(FinanceError):
    """FX-specific currency error (distinct from InvalidCurrency, exit 1)."""

    code = 5


class FxUnavailableError(FinanceError):
    """FX service unavailable (network error, upstream 5xx)."""

    code = 6


# ── Runtime errors (exit 2) ────────────────────────────────────────────────


class ReplRequiresTTYError(FinanceError):
    """REPL mode requires an interactive terminal."""

    code = 2


__all__ = [
    "AccountNotFoundError",
    "ConfigError",
    "CurrencyMismatchError",
    "FinanceError",
    "FxUnavailableError",
    "InvalidAccountName",
    "InvalidAmount",
    "InvalidCurrency",
    "InvalidCurrencyError",
    "InvalidDate",
    "InvalidDescription",
    "NotInitializedError",
    "RateNotFoundError",
    "ReplRequiresTTYError",
    "TooFewPostings",
    "UnbalancedTransaction",
    "ValidationError",
    "ZeroAmountPosting",
]
