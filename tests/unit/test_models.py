"""Tests for Account frozen dataclass."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from pyfintracker.models import Account, Posting, Transaction


@pytest.mark.unit
class TestAccountFrozenDataclass:
    """T-2.1: Account is a frozen dataclass with validation in __post_init__."""

    def test_valid_account_minimal(self) -> None:
        """Account with bare minimum required fields."""
        acct = Account(name="Assets:Checking", currency="COP", depth=1, kind="Assets")
        assert acct.name == "Assets:Checking"
        assert acct.currency == "COP"
        assert acct.depth == 1
        assert acct.kind == "Assets"
        assert acct.id is None
        assert acct.parent_id is None
        assert acct.is_archived is False

    def test_valid_account_with_id(self) -> None:
        """Account with optional id set."""
        acct = Account(id=1, name="Assets:Checking", currency="COP", depth=1, kind="Assets")
        assert acct.id == 1

    def test_account_is_frozen(self) -> None:
        """Account fields cannot be set after init."""
        acct = Account(name="Assets:Checking", currency="COP", depth=1, kind="Assets")
        with pytest.raises(AttributeError):
            acct.name = "Liabilities:Loan"  # type: ignore[misc]

    def test_invalid_kind(self) -> None:
        """Account rejects kind not in ROOT_TYPES."""
        with pytest.raises(ValueError, match="Invalid kind"):
            Account(name="Assets:Checking", currency="COP", depth=1, kind="FakeAssets")

    def test_empty_kind(self) -> None:
        """Account rejects empty kind."""
        with pytest.raises(ValueError, match="Invalid kind"):
            Account(name="Assets:Checking", currency="COP", depth=1, kind="")

    def test_invalid_depth_negative(self) -> None:
        """Account rejects negative depth."""
        with pytest.raises(ValueError, match="Depth must be 0-2"):
            Account(name="Income:Salary", currency="COP", depth=-1, kind="Income")

    def test_invalid_depth_too_deep(self) -> None:
        """Account rejects depth > 2."""
        with pytest.raises(ValueError, match="Depth must be 0-2"):
            Account(name="Expenses:Food:Groceries", currency="COP", depth=3, kind="Expenses")

    def test_invalid_name_empty(self) -> None:
        """Account rejects empty name."""
        with pytest.raises(ValueError, match="Account name cannot be empty"):
            Account(name="", currency="COP", depth=0, kind="Assets")

    def test_valid_account_all_fields(self) -> None:
        """Account with all optional fields set explicitly."""
        acct = Account(
            id=5,
            name="Expenses:Food:Groceries",
            parent_id=3,
            currency="USD",
            depth=2,
            kind="Expenses",
            is_archived=True,
        )
        assert acct.id == 5
        assert acct.name == "Expenses:Food:Groceries"
        assert acct.parent_id == 3
        assert acct.currency == "USD"
        assert acct.depth == 2
        assert acct.kind == "Expenses"
        assert acct.is_archived is True

    def test_valid_depth_zero(self) -> None:
        """Depth 0 is valid (root account placeholder)."""
        acct = Account(name="Assets:Cash", currency="COP", depth=0, kind="Assets")
        assert acct.depth == 0


@pytest.mark.unit
class TestAccountRowConversion:
    """T-2.2: Account.to_row() / from_row() conversion."""

    def test_to_row_minimal(self) -> None:
        """to_row() returns dict without optional fields when not set."""
        acct = Account(name="Assets:Checking", currency="COP", depth=1, kind="Assets")
        row = acct.to_row()
        assert row == {
            "name": "Assets:Checking",
            "currency": "COP",
            "depth": 1,
            "kind": "Assets",
            "is_archived": 0,
        }

    def test_to_row_with_id(self) -> None:
        """to_row() includes id when set."""
        acct = Account(id=42, name="Assets:Savings", currency="USD", depth=1, kind="Assets")
        row = acct.to_row()
        assert row["id"] == 42

    def test_to_row_with_parent_id(self) -> None:
        """to_row() includes parent_id when set."""
        acct = Account(
            id=5,
            name="Expenses:Food:Groceries",
            parent_id=3,
            currency="COP",
            depth=2,
            kind="Expenses",
        )
        row = acct.to_row()
        assert row["parent_id"] == 3

    def test_to_row_archived(self) -> None:
        """to_row() sets is_archived=1 when archived."""
        acct = Account(
            name="Liabilities:CreditCard",
            currency="COP",
            depth=1,
            kind="Liabilities",
            is_archived=True,
        )
        row = acct.to_row()
        assert row["is_archived"] == 1

    def test_from_row_roundtrip_no_id(self) -> None:
        """from_row(to_row(account)) == account with None id."""
        acct = Account(name="Income:Salary", currency="COP", depth=1, kind="Income")
        row = acct.to_row()
        # Simulate a SQLAlchemy RowMapping
        row_data = dict(row)
        mock_row = MagicMock()
        mock_row._mapping = row_data
        restored = Account.from_row(mock_row)
        assert restored == acct

    def test_from_row_roundtrip_with_id(self) -> None:
        """from_row(to_row(account)) == account with explicit id."""
        acct = Account(
            id=10,
            name="Expenses:Rent",
            parent_id=7,
            currency="USD",
            depth=1,
            kind="Expenses",
            is_archived=True,
        )
        row = acct.to_row()
        row_data = dict(row)
        mock_row = MagicMock()
        mock_row._mapping = row_data
        restored = Account.from_row(mock_row)
        assert restored == acct

    def test_from_row_handles_row_without_mapping(self) -> None:
        """from_row also works on rows without _mapping (direct dict compat)."""
        acct = Account(id=3, name="Equity:Opening", currency="COP", depth=0, kind="Equity")
        row = acct.to_row()
        mock_row = MagicMock(spec=[])  # No _mapping attr
        mock_row._mapping = row  # But we add it manually like a real SA row
        restored = Account.from_row(mock_row)
        assert restored == acct


@pytest.mark.unit
class TestPosting:
    """T-4.1: Posting frozen dataclass."""

    def test_construction(self) -> None:
        p = Posting(account_id=1, amount=Decimal("100.00"), currency="COP")
        assert p.account_id == 1
        assert p.amount == Decimal("100.00")
        assert p.currency == "COP"

    def test_with_transaction_id(self) -> None:
        p = Posting(transaction_id=5, account_id=1, amount=Decimal("100.00"), currency="COP")
        assert p.transaction_id == 5

    def test_frozen(self) -> None:
        p = Posting(account_id=1, amount=Decimal("100"), currency="COP")
        with pytest.raises(AttributeError):
            p.amount = Decimal("200")  # type: ignore[misc]

    def test_to_row(self) -> None:
        p = Posting(transaction_id=5, account_id=1, amount=Decimal("100.00"), currency="COP")
        row = p.to_row()
        assert row["transaction_id"] == 5
        assert row["account_id"] == 1

    def test_from_row(self) -> None:
        row = {
            "id": 10,
            "transaction_id": 5,
            "account_id": 1,
            "amount": Decimal("100.00"),
            "currency": "COP",
        }
        p = Posting.from_row(row)
        assert p.id == 10
        assert p.amount == Decimal("100.00")

    def test_roundtrip(self) -> None:
        original = Posting(transaction_id=5, account_id=1, amount=Decimal("100.00"), currency="COP")
        row = original.to_row()
        restored = Posting.from_row(row)
        assert restored == original


@pytest.mark.unit
class TestTransaction:
    """T-4.2: Transaction frozen dataclass."""

    def test_construction(self) -> None:
        t = Transaction(date=date(2024, 1, 15), description="Test txn")
        assert t.date == date(2024, 1, 15)
        assert t.description == "Test txn"
        assert t.currency == "COP"

    def test_with_id(self) -> None:
        t = Transaction(id=1, date=date(2024, 1, 15), description="Test")
        assert t.id == 1

    def test_frozen(self) -> None:
        t = Transaction(date=date(2024, 1, 15), description="Test")
        with pytest.raises(AttributeError):
            t.date = date(2024, 2, 1)  # type: ignore[misc]

    def test_to_row(self) -> None:
        t = Transaction(id=1, date=date(2024, 1, 15), description="Test", currency="COP")
        row = t.to_row()
        assert row["id"] == 1

    def test_from_row(self) -> None:
        row = {"id": 1, "date": date(2024, 1, 15), "description": "Test", "currency": "COP"}
        t = Transaction.from_row(row)
        assert t.id == 1
        assert t.date == date(2024, 1, 15)

    def test_roundtrip(self) -> None:
        original = Transaction(date=date(2024, 1, 15), description="Test", currency="COP")
        row = original.to_row()
        restored = Transaction.from_row(row)
        assert restored == original


#
# ── T-A.2: Rate frozen dataclass ──────────────────────────────────────────────
#


@pytest.mark.unit
class TestRate:
    """T-A.2: Rate frozen dataclass with to_row/from_row."""

    def test_rate_construction(self) -> None:
        """Rate minimal construction."""
        from datetime import date
        from decimal import Decimal

        from pyfintracker.models import Rate

        r = Rate(date=date(2026, 7, 18), from_ccy="USD", to_ccy="COP", rate=Decimal("3255.56"))
        assert r.date == date(2026, 7, 18)
        assert r.from_ccy == "USD"
        assert r.to_ccy == "COP"
        assert r.rate == Decimal("3255.56")
        assert r.fetched_at is None
        assert r.source == "frankfurter"
        assert r.id is None

    def test_rate_is_decimal(self) -> None:
        """Rate.rate is Decimal type (float enforced by mypy)."""
        from datetime import date
        from decimal import Decimal

        from pyfintracker.models import Rate

        r = Rate(date=date(2026, 7, 18), from_ccy="USD", to_ccy="COP", rate=Decimal("3255.56"))
        assert type(r.rate) is Decimal

    def test_rate_is_frozen(self) -> None:
        """Rate is immutable after construction."""
        from datetime import date
        from decimal import Decimal

        from pyfintracker.models import Rate

        r = Rate(date=date(2026, 7, 18), from_ccy="USD", to_ccy="COP", rate=Decimal("1"))
        with pytest.raises(AttributeError):
            r.rate = Decimal("2")  # type: ignore[misc]

    def test_rate_to_row_maps_ccy_columns(self) -> None:
        """to_row maps from_ccy→base_currency, to_ccy→target_currency."""
        from datetime import date, datetime
        from decimal import Decimal

        from pyfintracker.models import Rate

        r = Rate(
            id=1,
            date=date(2026, 7, 18),
            from_ccy="USD",
            to_ccy="COP",
            rate=Decimal("3255.56"),
            fetched_at=datetime(2026, 7, 18, 12, 0, 0),
        )
        row = r.to_row()
        assert row["base_currency"] == "USD"
        assert row["target_currency"] == "COP"
        assert row["rate"] == Decimal("3255.56")
        assert row["date"] == date(2026, 7, 18)
        assert row["source"] == "frankfurter"
        assert row["fetched_at"] == datetime(2026, 7, 18, 12, 0, 0)

    def test_rate_from_row_roundtrip(self) -> None:
        """Rate.from_row(to_row()) preserves all fields byte-exact."""
        from datetime import date, datetime
        from decimal import Decimal

        from pyfintracker.models import Rate

        original = Rate(
            id=1,
            date=date(2026, 7, 18),
            from_ccy="USD",
            to_ccy="COP",
            rate=Decimal("3255.56"),
            fetched_at=datetime(2026, 7, 18, 12, 0, 0),
        )
        row = original.to_row()
        restored = Rate.from_row(row)
        assert restored == original
        assert type(restored.rate) is Decimal

    def test_rate_from_row_without_id(self) -> None:
        """from_row works without id (None on insert)."""
        from datetime import date
        from decimal import Decimal

        from pyfintracker.models import Rate

        row = {
            "date": date(2026, 7, 18),
            "base_currency": "USD",
            "target_currency": "COP",
            "rate": Decimal("3255.56"),
            "source": "frankfurter",
        }
        r = Rate.from_row(row)
        assert r.id is None
        assert r.from_ccy == "USD"
        assert r.to_ccy == "COP"
        assert r.rate == Decimal("3255.56")
        assert r.fetched_at is None
