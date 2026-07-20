"""Frozen dataclass entities for pyfintracker."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
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
    def from_row(row: Mapping[str, Any]) -> Transaction:
        """Reconstruct from a SQLAlchemy result row."""
        return Transaction(
            id=row.get("id"),
            date=row["date"],
            description=row["description"],
            currency=row.get("currency", "COP"),
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


__all__ = [
    "ROOT_TYPES",
    "Account",
    "Posting",
    "Rate",
    "Tag",
    "Transaction",
]
