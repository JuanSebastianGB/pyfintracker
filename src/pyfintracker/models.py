"""Frozen dataclass entities for pyfintracker."""

from __future__ import annotations

import calendar
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

ROOT_TYPES: frozenset[str] = frozenset({"Assets", "Liabilities", "Equity", "Income", "Expenses"})


@dataclass(frozen=True)
class Account:
    """A single account in the chart of accounts.

    Frozen dataclass — fields are immutable after construction.
    Validation in ``__post_init__`` enforces domain invariants.
    """

    id: int | None = None
    name: str = ""
    parent_id: int | None = None
    currency: str = "COP"
    depth: int = 0
    kind: str = ""
    is_archived: bool = False

    def __post_init__(self) -> None:
        if self.name == "":
            raise ValueError("Account name cannot be empty")
        if self.kind not in ROOT_TYPES:
            raise ValueError(f"Invalid kind: {self.kind}. Must be one of {sorted(ROOT_TYPES)}")
        if not (0 <= self.depth <= 2):
            raise ValueError(f"Depth must be 0-2, got {self.depth}")

    def to_row(self) -> dict[str, object]:
        """Convert to dict for SQLAlchemy Core insertion."""
        d: dict[str, object] = {
            "name": self.name,
            "currency": self.currency,
            "depth": self.depth,
            "kind": self.kind,
            "is_archived": 1 if self.is_archived else 0,
        }
        if self.id is not None:
            d["id"] = self.id
        if self.parent_id is not None:
            d["parent_id"] = self.parent_id
        return d

    @staticmethod
    def from_row(row: Any) -> Account:
        """Reconstruct from a SQLAlchemy result row (RowMapping or tuple)."""
        data: dict[str, Any] = dict(row._mapping)
        return Account(
            id=data.get("id"),
            name=data["name"],
            parent_id=data.get("parent_id"),
            currency=data.get("currency", "COP"),
            depth=data.get("depth", 0),
            kind=data["kind"],
            is_archived=bool(data.get("is_archived", 0)),
        )


@dataclass(frozen=True, slots=True)
class Posting:
    """A single posting in a double-entry transaction."""

    id: int | None = None
    transaction_id: int | None = None
    account_id: int = 0
    amount: Decimal = Decimal("0")
    currency: str = "COP"

    def to_row(self) -> dict[str, object]:
        """Convert to dict for SQLAlchemy Core insertion."""
        d: dict[str, object] = {
            "account_id": self.account_id,
            "amount": self.amount,
            "currency": self.currency,
        }
        if self.id is not None:
            d["id"] = self.id
        if self.transaction_id is not None:
            d["transaction_id"] = self.transaction_id
        return d

    @staticmethod
    def from_row(row: Mapping[str, Any]) -> Posting:
        """Reconstruct from a SQLAlchemy result row."""
        return Posting(
            id=row.get("id"),
            transaction_id=row.get("transaction_id"),
            account_id=row["account_id"],
            amount=row["amount"],
            currency=row.get("currency", "COP"),
        )


@dataclass(frozen=True, slots=True)
class Transaction:
    """A financial transaction with a list of postings."""

    id: int | None = None
    date: date | None = None
    description: str = ""
    currency: str = "COP"

    def to_row(self) -> dict[str, object]:
        """Convert to dict for SQLAlchemy Core insertion."""
        d: dict[str, object] = {
            "date": self.date,
            "description": self.description,
            "currency": self.currency,
        }
        if self.id is not None:
            d["id"] = self.id
        return d

    @staticmethod
    def from_row(row: Any) -> Transaction:
        """Reconstruct from a SQLAlchemy result row.

        Accepts a Row, RowMapping, or plain dict.
        """
        data: dict[str, Any] = dict(getattr(row, "_mapping", row))
        return Transaction(
            id=data.get("id"),
            date=data["date"],
            description=data["description"],
            currency=data.get("currency", "COP"),
        )


@dataclass(frozen=True, slots=True)
class Tag:
    """A tag for categorising transactions.

    ``account_id`` may be None for global tags usable on any transaction.
    """

    id: int | None = None
    name: str = ""
    account_id: int | None = None
    created_at: str = ""

    def to_row(self) -> dict[str, object]:
        """Convert to dict for SQLAlchemy Core insertion."""
        d: dict[str, object] = {"name": self.name}
        if self.id is not None:
            d["id"] = self.id
        if self.account_id is not None:
            d["account_id"] = self.account_id
        return d

    @staticmethod
    def from_row(row: object) -> Tag:
        """Reconstruct from a SQLAlchemy result row."""
        raw: Any = getattr(row, "_mapping", row)
        return Tag(
            id=int(raw["id"]) if raw.get("id") is not None else 0,
            name=str(raw["name"]),
            account_id=int(raw["account_id"]) if raw.get("account_id") is not None else None,
            created_at=str(raw.get("created_at", "")),
        )


@dataclass(frozen=True, slots=True)
class Rate:
    """An FX rate between two currencies.

    Maps to the 'rates' DB table with column mapping:
        from_ccy → base_currency
        to_ccy → target_currency
    """

    date: date
    from_ccy: str = ""
    to_ccy: str = ""
    rate: Decimal = Decimal("0")
    source: str = "frankfurter"
    id: int | None = None
    fetched_at: datetime | None = None

    def to_row(self) -> dict[str, object]:
        """Convert to dict for SQLAlchemy Core insertion."""
        d: dict[str, object] = {
            "base_currency": self.from_ccy,
            "target_currency": self.to_ccy,
            "rate": self.rate,
            "date": self.date,
            "source": self.source,
        }
        if self.id is not None:
            d["id"] = self.id
        if self.fetched_at is not None:
            d["fetched_at"] = self.fetched_at
        return d

    @staticmethod
    def from_row(row: Any) -> Rate:
        """Reconstruct from a SQLAlchemy result row.

        Coerces SQLite TEXT columns (date, fetched_at, rate) to their Python
        types. Accepts a Row, RowMapping, or plain ``dict`` (e.g. from tests).
        """
        from datetime import date as _date
        from datetime import datetime as _datetime
        from decimal import Decimal as _Decimal

        data: dict[str, Any] = dict(getattr(row, "_mapping", row))

        raw_date = data["date"]
        if isinstance(raw_date, str):
            data["date"] = _date.fromisoformat(raw_date)

        raw_fetched = data.get("fetched_at")
        if isinstance(raw_fetched, str):
            data["fetched_at"] = _datetime.fromisoformat(raw_fetched)

        raw_rate = data["rate"]
        if isinstance(raw_rate, str):
            data["rate"] = _Decimal(raw_rate)

        return Rate(
            id=data.get("id"),
            date=data["date"],
            from_ccy=data["base_currency"],
            to_ccy=data["target_currency"],
            rate=data["rate"],
            fetched_at=data.get("fetched_at"),
            source=data.get("source", "frankfurter"),
        )


@dataclass(frozen=True, slots=True)
class Budget:
    """A spending budget with period, scope, and limit.

    Frozen dataclass — fields are immutable after construction.
    ``account_id`` may be None (all accounts); ``tag_id`` may be None (all tags).
    """

    id: int | None = None
    name: str = ""
    amount: Decimal = Decimal("0")
    currency: str = "COP"
    period: str = "monthly"
    account_id: int | None = None
    tag_id: int | None = None
    start_date: str = ""
    is_active: bool = True
    created_at: str = ""

    def __post_init__(self) -> None:
        if self.period not in ("monthly", "yearly"):
            raise ValueError(f"period must be 'monthly' or 'yearly', got '{self.period}'")
        if self.amount < Decimal("0"):
            raise ValueError(f"amount must be non-negative, got {self.amount}")

    def to_row(self) -> dict[str, object]:
        """Convert to dict for SQLAlchemy Core insertion."""
        d: dict[str, object] = {
            "name": self.name,
            "amount": str(self.amount),
            "currency": self.currency,
            "period": self.period,
            "start_date": self.start_date,
            "is_active": 1 if self.is_active else 0,
        }
        if self.id is not None:
            d["id"] = self.id
        if self.account_id is not None:
            d["account_id"] = self.account_id
        if self.tag_id is not None:
            d["tag_id"] = self.tag_id
        return d

    @staticmethod
    def from_row(row: Any) -> Budget:
        """Reconstruct from a SQLAlchemy result row."""
        raw: dict[str, Any] = dict(getattr(row, "_mapping", row))
        return Budget(
            id=int(raw["id"]) if raw.get("id") is not None else None,
            name=str(raw["name"]),
            amount=Decimal(str(raw.get("amount", "0"))),
            currency=str(raw.get("currency", "COP")),
            period=str(raw["period"]),
            account_id=int(raw["account_id"]) if raw.get("account_id") is not None else None,
            tag_id=int(raw["tag_id"]) if raw.get("tag_id") is not None else None,
            start_date=str(raw["start_date"]),
            is_active=bool(raw.get("is_active", 1)),
            created_at=str(raw.get("created_at", "")),
        )


@dataclass(frozen=True, slots=True)
class RecurringRule:
    """A recurring transaction rule.

    Defines a schedule for generating transactions automatically.
    """

    id: int | None = None
    name: str = ""
    description: str = ""
    frequency: str = "monthly"  # daily|weekly|monthly|yearly
    interval_days: int = 0
    day_of_month: int | None = None
    day_of_week: int | None = None
    start_date: str = ""  # ISO date
    end_date: str | None = None
    next_date: str = ""  # ISO date
    is_active: bool = True
    created_at: str = ""

    def to_row(self) -> dict[str, object]:
        """Convert to dict for SQLAlchemy Core insertion.

        Always includes nullable columns (day_of_month, day_of_week, end_date)
        so SQLAlchemy named bind params resolve correctly.
        """
        d: dict[str, object] = {
            "name": self.name,
            "description": self.description,
            "frequency": self.frequency,
            "interval_days": self.interval_days,
            "day_of_month": self.day_of_month,
            "day_of_week": self.day_of_week,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "next_date": self.next_date,
            "is_active": 1 if self.is_active else 0,
        }
        if self.id is not None:
            d["id"] = self.id
        return d

    @staticmethod
    def from_row(row: Any) -> RecurringRule:
        """Reconstruct from a SQLAlchemy result row."""
        raw: dict[str, Any] = dict(getattr(row, "_mapping", row))
        return RecurringRule(
            id=int(raw["id"]) if raw.get("id") is not None else None,
            name=str(raw["name"]),
            description=str(raw.get("description", "")),
            frequency=str(raw["frequency"]),
            interval_days=int(raw.get("interval_days", 0)),
            day_of_month=int(raw["day_of_month"]) if raw.get("day_of_month") is not None else None,
            day_of_week=int(raw["day_of_week"]) if raw.get("day_of_week") is not None else None,
            start_date=str(raw["start_date"]),
            end_date=str(raw["end_date"]) if raw.get("end_date") is not None else None,
            next_date=str(raw["next_date"]),
            is_active=bool(raw.get("is_active", 1)),
            created_at=str(raw.get("created_at", "")),
        )


@dataclass(frozen=True, slots=True)
class RecurringPosting:
    """A posting template within a recurring rule."""

    id: int | None = None
    rule_id: int | None = None
    account_id: int = 0
    amount: Decimal = Decimal("0")
    currency: str = "COP"

    def to_row(self) -> dict[str, object]:
        """Convert to dict for SQLAlchemy Core insertion."""
        d: dict[str, object] = {
            "account_id": self.account_id,
            "amount": str(self.amount),
            "currency": self.currency,
        }
        if self.id is not None:
            d["id"] = self.id
        if self.rule_id is not None:
            d["rule_id"] = self.rule_id
        return d

    @staticmethod
    def from_row(row: Any) -> RecurringPosting:
        """Reconstruct from a SQLAlchemy result row."""
        raw: dict[str, Any] = dict(getattr(row, "_mapping", row))
        return RecurringPosting(
            id=int(raw["id"]) if raw.get("id") is not None else None,
            rule_id=int(raw["rule_id"]) if raw.get("rule_id") is not None else None,
            account_id=int(raw["account_id"]),
            amount=Decimal(str(raw.get("amount", "0"))),
            currency=str(raw.get("currency", "COP")),
        )


def compute_next_date(current_iso: str, frequency: str, /) -> str:
    """Return the next occurrence date for a given frequency.

    Implements month-arithmetic manually — no ``python-dateutil`` dependency.

    Args:
        current_iso: Current ``next_date`` in ISO format (YYYY-MM-DD).
        frequency: One of ``daily``, ``weekly``, ``monthly``, ``yearly``.

    Returns:
        The next date as an ISO string.

    Edge cases:
        - Monthly on Jan 31 → Feb 28 (non-leap) / Feb 29 (leap).
        - Monthly on Mar 31 → Apr 30.
    """
    dt = date.fromisoformat(current_iso)

    if frequency == "daily":
        next_dt = dt + timedelta(days=1)
    elif frequency == "weekly":
        next_dt = dt + timedelta(days=7)
    elif frequency == "monthly":
        year = dt.year
        month = dt.month + 1
        if month > 12:
            year += 1
            month = 1
        max_day = calendar.monthrange(year, month)[1]
        day = min(dt.day, max_day)
        next_dt = date(year, month, day)
    elif frequency == "yearly":
        year = dt.year + 1
        # handle Feb 29 edge case
        max_day = calendar.monthrange(year, dt.month)[1]
        day = min(dt.day, max_day)
        next_dt = date(year, dt.month, day)
    else:
        raise ValueError(f"Unknown frequency: {frequency}")

    return next_dt.isoformat()


__all__ = [
    "ROOT_TYPES",
    "Account",
    "Budget",
    "Posting",
    "Rate",
    "RecurringPosting",
    "RecurringRule",
    "Tag",
    "Transaction",
    "compute_next_date",
]
