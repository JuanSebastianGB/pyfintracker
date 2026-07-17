"""Tests for the FinanceError exception tree."""

import pytest

from pyfintracker.exceptions import (
    AccountNotFoundError,
    ConfigError,
    CurrencyMismatchError,
    FinanceError,
    InvalidAccountName,
    InvalidAmount,
    InvalidCurrency,
    InvalidDate,
    NotInitializedError,
    ReplRequiresTTYError,
    TooFewPostings,
    UnbalancedTransaction,
    ValidationError,
    ZeroAmountPosting,
)

EXIT_CODE_MAP: dict[type[FinanceError], int] = {
    ValidationError: 1,
    InvalidAccountName: 1,
    InvalidCurrency: 1,
    InvalidDate: 1,
    InvalidAmount: 1,
    CurrencyMismatchError: 1,
    TooFewPostings: 1,
    ZeroAmountPosting: 1,
    UnbalancedTransaction: 1,
    AccountNotFoundError: 1,
    NotInitializedError: 3,
    ConfigError: 3,
    ReplRequiresTTYError: 2,
}

ALL_EXCEPTIONS = list(EXIT_CODE_MAP.keys())

EXCEPTION_PARENT: dict[type[FinanceError], type[FinanceError] | None] = {
    ValidationError: FinanceError,
    InvalidAccountName: ValidationError,
    InvalidCurrency: ValidationError,
    InvalidDate: ValidationError,
    InvalidAmount: ValidationError,
    CurrencyMismatchError: ValidationError,
    TooFewPostings: ValidationError,
    ZeroAmountPosting: ValidationError,
    UnbalancedTransaction: ValidationError,
    AccountNotFoundError: FinanceError,
    NotInitializedError: FinanceError,
    ConfigError: FinanceError,
    ReplRequiresTTYError: FinanceError,
}


@pytest.mark.unit
@pytest.mark.parametrize("exc_cls", ALL_EXCEPTIONS)
def test_is_finance_error_subclass(exc_cls: type[FinanceError]) -> None:
    """Every exception is a FinanceError."""
    assert issubclass(exc_cls, FinanceError)


@pytest.mark.unit
@pytest.mark.parametrize("exc_cls", ALL_EXCEPTIONS)
def test_exit_code_mapping(exc_cls: type[FinanceError]) -> None:
    """Every exception has the correct exit code via .code."""
    instance = exc_cls()
    expected = EXIT_CODE_MAP[exc_cls]
    assert instance.code == expected, f"{exc_cls.__name__}: expected {expected}, got {instance.code}"


@pytest.mark.unit
@pytest.mark.parametrize("exc_cls, parent", EXCEPTION_PARENT.items())
def test_inheritance_chain(exc_cls: type[FinanceError], parent: type[FinanceError]) -> None:
    """Each exception is a direct or indirect subclass of its parent."""
    assert issubclass(exc_cls, parent)
