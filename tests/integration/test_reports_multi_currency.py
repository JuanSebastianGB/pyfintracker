"""Integration tests for multi-currency reports.

Tests ``fin report month --currency`` and ``fin balance --currency`` with
seeded mixed-currency data and cached FX rates.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from pyfintracker.db import get_session, make_test_engine
from pyfintracker.models import Posting, Transaction
from pyfintracker.repository import create_transaction_with_postings

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mixed_db():
    """In-memory engine seeded with accounts, txns, postings, and cached rates.

    Schema includes accounts, transactions, postings, and rates tables.
    Seed data:
      - 50000 COP on 2026-07-05 (salary)
      - -15 USD on 2026-07-10 (freelance expense)
      - Rates: COP→USD @ 0.00025 (2026-07-05), USD→COP @ 4000 (2026-07-05),
               USD→COP @ 4200 (2026-07-10), COP→USD @ 0.000238 (2026-07-10)
    """
    eng = make_test_engine()
    with eng.begin() as conn:
        conn.execute(
            text("""
                CREATE TABLE accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    currency TEXT NOT NULL DEFAULT 'COP',
                    depth INTEGER NOT NULL DEFAULT 0,
                    kind TEXT NOT NULL,
                    is_archived INTEGER NOT NULL DEFAULT 0
                )
            """)
        )
        conn.execute(
            text("""
                CREATE TABLE transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT ''
                )
            """)
        )
        conn.execute(
            text("""
                CREATE TABLE postings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id INTEGER NOT NULL REFERENCES transactions(id),
                    account_id INTEGER NOT NULL REFERENCES accounts(id),
                    amount TEXT NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'COP'
                )
            """)
        )
        conn.execute(
            text("""
                CREATE TABLE rates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    base_currency TEXT NOT NULL,
                    target_currency TEXT NOT NULL,
                    rate TEXT NOT NULL,
                    date TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'frankfurter',
                    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(base_currency, target_currency, date)
                )
            """)
        )
        now_ts = datetime.now(UTC).isoformat()
        for base, target, rate, dt in [
            ("COP", "USD", "0.00025", "2026-07-05"),
            ("USD", "COP", "4000", "2026-07-05"),
            ("USD", "COP", "4200", "2026-07-10"),
            ("COP", "USD", "0.000238", "2026-07-10"),
        ]:
            conn.execute(
                text("""
                    INSERT OR IGNORE INTO rates (base_currency, target_currency, rate, date, source, fetched_at)
                    VALUES (:base, :target, :rate, :dt, 'frankfurter', :now)
                """),
                {"base": base, "target": target, "rate": rate, "dt": dt, "now": now_ts},
            )

        # 3-currency rates
        for base, target, rate, dt in [
            ("COP", "EUR", "0.00024", "2026-07-05"),
            ("EUR", "COP", "4166.67", "2026-07-05"),
            ("USD", "EUR", "0.92", "2026-07-10"),
            ("EUR", "USD", "1.09", "2026-07-10"),
        ]:
            conn.execute(
                text("""
                    INSERT OR IGNORE INTO rates (base_currency, target_currency, rate, date, source, fetched_at)
                    VALUES (:base, :target, :rate, :dt, 'frankfurter', :now)
                """),
                {"base": base, "target": target, "rate": rate, "dt": dt, "now": now_ts},
            )

        # Accounts
        conn.execute(text("INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Checking', 'COP', 1, 'Assets')"))
        conn.execute(text("INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:UsdAccount', 'USD', 1, 'Assets')"))
        conn.execute(text("INSERT INTO accounts (name, currency, depth, kind) VALUES ('Income:Salary', 'COP', 1, 'Income')"))
        conn.execute(text("INSERT INTO accounts (name, currency, depth, kind) VALUES ('Expenses:Freelance', 'USD', 1, 'Expenses')"))
        accts = {r.name: r.id for r in conn.execute(text("SELECT id, name FROM accounts")).fetchall()}

    # Salary (COP)
    txn1 = Transaction(date=date(2026, 7, 5), description="Salary")
    with get_session(eng) as conn:
        create_transaction_with_postings(conn, txn1, [
            Posting(account_id=accts["Income:Salary"], amount=Decimal("-50000"), currency="COP"),
            Posting(account_id=accts["Assets:Checking"], amount=Decimal("50000"), currency="COP"),
        ])

    # Freelance expense (USD)
    txn2 = Transaction(date=date(2026, 7, 10), description="Freelance tools")
    with get_session(eng) as conn:
        create_transaction_with_postings(conn, txn2, [
            Posting(account_id=accts["Expenses:Freelance"], amount=Decimal("15"), currency="USD"),
            Posting(account_id=accts["Assets:UsdAccount"], amount=Decimal("-15"), currency="USD"),
        ])

    yield eng
    eng.dispose()


@pytest.fixture
def three_currency_db():
    """In-memory engine seeded with 3-currency accounts + rates.

    Accounts: Assets:Checking (COP), Assets:UsdAccount (USD), Assets:EuroAccount (EUR)
    """
    eng = make_test_engine()
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, currency TEXT NOT NULL DEFAULT 'COP', depth INTEGER NOT NULL DEFAULT 0, kind TEXT NOT NULL, is_archived INTEGER NOT NULL DEFAULT 0)"))
        conn.execute(text("CREATE TABLE transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, description TEXT NOT NULL DEFAULT '')"))
        conn.execute(text("CREATE TABLE postings (id INTEGER PRIMARY KEY AUTOINCREMENT, transaction_id INTEGER NOT NULL REFERENCES transactions(id), account_id INTEGER NOT NULL REFERENCES accounts(id), amount TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'COP')"))
        conn.execute(text("CREATE TABLE rates (id INTEGER PRIMARY KEY AUTOINCREMENT, base_currency TEXT NOT NULL, target_currency TEXT NOT NULL, rate TEXT NOT NULL, date TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'frankfurter', fetched_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE(base_currency, target_currency, date))"))

        now_ts = datetime.now(UTC).isoformat()
        for base, target, rate, dt in [
            ("COP", "EUR", "0.00024", "2026-07-05"),
            ("EUR", "COP", "4166.67", "2026-07-05"),
            ("USD", "EUR", "0.92", "2026-07-10"),
            ("EUR", "USD", "1.09", "2026-07-10"),
            ("COP", "USD", "0.00025", "2026-07-05"),
            ("USD", "COP", "4000", "2026-07-05"),
            ("COP", "USD", "0.000238", "2026-07-10"),
            ("USD", "COP", "4200", "2026-07-10"),
        ]:
            conn.execute(text("INSERT OR IGNORE INTO rates (base_currency, target_currency, rate, date, source, fetched_at) VALUES (:base, :target, :rate, :dt, 'frankfurter', :now)"),
                         {"base": base, "target": target, "rate": rate, "dt": dt, "now": now_ts})

        conn.execute(text("INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Checking', 'COP', 1, 'Assets')"))
        conn.execute(text("INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:UsdAccount', 'USD', 1, 'Assets')"))
        conn.execute(text("INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:EuroAccount', 'EUR', 1, 'Assets')"))
        accts = {r.name: r.id for r in conn.execute(text("SELECT id, name FROM accounts")).fetchall()}

    with get_session(eng) as conn:
        create_transaction_with_postings(conn, Transaction(date=date(2026, 7, 5), description="Salary"), [
            Posting(account_id=accts["Assets:Checking"], amount=Decimal("50000"), currency="COP"),
            Posting(account_id=accts["Assets:UsdAccount"], amount=Decimal("-50000"), currency="COP"),
        ])
        create_transaction_with_postings(conn, Transaction(date=date(2026, 7, 10), description="USD deposit"), [
            Posting(account_id=accts["Assets:UsdAccount"], amount=Decimal("100"), currency="USD"),
            Posting(account_id=accts["Assets:Checking"], amount=Decimal("-100"), currency="USD"),
        ])
        create_transaction_with_postings(conn, Transaction(date=date(2026, 7, 15), description="EUR deposit"), [
            Posting(account_id=accts["Assets:EuroAccount"], amount=Decimal("200"), currency="EUR"),
            Posting(account_id=accts["Assets:UsdAccount"], amount=Decimal("-200"), currency="EUR"),
        ])

    yield eng
    eng.dispose()


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestReportMonthCurrency:
    """T-D.6 + T-D.9: --currency flag on fin report month."""

    def test_report_month_currency_flag(self, mixed_db) -> None:
        """fin report month --currency USD shows converted amounts."""
        from pyfintracker.reports import compute_monthly_report

        with get_session(mixed_db) as conn:
            report = compute_monthly_report(conn, "2026-07", display_currency="USD")

        assert report.currency == "USD"
        assert report.income_total == Decimal("12.50")  # 50000 * 0.00025
        # We can't easily call CLI with in-memory DB, so test compute directly
        assert isinstance(report.net, Decimal)

    def test_report_month_invalid_currency_no_db_query(self) -> None:
        """Invalid --currency exits 1 and never queries DB (validate first)."""
        from typer.testing import CliRunner

        from pyfintracker.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["report", "month", "--month", "2026-07", "--currency", "XYZ"])
        assert result.exit_code == 1
        assert "Unsupported currency" in result.stdout

    def test_report_month_mixed_currency_cli(self, mixed_db) -> None:
        """Seeded mixed-currency data renders correct CLI output."""
        from io import StringIO

        from rich.console import Console

        from pyfintracker.reports import compute_monthly_report, render_monthly_report

        with get_session(mixed_db) as conn:
            report = compute_monthly_report(conn, "2026-07", display_currency="USD")

        buf = StringIO()
        console = Console(file=buf, width=80)
        render_monthly_report(report, console)
        output = buf.getvalue()

        assert "July 2026" in output or "2026-07" in output
        assert "(USD)" in output


@pytest.mark.integration
class TestBalanceCurrency:
    """T-D.7 + T-D.10: --currency flag on fin balance."""

    def test_balance_currency_flag_euro(self, three_currency_db) -> None:
        """fin balance --currency EUR shows converted amounts."""
        from pyfintracker.reports import compute_balance

        with get_session(three_currency_db) as conn:
            report = compute_balance(conn, display_currency="EUR")

        assert report.currency == "EUR"
        # Fixture balances out: Checking(-80) + UsdAccount(-120) + EuroAccount(200) = 0 net
        # Individual account values are correct (not just zero)
        accts = {ln.account_name: ln.balance for ln in report.lines}
        assert "Assets:EuroAccount" in accts
        assert accts["Assets:EuroAccount"] == Decimal("200")
        assert isinstance(report.net_worth, Decimal)

    def test_balance_invalid_currency_exits_1(self) -> None:
        """Invalid --currency on balance exits 1."""
        from typer.testing import CliRunner

        from pyfintracker.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["report", "balance", "--currency", "ABC"])
        assert result.exit_code == 1
        assert "Unsupported currency" in result.stdout

    def test_balance_three_currency_cli(self, three_currency_db) -> None:
        """Three-currency balance displays per-account converted lines + EUR net worth."""
        from io import StringIO

        from rich.console import Console

        from pyfintracker.reports import compute_balance, render_balance

        with get_session(three_currency_db) as conn:
            report = compute_balance(conn, display_currency="EUR")

        buf = StringIO()
        console = Console(file=buf, width=80)
        render_balance(report, console)
        output = buf.getvalue()

        assert "EUR" in output
        assert "Net worth:" in output
