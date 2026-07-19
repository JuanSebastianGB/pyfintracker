"""Snapshot tests for report rendering functions.

These tests capture Rich console output and verify structure (section
titles, bold markers, color markers).  Full syrupy snapshot fixtures
will be created in Batch 4 — for now we verify output invariants.
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

import pytest
from rich.console import Console

from pyfintracker.reports import BalanceLine, BalanceReport, MonthlyLine, MonthlyReport

# ANSI escape codes emitted by Rich with force_terminal=True
ANSI_GREEN = "\x1b[32m"
ANSI_RED = "\x1b[31m"
ANSI_BOLD = "\x1b[1m"


@pytest.mark.snapshot
class TestRenderMonthly:
    """T-6.4: render_monthly_report output structure."""

    def _make_report(
        self,
        income: list[tuple[int, str, str, str]] | None = None,
        expenses: list[tuple[int, str, str, str]] | None = None,
    ) -> MonthlyReport:
        """Build a MonthlyReport from compact test data.

        Each tuple: (day, label, amount_str, cum_balance_str)
        """
        income_lines = []
        if income:
            for day, label, amt, bal in income:
                income_lines.append(
                    MonthlyLine(day=day, label=label, amount=Decimal(amt), balance=Decimal(bal))
                )
        expense_lines = []
        if expenses:
            for day, label, amt, bal in expenses:
                expense_lines.append(
                    MonthlyLine(day=day, label=label, amount=Decimal(amt), balance=Decimal(bal))
                )

        income_total = sum((line.amount for line in income_lines), Decimal("0"))
        expense_total = sum((line.amount for line in expense_lines), Decimal("0"))

        return MonthlyReport(
            year_month="2024-01",
            income_lines=income_lines,
            expense_lines=expense_lines,
            income_total=income_total,
            expense_total=expense_total,
            net=income_total - expense_total,
        )

    def test_has_income_section_title(self) -> None:
        """Output contains 'Income' section title."""
        from pyfintracker.reports import render_monthly_report

        report = self._make_report(
            income=[(15, "Income:Salary", "3000000", "3000000")],
            expenses=[(3, "Expenses:Rent", "1000000", "-1000000")],
        )
        buf = StringIO()
        console = Console(file=buf, width=80, force_terminal=True)
        render_monthly_report(report, console)
        output = buf.getvalue()

        assert "Income" in output
        assert "Expenses" in output
        assert "Net" in output
        assert "Monthly Report" in output and "2024-01" in output

    def test_income_amount_green(self) -> None:
        """Income amounts are rendered with green (ANSI)."""
        from pyfintracker.reports import render_monthly_report

        report = self._make_report(
            income=[(15, "Income:Salary", "3000000", "3000000")],
        )
        buf = StringIO()
        console = Console(file=buf, width=80, force_terminal=True)
        render_monthly_report(report, console)
        output = buf.getvalue()

        assert ANSI_GREEN in output

    def test_expense_amount_red(self) -> None:
        """Expense amounts are rendered with red (ANSI)."""
        from pyfintracker.reports import render_monthly_report

        report = self._make_report(
            expenses=[(3, "Expenses:Rent", "1000000", "-1000000")],
        )
        buf = StringIO()
        console = Console(file=buf, width=80, force_terminal=True)
        render_monthly_report(report, console)
        output = buf.getvalue()

        assert ANSI_RED in output

    def test_footer_total_bold(self) -> None:
        """Footer total row uses bold (ANSI)."""
        from pyfintracker.reports import render_monthly_report

        report = self._make_report(
            income=[(15, "Income:Salary", "3000000", "3000000")],
            expenses=[(3, "Expenses:Rent", "1000000", "-1000000")],
        )
        buf = StringIO()
        console = Console(file=buf, width=80, force_terminal=True)
        render_monthly_report(report, console)
        output = buf.getvalue()

        assert ANSI_BOLD in output

    def test_net_positive_green(self) -> None:
        """Positive net amount renders green (ANSI)."""
        from pyfintracker.reports import render_monthly_report

        report = self._make_report(
            income=[(15, "Income:Salary", "3000000", "3000000")],
            expenses=[(3, "Expenses:Rent", "1000000", "-1000000")],
        )
        buf = StringIO()
        console = Console(file=buf, width=80, force_terminal=True)
        render_monthly_report(report, console)
        output = buf.getvalue()

        assert ANSI_GREEN in output

    def test_net_negative_red(self) -> None:
        """Negative net amount renders red (ANSI)."""
        from pyfintracker.reports import render_monthly_report

        report = self._make_report(
            income=[(15, "Income:Salary", "500000", "500000")],
            expenses=[(3, "Expenses:Rent", "1000000", "-1000000")],
        )
        buf = StringIO()
        console = Console(file=buf, width=80, force_terminal=True)
        render_monthly_report(report, console)
        output = buf.getvalue()

        # Net should be negative (500000 - 1000000 = -500000)
        assert ANSI_RED in output

    def test_empty_month(self) -> None:
        """Empty report (no lines) still renders sections."""
        from pyfintracker.reports import render_monthly_report

        report = self._make_report()
        buf = StringIO()
        console = Console(file=buf, width=80, force_terminal=True)
        render_monthly_report(report, console)
        output = buf.getvalue()

        assert "Income" in output
        assert "Expenses" in output
        assert "Net" in output


@pytest.mark.snapshot
class TestRenderBalance:
    """T-6.5: render_balance output structure."""

    def test_has_net_worth_footer(self) -> None:
        """Output contains 'Net worth:' bold footer."""
        from pyfintracker.reports import render_balance

        report = BalanceReport(
            lines=[
                BalanceLine(account_name="Assets:Checking", account_kind="Assets", balance=Decimal("1550000")),
            ],
            net_worth=Decimal("1550000"),
        )
        buf = StringIO()
        console = Console(file=buf, width=80, force_terminal=True)
        render_balance(report, console)
        output = buf.getvalue()

        assert "Net worth:" in output
        assert ANSI_BOLD in output

    def test_has_balance_title(self) -> None:
        """Output contains 'Balance Report' title."""
        from pyfintracker.reports import render_balance

        report = BalanceReport(lines=[], net_worth=Decimal("0"))
        buf = StringIO()
        console = Console(file=buf, width=80, force_terminal=True)
        render_balance(report, console)
        output = buf.getvalue()

        assert "Balance Report" in output

    def test_groups_by_kind(self) -> None:
        """Output contains section headers for each account kind."""
        from pyfintracker.reports import render_balance

        report = BalanceReport(
            lines=[
                BalanceLine(account_name="Assets:Checking", account_kind="Assets", balance=Decimal("1550000")),
                BalanceLine(account_name="Liabilities:CreditCard", account_kind="Liabilities", balance=Decimal("500000")),
            ],
            net_worth=Decimal("1050000"),
        )
        buf = StringIO()
        console = Console(file=buf, width=80, force_terminal=True)
        render_balance(report, console)
        output = buf.getvalue()

        assert "Assets" in output
        assert "Liabilities" in output

    def test_balance_colors(self) -> None:
        """Positive balances green, negative red (ANSI)."""
        from pyfintracker.reports import render_balance

        report = BalanceReport(
            lines=[
                BalanceLine(account_name="Assets:Checking", account_kind="Assets", balance=Decimal("1550000")),
                BalanceLine(account_name="Liabilities:CreditCard", account_kind="Liabilities", balance=Decimal("-50000")),
            ],
            net_worth=Decimal("1500000"),
        )
        buf = StringIO()
        console = Console(file=buf, width=80, force_terminal=True)
        render_balance(report, console)
        output = buf.getvalue()

        assert ANSI_GREEN in output
        assert ANSI_RED in output

    def test_net_worth_positive_green(self) -> None:
        """Positive net worth renders green (ANSI)."""
        from pyfintracker.reports import render_balance

        report = BalanceReport(
            lines=[
                BalanceLine(account_name="Assets:Checking", account_kind="Assets", balance=Decimal("1550000")),
            ],
            net_worth=Decimal("1550000"),
        )
        buf = StringIO()
        console = Console(file=buf, width=80, force_terminal=True)
        render_balance(report, console)
        output = buf.getvalue()

        assert ANSI_GREEN in output

    def test_net_worth_negative_red(self) -> None:
        """Negative net worth renders red (ANSI)."""
        from pyfintracker.reports import render_balance

        report = BalanceReport(
            lines=[
                BalanceLine(account_name="Liabilities:CreditCard", account_kind="Liabilities", balance=Decimal("-500000")),
            ],
            net_worth=Decimal("-500000"),
        )
        buf = StringIO()
        console = Console(file=buf, width=80, force_terminal=True)
        render_balance(report, console)
        output = buf.getvalue()

        assert ANSI_RED in output
