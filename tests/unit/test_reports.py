"""Tests for reports module — MonthlyReport, BalanceReport, and compute functions.

Strict TDD: test first, then implement.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pydantic
import pytest
from sqlalchemy import text

from pyfintracker.db import get_session, make_test_engine
from pyfintracker.models import Posting, Transaction


@pytest.mark.unit
class TestReportsModels:
    """T-6.1: Pydantic models for report output."""

    def test_monthly_line_instantiate(self) -> None:
        """MonthlyLine can be created with all fields."""
        from pyfintracker.reports import MonthlyLine

        line = MonthlyLine(day=15, label="Income:Salary", amount=Decimal("1000"), balance=Decimal("1000"))
        assert line.day == 15
        assert line.label == "Income:Salary"
        assert line.amount == Decimal("1000")
        assert line.balance == Decimal("1000")

    def test_monthly_line_is_frozen(self) -> None:
        """MonthlyLine cannot be modified after creation."""
        from pyfintracker.reports import MonthlyLine

        line = MonthlyLine(day=1, label="Test", amount=Decimal("100"), balance=Decimal("100"))
        with pytest.raises((AttributeError, TypeError, pydantic.ValidationError)):
            line.day = 2  # type: ignore[misc]

    def test_monthly_report_instantiate(self) -> None:
        """MonthlyReport can be created with all fields."""
        from pyfintracker.reports import MonthlyLine, MonthlyReport

        report = MonthlyReport(
            year_month="2024-01",
            income_lines=[
                MonthlyLine(day=15, label="Income:Salary", amount=Decimal("3000"), balance=Decimal("3000")),
            ],
            expense_lines=[
                MonthlyLine(day=3, label="Expenses:Rent", amount=Decimal("1000"), balance=Decimal("-1000")),
            ],
            income_total=Decimal("3000"),
            expense_total=Decimal("1000"),
            net=Decimal("2000"),
        )
        assert report.year_month == "2024-01"
        assert len(report.income_lines) == 1
        assert len(report.expense_lines) == 1
        assert report.income_total == Decimal("3000")
        assert report.expense_total == Decimal("1000")
        assert report.net == Decimal("2000")

    def test_monthly_report_is_frozen(self) -> None:
        """MonthlyReport cannot be modified after creation."""
        from pyfintracker.reports import MonthlyReport

        report = MonthlyReport(
            year_month="2024-01",
            income_lines=[],
            expense_lines=[],
            income_total=Decimal("0"),
            expense_total=Decimal("0"),
            net=Decimal("0"),
        )
        with pytest.raises((AttributeError, TypeError, pydantic.ValidationError)):
            report.net = Decimal("100")  # type: ignore[misc]

    def test_monthly_report_serialize(self) -> None:
        """MonthlyReport can be serialized to dict."""
        from pyfintracker.reports import MonthlyReport

        report = MonthlyReport(
            year_month="2024-01",
            income_lines=[],
            expense_lines=[],
            income_total=Decimal("0"),
            expense_total=Decimal("0"),
            net=Decimal("0"),
        )
        d = report.model_dump()
        assert d["year_month"] == "2024-01"
        assert d["income_total"] == Decimal("0")

    def test_balance_line_instantiate(self) -> None:
        """BalanceLine can be created with all fields."""
        from pyfintracker.reports import BalanceLine

        line = BalanceLine(account_name="Assets:Checking", account_kind="Assets", balance=Decimal("5000"))
        assert line.account_name == "Assets:Checking"
        assert line.account_kind == "Assets"
        assert line.balance == Decimal("5000")

    def test_balance_line_is_frozen(self) -> None:
        """BalanceLine cannot be modified after creation."""
        from pyfintracker.reports import BalanceLine

        line = BalanceLine(account_name="Assets:Checking", account_kind="Assets", balance=Decimal("5000"))
        with pytest.raises((AttributeError, TypeError, pydantic.ValidationError)):
            line.balance = Decimal("0")  # type: ignore[misc]

    def test_balance_report_instantiate(self) -> None:
        """BalanceReport can be created with all fields."""
        from pyfintracker.reports import BalanceLine, BalanceReport

        report = BalanceReport(
            lines=[
                BalanceLine(account_name="Assets:Checking", account_kind="Assets", balance=Decimal("1000")),
            ],
            net_worth=Decimal("1000"),
        )
        assert len(report.lines) == 1
        assert report.net_worth == Decimal("1000")

    def test_balance_report_is_frozen(self) -> None:
        """BalanceReport cannot be modified after creation."""
        from pyfintracker.reports import BalanceReport

        report = BalanceReport(lines=[], net_worth=Decimal("0"))
        with pytest.raises((AttributeError, TypeError, pydantic.ValidationError)):
            report.net_worth = Decimal("100")  # type: ignore[misc]

    def test_balance_report_serialize(self) -> None:
        """BalanceReport can be serialized to dict."""
        from pyfintracker.reports import BalanceReport

        report = BalanceReport(lines=[], net_worth=Decimal("0"))
        d = report.model_dump()
        assert d["net_worth"] == Decimal("0")
        assert d["lines"] == []


# ── Helper to build an in-memory DB with schema + seed data ────────────


@pytest.fixture
def reports_engine():
    """In-memory engine with accounts, transactions, postings tables."""
    eng = make_test_engine()
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    currency TEXT NOT NULL DEFAULT 'COP',
                    depth INTEGER NOT NULL DEFAULT 0,
                    kind TEXT NOT NULL,
                    is_archived INTEGER NOT NULL DEFAULT 0
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT ''
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE postings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id INTEGER NOT NULL REFERENCES transactions(id),
                    account_id INTEGER NOT NULL REFERENCES accounts(id),
                    amount TEXT NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'COP'
                )
                """
            )
        )
    yield eng
    eng.dispose()


@pytest.fixture
def seed_simple_month(reports_engine):
    """Seed data for a simple month: income + expense transaction.

    Returns a dict mapping account names to their IDs.
    """
    with reports_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Checking', 'COP', 1, 'Assets')"),
        )
        conn.execute(
            text("INSERT INTO accounts (name, currency, depth, kind) VALUES ('Income:Salary', 'COP', 1, 'Income')"),
        )
        conn.execute(
            text("INSERT INTO accounts (name, currency, depth, kind) VALUES ('Expenses:Rent', 'COP', 1, 'Expenses')"),
        )
        conn.execute(
            text("INSERT INTO accounts (name, currency, depth, kind) VALUES ('Expenses:Food:Groceries', 'COP', 2, 'Expenses')"),
        )
        rows = conn.execute(text("SELECT id, name FROM accounts ORDER BY id")).fetchall()
    accounts = {r.name: r.id for r in rows}

    from pyfintracker.repository import create_transaction_with_postings

    txn1 = Transaction(date=date(2024, 1, 3), description="Rent payment")
    postings1 = [
        Posting(account_id=accounts["Expenses:Rent"], amount=Decimal("1200000"), currency="COP"),
        Posting(account_id=accounts["Assets:Checking"], amount=Decimal("-1200000"), currency="COP"),
    ]
    with get_session(reports_engine) as conn:
        create_transaction_with_postings(conn, txn1, postings1)

    txn2 = Transaction(date=date(2024, 1, 15), description="Salary")
    postings2 = [
        Posting(account_id=accounts["Income:Salary"], amount=Decimal("-3000000"), currency="COP"),
        Posting(account_id=accounts["Assets:Checking"], amount=Decimal("3000000"), currency="COP"),
    ]
    with get_session(reports_engine) as conn:
        create_transaction_with_postings(conn, txn2, postings2)

    txn3 = Transaction(date=date(2024, 1, 20), description="Groceries")
    postings3 = [
        Posting(account_id=accounts["Expenses:Food:Groceries"], amount=Decimal("250000"), currency="COP"),
        Posting(account_id=accounts["Assets:Checking"], amount=Decimal("-250000"), currency="COP"),
    ]
    with get_session(reports_engine) as conn:
        create_transaction_with_postings(conn, txn3, postings3)

    return accounts


@pytest.mark.unit
class TestComputeMonthlyReport:
    """T-6.2: compute_monthly_report logic."""

    def test_monthly_report_happy_path(self, reports_engine, seed_simple_month) -> None:
        """Happy path: income + expenses in Jan 2024 produce correct report."""
        from pyfintracker.reports import compute_monthly_report

        with get_session(reports_engine) as conn:
            report = compute_monthly_report(conn, "2024-01")

        assert report.year_month == "2024-01"
        # Income: 3000000 (salary)
        assert report.income_total == Decimal("3000000")
        # Expenses: 1200000 + 250000
        assert report.expense_total == Decimal("1450000")
        # Net: income - expenses
        assert report.net == Decimal("1550000")

        # Income lines
        assert len(report.income_lines) == 1
        assert report.income_lines[0].day == 15
        assert report.income_lines[0].label == "Income:Salary"
        assert report.income_lines[0].amount == Decimal("3000000")
        assert report.income_lines[0].balance == Decimal("3000000")

        # Expense lines
        assert len(report.expense_lines) == 2
        # Sorted by day then name
        assert report.expense_lines[0].day == 3
        assert report.expense_lines[0].label == "Expenses:Rent"
        assert report.expense_lines[0].amount == Decimal("1200000")
        assert report.expense_lines[1].day == 20
        assert report.expense_lines[1].label == "Expenses:Food:Groceries"
        assert report.expense_lines[1].amount == Decimal("250000")

    def test_income_sum_minus_expense_equals_net(self, reports_engine, seed_simple_month) -> None:
        """Algebraic invariant: income_total - expense_total == net."""
        from pyfintracker.reports import compute_monthly_report

        with get_session(reports_engine) as conn:
            report = compute_monthly_report(conn, "2024-01")

        assert report.income_total + (-report.expense_total) == report.net

    def test_empty_month(self, reports_engine) -> None:
        """A month with no transactions returns zero totals and empty lines."""
        from pyfintracker.reports import compute_monthly_report

        with get_session(reports_engine) as conn:
            # No accounts/txns seeded — empty DB
            report = compute_monthly_report(conn, "2024-06")

        assert report.year_month == "2024-06"
        assert report.income_total == Decimal("0")
        assert report.expense_total == Decimal("0")
        assert report.net == Decimal("0")
        assert report.income_lines == []
        assert report.expense_lines == []

    def test_invalid_year_month_format(self, reports_engine) -> None:
        """Invalid year_month format raises ValueError."""
        from pyfintracker.reports import compute_monthly_report

        with get_session(reports_engine) as conn, pytest.raises(
            ValueError, match="Invalid year_month format"
        ):
            compute_monthly_report(conn, "2024/01")

    def test_multiple_income_same_day(self, reports_engine, seed_simple_month) -> None:
        """Multiple income entries on the same day are grouped correctly."""
        from pyfintracker.reports import compute_monthly_report

        # Add another income on the same day
        with reports_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO accounts (name, currency, depth, kind) VALUES ('Income:Bonus', 'COP', 1, 'Income')"),
            )
            accts = {r.name: r.id for r in conn.execute(text("SELECT id, name FROM accounts")).fetchall()}

        from pyfintracker.repository import create_transaction_with_postings

        txn = Transaction(date=date(2024, 1, 15), description="Bonus")
        postings = [
            Posting(account_id=accts["Income:Bonus"], amount=Decimal("-500000"), currency="COP"),
            Posting(account_id=accts["Assets:Checking"], amount=Decimal("500000"), currency="COP"),
        ]
        with get_session(reports_engine) as conn:
            create_transaction_with_postings(conn, txn, postings)

        with get_session(reports_engine) as conn:
            report = compute_monthly_report(conn, "2024-01")

        # Two income lines now (Salary, Bonus) — sorted by day then name
        assert len(report.income_lines) == 2
        assert report.income_total == Decimal("3500000")  # 3000000 + 500000
        assert report.net == Decimal("2050000")  # 3500000 - 1450000


@pytest.mark.unit
class TestComputeBalance:
    """T-6.3: compute_balance logic."""

    def test_balance_asset_positive(self, reports_engine, seed_simple_month) -> None:
        """Assets show positive balance."""
        from pyfintracker.reports import compute_balance

        with get_session(reports_engine) as conn:
            report = compute_balance(conn)

        # Assets:Checking should have positive balance
        checking = [line for line in report.lines if line.account_name == "Assets:Checking"]
        assert len(checking) == 1
        # 3000000 (salary) - 1200000 (rent) - 250000 (groceries) = 1550000
        assert checking[0].balance == Decimal("1550000")
        assert checking[0].account_kind == "Assets"

    def test_exclude_income_expenses(self, reports_engine, seed_simple_month) -> None:
        """Income and Expenses accounts are excluded from balance."""
        from pyfintracker.reports import compute_balance

        with get_session(reports_engine) as conn:
            report = compute_balance(conn)

        names = [line.account_name for line in report.lines]
        assert "Income:Salary" not in names
        assert "Expenses:Rent" not in names
        assert "Expenses:Food:Groceries" not in names

    def test_net_worth_positive(self, reports_engine, seed_simple_month) -> None:
        """Net worth equals sum of (asset + liability + equity) balances."""
        from pyfintracker.reports import compute_balance

        with get_session(reports_engine) as conn:
            report = compute_balance(conn)

        # Only Assets:Checking has a balance, so net_worth == its balance
        assert report.net_worth == Decimal("1550000")

    def test_balance_multiple_assets(self, reports_engine, seed_simple_month) -> None:
        """Multiple asset accounts all appear."""
        from pyfintracker.reports import compute_balance

        # Add a second asset account
        with reports_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Savings', 'COP', 1, 'Assets')"),
            )

        with get_session(reports_engine) as conn:
            report = compute_balance(conn)

        names = [line.account_name for line in report.lines]
        assert "Assets:Checking" in names
        # Savings has zero balance — should be excluded
        assert "Assets:Savings" not in names, "Zero-balance accounts should be excluded"

    def test_liability_positive(self, reports_engine) -> None:
        """Liabilities show positive balance."""
        from pyfintracker.reports import compute_balance

        with reports_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO accounts (name, currency, depth, kind) VALUES ('Liabilities:CreditCard', 'COP', 1, 'Liabilities')"),
            )
            conn.execute(
                text("INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Checking', 'COP', 1, 'Assets')"),
            )
            accts = {r.name: r.id for r in conn.execute(text("SELECT id, name FROM accounts")).fetchall()}

        from pyfintracker.repository import create_transaction_with_postings

        txn = Transaction(date=date(2024, 1, 1), description="CC charge")
        postings = [
            Posting(account_id=accts["Liabilities:CreditCard"], amount=Decimal("-500000"), currency="COP"),
            Posting(account_id=accts["Assets:Checking"], amount=Decimal("500000"), currency="COP"),
        ]
        with get_session(reports_engine) as conn:
            create_transaction_with_postings(conn, txn, postings)

        with get_session(reports_engine) as conn:
            report = compute_balance(conn)

        cc = [line for line in report.lines if line.account_name == "Liabilities:CreditCard"]
        assert len(cc) == 1
        assert cc[0].balance == Decimal("500000")  # positive convention
        assert cc[0].account_kind == "Liabilities"

    def test_zero_balance_excluded(self, reports_engine) -> None:
        """Accounts with zero balance are excluded from the report."""
        from pyfintracker.reports import compute_balance

        with reports_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Empty', 'COP', 1, 'Assets')"),
            )

        with get_session(reports_engine) as conn:
            report = compute_balance(conn)

        names = [line.account_name for line in report.lines]
        assert "Assets:Empty" not in names
