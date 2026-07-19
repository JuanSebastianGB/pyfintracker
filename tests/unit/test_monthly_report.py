"""Tests for the MonthlyReport model + compute_monthly_report."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pydantic
import pytest
from sqlalchemy import text

from pyfintracker.db import get_session
from pyfintracker.models import Posting, Transaction


@pytest.mark.unit
class TestMonthlyReportModels:
    """T-6.1: Pydantic MonthlyReport model."""

    def test_monthly_line_instantiate(self) -> None:
        """MonthlyLine can be created with all fields."""
        from pyfintracker.reports import MonthlyLine

        line = MonthlyLine(
            day=15, label="Income:Salary", amount=Decimal("1000"), balance=Decimal("1000")
        )
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
                MonthlyLine(
                    day=15, label="Income:Salary", amount=Decimal("3000"), balance=Decimal("3000")
                ),
            ],
            expense_lines=[
                MonthlyLine(
                    day=3, label="Expenses:Rent", amount=Decimal("1000"), balance=Decimal("-1000")
                ),
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

    def test_monthly_report_currency_default(self) -> None:
        """MonthlyReport defaults to COP currency."""
        from pyfintracker.reports import MonthlyReport

        report = MonthlyReport(
            year_month="2024-01",
            income_lines=[],
            expense_lines=[],
            income_total=Decimal("0"),
            expense_total=Decimal("0"),
            net=Decimal("0"),
        )
        assert report.currency == "COP"

    def test_monthly_report_currency_custom(self) -> None:
        """MonthlyReport accepts custom currency."""
        from pyfintracker.reports import MonthlyReport

        report = MonthlyReport(
            year_month="2024-01",
            income_lines=[],
            expense_lines=[],
            income_total=Decimal("0"),
            expense_total=Decimal("0"),
            net=Decimal("0"),
            currency="USD",
        )
        assert report.currency == "USD"

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


@pytest.mark.unit
class TestComputeMonthlyReport:
    """T-6.2: compute_monthly_report logic."""

    def test_monthly_report_default_display_currency(
        self, reports_engine, seed_simple_month
    ) -> None:
        """Default display_currency is COP (same as seed data) — identity."""
        from pyfintracker.reports import compute_monthly_report

        with get_session(reports_engine) as conn:
            report = compute_monthly_report(conn, "2024-01")

        assert report.currency == "COP"
        # Verify amounts unchanged from seed
        assert report.income_total == Decimal("3000000")
        assert report.expense_total == Decimal("1450000")
        assert report.net == Decimal("1550000")

    def test_monthly_report_same_currency_identity(self, reports_engine, seed_simple_month) -> None:
        """Explicit display_currency='COP' produces byte-equal results to default."""
        from pyfintracker.reports import compute_monthly_report

        with get_session(reports_engine) as conn:
            report_default = compute_monthly_report(conn, "2024-01")
            report_explicit = compute_monthly_report(conn, "2024-01", display_currency="COP")

        assert report_default.model_dump() == report_explicit.model_dump()

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

    def test_compute_monthly_mixed_currency_converts_via_txn_date(
        self,
        seed_mixed_month,
    ) -> None:
        """Mixed COP+USD postings convert each at own txn-date rate."""
        from pyfintracker.reports import compute_monthly_report

        with get_session(seed_mixed_month) as conn:
            report = compute_monthly_report(conn, "2026-07", display_currency="USD")

        assert report.currency == "USD"
        # Income: 50000 COP @ 0.00025 = 12.50 USD, plus 15 USD = 27.50 USD
        assert report.income_total == Decimal("27.50")
        # Expenses: 1200 COP @ 0.000238 = 0.2856, quantized to 0.29
        assert report.expense_total == Decimal("0.29")
        # Net: 27.50 - 0.29 = 27.21
        assert report.net == Decimal("27.21")

    def test_compute_monthly_algebraic_identity_mixed(self, seed_mixed_month) -> None:
        """Algebraic invariant: income_total - expense_total == net holds in display_currency."""
        from pyfintracker.reports import compute_monthly_report

        with get_session(seed_mixed_month) as conn:
            report = compute_monthly_report(conn, "2026-07", display_currency="USD")

        assert report.income_total - report.expense_total == report.net

    def test_invalid_year_month_format(self, reports_engine) -> None:
        """Invalid year_month format raises ValueError."""
        from pyfintracker.reports import compute_monthly_report

        with (
            get_session(reports_engine) as conn,
            pytest.raises(ValueError, match="Invalid year_month format"),
        ):
            compute_monthly_report(conn, "2024/01")

    @pytest.mark.parametrize(
        "year_month",
        [
            "2024-013",  # extra trailing char
            "2024-0a",  # month is not all digits
        ],
    )
    def test_year_month_must_be_seven_chars(self, reports_engine, year_month: str) -> None:
        """Length and per-slice digit checks reject malformed strings before SQL."""
        from pyfintracker.reports import compute_monthly_report

        with (
            get_session(reports_engine) as conn,
            pytest.raises(ValueError, match="Invalid year_month format"),
        ):
            compute_monthly_report(conn, year_month)

    def test_year_month_uses_separator_index_5(self, reports_engine) -> None:
        """A valid 'YYYY-MM' must read month from index 5 onwards (not 6)."""
        from pyfintracker.reports import compute_monthly_report

        eng = reports_engine
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Income:Salary', 'COP', 1, 'Income')"
                ),
            )
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Checking', 'COP', 1, 'Assets')"
                ),
            )
            accts = {
                r.name: r.id for r in conn.execute(text("SELECT id, name FROM accounts")).fetchall()
            }
            txn_id = conn.execute(
                text(
                    "INSERT INTO transactions (date, description) VALUES ('2026-07-05', 'Salary') RETURNING id"
                ),
            ).scalar()
            conn.execute(
                text(
                    "INSERT INTO postings (transaction_id, account_id, amount, currency) VALUES (:tid, :aid, :amt, :cur)"
                ),
                {"tid": txn_id, "aid": accts["Income:Salary"], "amt": "-100000", "cur": "COP"},
            )
            conn.execute(
                text(
                    "INSERT INTO postings (transaction_id, account_id, amount, currency) VALUES (:tid, :aid, :amt, :cur)"
                ),
                {"tid": txn_id, "aid": accts["Assets:Checking"], "amt": "100000", "cur": "COP"},
            )

        with get_session(eng) as conn:
            report = compute_monthly_report(conn, "2026-07")

        assert report.income_total == Decimal("100000")

    def test_no_cross_currency_skips_prefetch(self, reports_engine) -> None:
        """When every posting matches the display currency, totals are correct without FX."""
        from pyfintracker.reports import compute_monthly_report

        eng = reports_engine
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Income:Salary', 'COP', 1, 'Income')"
                ),
            )
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Checking', 'COP', 1, 'Assets')"
                ),
            )
            accts = {
                r.name: r.id for r in conn.execute(text("SELECT id, name FROM accounts")).fetchall()
            }
            txn_id = conn.execute(
                text(
                    "INSERT INTO transactions (date, description) VALUES ('2026-07-05', 'Salary') RETURNING id"
                ),
            ).scalar()
            conn.execute(
                text(
                    "INSERT INTO postings (transaction_id, account_id, amount, currency) VALUES (:tid, :aid, :amt, :cur)"
                ),
                {"tid": txn_id, "aid": accts["Income:Salary"], "amt": "-100", "cur": "COP"},
            )
            conn.execute(
                text(
                    "INSERT INTO postings (transaction_id, account_id, amount, currency) VALUES (:tid, :aid, :amt, :cur)"
                ),
                {"tid": txn_id, "aid": accts["Assets:Checking"], "amt": "100", "cur": "COP"},
            )

        with get_session(eng) as conn:
            report = compute_monthly_report(conn, "2026-07", display_currency="COP")

        assert report.income_total == Decimal("100")

    def test_cross_currency_converts_each_posting(self, reports_engine_with_rates) -> None:
        """Postings in a foreign currency must be converted to the display currency."""
        from pyfintracker.reports import compute_monthly_report

        eng = reports_engine_with_rates
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Income:Salary', 'USD', 1, 'Income')"
                ),
            )
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Checking', 'COP', 1, 'Assets')"
                ),
            )
            accts = {
                r.name: r.id for r in conn.execute(text("SELECT id, name FROM accounts")).fetchall()
            }
            txn_id = conn.execute(
                text(
                    "INSERT INTO transactions (date, description) VALUES ('2026-07-05', 'Salary') RETURNING id"
                ),
            ).scalar()
            conn.execute(
                text(
                    "INSERT INTO postings (transaction_id, account_id, amount, currency) VALUES (:tid, :aid, :amt, :cur)"
                ),
                {"tid": txn_id, "aid": accts["Income:Salary"], "amt": "-100", "cur": "USD"},
            )
            conn.execute(
                text(
                    "INSERT INTO postings (transaction_id, account_id, amount, currency) VALUES (:tid, :aid, :amt, :cur)"
                ),
                {"tid": txn_id, "aid": accts["Assets:Checking"], "amt": "100", "cur": "USD"},
            )

        with get_session(eng) as conn:
            report = compute_monthly_report(conn, "2026-07", display_currency="COP")

        assert report.income_total == Decimal("400000")

    def test_multiple_income_same_day(self, reports_engine, seed_simple_month) -> None:
        """Multiple income entries on the same day are grouped correctly."""
        from pyfintracker.reports import compute_monthly_report

        # Add another income on the same day
        with reports_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Income:Bonus', 'COP', 1, 'Income')"
                ),
            )
            accts = {
                r.name: r.id for r in conn.execute(text("SELECT id, name FROM accounts")).fetchall()
            }

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


