"""Tests for the BalanceReport model + compute_balance."""

from __future__ import annotations

from datetime import UTC, date
from decimal import Decimal

import pydantic
import pytest
from sqlalchemy import text

from pyfintracker.db import get_session
from pyfintracker.models import Posting, Transaction


@pytest.mark.unit
class TestBalanceReportModels:
    """T-6.1: Pydantic BalanceReport model."""

    def test_balance_line_instantiate(self) -> None:
        """BalanceLine can be created with all fields."""
        from pyfintracker.reports import BalanceLine

        line = BalanceLine(
            account_name="Assets:Checking", account_kind="Assets", balance=Decimal("5000")
        )
        assert line.account_name == "Assets:Checking"
        assert line.account_kind == "Assets"
        assert line.balance == Decimal("5000")

    def test_balance_line_is_frozen(self) -> None:
        """BalanceLine cannot be modified after creation."""
        from pyfintracker.reports import BalanceLine

        line = BalanceLine(
            account_name="Assets:Checking", account_kind="Assets", balance=Decimal("5000")
        )
        with pytest.raises((AttributeError, TypeError, pydantic.ValidationError)):
            line.balance = Decimal("0")  # type: ignore[misc]

    def test_balance_report_instantiate(self) -> None:
        """BalanceReport can be created with all fields."""
        from pyfintracker.reports import BalanceLine, BalanceReport

        report = BalanceReport(
            lines=[
                BalanceLine(
                    account_name="Assets:Checking", account_kind="Assets", balance=Decimal("1000")
                ),
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

    def test_balance_report_currency_default(self) -> None:
        """BalanceReport defaults to COP currency."""
        from pyfintracker.reports import BalanceReport

        report = BalanceReport(lines=[], net_worth=Decimal("0"))
        assert report.currency == "COP"

    def test_balance_report_currency_custom(self) -> None:
        """BalanceReport accepts custom currency."""
        from pyfintracker.reports import BalanceReport

        report = BalanceReport(lines=[], net_worth=Decimal("0"), currency="EUR")
        assert report.currency == "EUR"

    def test_balance_report_serialize(self) -> None:
        """BalanceReport can be serialized to dict."""
        from pyfintracker.reports import BalanceReport

        report = BalanceReport(lines=[], net_worth=Decimal("0"))
        d = report.model_dump()
        assert d["net_worth"] == Decimal("0")
        assert d["lines"] == []


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
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Savings', 'COP', 1, 'Assets')"
                ),
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
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Liabilities:CreditCard', 'COP', 1, 'Liabilities')"
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

        from pyfintracker.repository import create_transaction_with_postings

        txn = Transaction(date=date(2024, 1, 1), description="CC charge")
        postings = [
            Posting(
                account_id=accts["Liabilities:CreditCard"],
                amount=Decimal("-500000"),
                currency="COP",
            ),
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
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Empty', 'COP', 1, 'Assets')"
                ),
            )

        with get_session(reports_engine) as conn:
            report = compute_balance(conn)

        names = [line.account_name for line in report.lines]
        assert "Assets:Empty" not in names

    def test_compute_balance_default_display_currency(
        self, reports_engine, seed_simple_month
    ) -> None:
        """Default display_currency is COP — identity for COP-only data."""
        from pyfintracker.reports import compute_balance

        with get_session(reports_engine) as conn:
            report = compute_balance(conn)

        assert report.currency == "COP"
        assert report.net_worth == Decimal("1550000")

    def test_compute_balance_same_currency_identity(
        self, reports_engine, seed_simple_month
    ) -> None:
        """Explicit display_currency='COP' produces byte-equal defaults."""
        from pyfintracker.reports import compute_balance

        with get_session(reports_engine) as conn:
            default = compute_balance(conn)
            explicit = compute_balance(conn, display_currency="COP")

        assert default.model_dump() == explicit.model_dump()

    def test_compute_balance_three_currencies_single_decimal(
        self, reports_engine_with_rates
    ) -> None:
        """3-currency accounts — net_worth is single Decimal in display_currency."""
        from pyfintracker.reports import compute_balance

        eng = reports_engine_with_rates
        with eng.begin() as conn:
            from datetime import datetime

            now_ts = datetime.now(UTC).isoformat()
            # Seed COP→USD and EUR→USD for conversion
            conn.execute(
                text(
                    "INSERT OR IGNORE INTO rates (base_currency, target_currency, rate, date, source, fetched_at) VALUES ('COP', 'USD', '0.00025', '2026-07-05', 'frankfurter', :now)"
                ),
                {"now": now_ts},
            )
            conn.execute(
                text(
                    "INSERT OR IGNORE INTO rates (base_currency, target_currency, rate, date, source, fetched_at) VALUES ('EUR', 'USD', '1.10', '2026-07-15', 'frankfurter', :now)"
                ),
                {"now": now_ts},
            )
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Checking', 'COP', 1, 'Assets')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:UsdAccount', 'USD', 1, 'Assets')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:EuroAccount', 'EUR', 1, 'Assets')"
                )
            )
            accts = {
                r.name: r.id for r in conn.execute(text("SELECT id, name FROM accounts")).fetchall()
            }

        from pyfintracker.repository import create_transaction_with_postings

        # Three separate transactions, each in native currency. No cross-currency postings.
        txn1 = Transaction(date=date(2026, 7, 5), description="Salary")
        with get_session(eng) as conn:
            create_transaction_with_postings(
                conn,
                txn1,
                [
                    Posting(
                        account_id=accts["Assets:Checking"], amount=Decimal("50000"), currency="COP"
                    ),
                    Posting(
                        account_id=accts["Assets:UsdAccount"],
                        amount=Decimal("-50000"),
                        currency="COP",
                    ),
                ],
            )
        txn2 = Transaction(date=date(2026, 7, 10), description="USD deposit")
        with get_session(eng) as conn:
            create_transaction_with_postings(
                conn,
                txn2,
                [
                    Posting(
                        account_id=accts["Assets:UsdAccount"], amount=Decimal("100"), currency="USD"
                    ),
                    Posting(
                        account_id=accts["Assets:Checking"], amount=Decimal("-100"), currency="USD"
                    ),
                ],
            )
        txn3 = Transaction(date=date(2026, 7, 15), description="EUR deposit")
        with get_session(eng) as conn:
            create_transaction_with_postings(
                conn,
                txn3,
                [
                    Posting(
                        account_id=accts["Assets:EuroAccount"],
                        amount=Decimal("200"),
                        currency="EUR",
                    ),
                    Posting(
                        account_id=accts["Assets:UsdAccount"],
                        amount=Decimal("-200"),
                        currency="EUR",
                    ),
                ],
            )

        with get_session(eng) as conn:
            report = compute_balance(conn, display_currency="USD")

        assert report.currency == "USD"
        # All transactions balance out — net is 0. Verify individual accounts:
        accts = {ln.account_name: ln.balance for ln in report.lines}
        assert accts["Assets:Checking"] == Decimal("-87.50")
        assert accts["Assets:EuroAccount"] == Decimal("220")
        assert isinstance(report.net_worth, Decimal)

    def test_compute_balance_uses_txn_date_not_as_of(self, reports_engine_with_rates) -> None:
        """as_of filter doesn't affect conversion date — postings convert at txn date."""
        from pyfintracker.reports import compute_balance

        # Seed a simple COP balance and a USD balance
        eng = reports_engine_with_rates
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Checking', 'COP', 1, 'Assets')"
                ),
            )
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:UsdAccount', 'USD', 1, 'Assets')"
                ),
            )
            accts = {
                r.name: r.id for r in conn.execute(text("SELECT id, name FROM accounts")).fetchall()
            }

        from pyfintracker.repository import create_transaction_with_postings

        txn1 = Transaction(date=date(2026, 7, 5), description="Salary")
        postings1 = [
            Posting(account_id=accts["Assets:Checking"], amount=Decimal("50000"), currency="COP"),
            Posting(
                account_id=accts["Assets:UsdAccount"], amount=Decimal("-50000"), currency="COP"
            ),
        ]
        with get_session(eng) as conn:
            create_transaction_with_postings(conn, txn1, postings1)

        with get_session(eng) as conn:
            report = compute_balance(conn, display_currency="USD")

        assert report.currency == "USD"
        # Checking: 50000 COP * 0.00025 = 12.50 USD
        checking = [ln for ln in report.lines if ln.account_name == "Assets:Checking"]
        assert len(checking) == 1
        assert checking[0].balance == Decimal("12.50")

    def test_compute_balance_as_of_excludes_post_as_of(
        self,
        reports_engine_with_rates,
    ) -> None:
        """as_of filter must drop postings dated after the cutoff."""
        from pyfintracker.reports import compute_balance

        eng = reports_engine_with_rates
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Checking', 'COP', 1, 'Assets')"
                ),
            )
            accts = {
                r.name: r.id for r in conn.execute(text("SELECT id, name FROM accounts")).fetchall()
            }
            for txn_date, amount in [("2026-07-05", "100"), ("2026-07-25", "200")]:
                txn_id = conn.execute(
                    text(
                        "INSERT INTO transactions (date, description) VALUES (:date, 'd') RETURNING id"
                    ),
                    {"date": txn_date},
                ).scalar()
                conn.execute(
                    text(
                        "INSERT INTO postings (transaction_id, account_id, amount, currency) "
                        "VALUES (:tid, :aid, :amt, :cur)"
                    ),
                    {"tid": txn_id, "aid": accts["Assets:Checking"], "amt": amount, "cur": "COP"},
                )

        with get_session(eng) as conn:
            full = compute_balance(conn)
            cutoff = compute_balance(conn, as_of=date(2026, 7, 10))

        assert full.net_worth == Decimal("300")
        assert cutoff.net_worth == Decimal("100")

    def test_compute_balance_as_of_with_foreign_currency(
        self,
        reports_engine_with_rates,
    ) -> None:
        """as_of filtering must apply to postings before conversion."""
        from pyfintracker.reports import compute_balance

        eng = reports_engine_with_rates
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:UsdAccount', 'USD', 1, 'Assets')"
                ),
            )
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Liabilities:CreditCard', 'USD', 1, 'Liabilities')"
                ),
            )
            accts = {
                r.name: r.id for r in conn.execute(text("SELECT id, name FROM accounts")).fetchall()
            }
            for txn_date, src, dst, amt in [
                ("2026-07-05", "Assets:UsdAccount", "Liabilities:CreditCard", "50"),
                ("2026-07-25", "Assets:UsdAccount", "Liabilities:CreditCard", "30"),
            ]:
                txn_id = conn.execute(
                    text(
                        "INSERT INTO transactions (date, description) VALUES (:date, 'd') RETURNING id"
                    ),
                    {"date": txn_date},
                ).scalar()
                conn.execute(
                    text(
                        "INSERT INTO postings (transaction_id, account_id, amount, currency) "
                        "VALUES (:tid, :aid, :amt, :cur)"
                    ),
                    {"tid": txn_id, "aid": accts[src], "amt": amt, "cur": "USD"},
                )
                conn.execute(
                    text(
                        "INSERT INTO postings (transaction_id, account_id, amount, currency) "
                        "VALUES (:tid, :aid, :amt, :cur)"
                    ),
                    {"tid": txn_id, "aid": accts[dst], "amt": f"-{amt}", "cur": "USD"},
                )

        with get_session(eng) as conn:
            full = compute_balance(conn, display_currency="USD")
            cutoff = compute_balance(conn, display_currency="USD", as_of=date(2026, 7, 10))

        # Two balancing postings across Assets and Liabilities each:
        # full net_worth = Asset 160 (50+30*4000 conv) - Liab -160 = 0; compute_balance
        # stores positive balances for both kinds because negative netting occurs at
        # render time. Verify both the asset and liability tally and as_of cutoff.
        assert full.lines[0].balance == Decimal("80")  # Assets:UsdAccount
        assert full.lines[1].balance == Decimal("80")  # Liabilities:CreditCard
        # Net worth is unsigned sum of balances per-account.
        assert full.net_worth == Decimal("160")
        # as_of=2026-07-10 only keeps 2026-07-05 USD postings (50 USD each, same sign).
        assert cutoff.net_worth == Decimal("100")

    def test_compute_balance_equity_minus_amount(self, reports_engine) -> None:
        """Equity postings must subtract from the running balance, like Liabilities."""
        from pyfintracker.reports import compute_balance

        eng = reports_engine
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Equity:Opening', 'COP', 0, 'Equity')"
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
                    "INSERT INTO transactions (date, description) VALUES ('2024-01-01', 'Open') RETURNING id"
                ),
            ).scalar()
            conn.execute(
                text(
                    "INSERT INTO postings (transaction_id, account_id, amount, currency) VALUES (:tid, :aid, :amt, :cur)"
                ),
                {"tid": txn_id, "aid": accts["Equity:Opening"], "amt": "1000", "cur": "COP"},
            )
            conn.execute(
                text(
                    "INSERT INTO postings (transaction_id, account_id, amount, currency) VALUES (:tid, :aid, :amt, :cur)"
                ),
                {"tid": txn_id, "aid": accts["Assets:Checking"], "amt": "-1000", "cur": "COP"},
            )

        with get_session(eng) as conn:
            report = compute_balance(conn)

        equity = [ln for ln in report.lines if ln.account_kind == "Equity"]
        assert len(equity) == 1
        # Equity:Opening has 1000 COP original, but liabilities-style sign flip → -1000.
        assert equity[0].balance == Decimal("-1000")

    def test_compute_balance_usd_to_cop_conversion(self, reports_engine_with_rates) -> None:
        """USD balances must convert at txn-date rate when display_currency=COP."""
        from pyfintracker.reports import compute_balance

        eng = reports_engine_with_rates
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:UsdAccount', 'USD', 1, 'Assets')"
                ),
            )
            accts = {
                r.name: r.id for r in conn.execute(text("SELECT id, name FROM accounts")).fetchall()
            }
            txn_id = conn.execute(
                text(
                    "INSERT INTO transactions (date, description) VALUES ('2026-07-05', 'd') RETURNING id"
                ),
            ).scalar()
            conn.execute(
                text(
                    "INSERT INTO postings (transaction_id, account_id, amount, currency) VALUES (:tid, :aid, :amt, :cur)"
                ),
                {"tid": txn_id, "aid": accts["Assets:UsdAccount"], "amt": "100", "cur": "USD"},
            )

        with get_session(eng) as conn:
            # as_of= triggers the cross-currency branch; COP display converts USD → COP.
            report = compute_balance(conn, display_currency="COP", as_of=date(2026, 7, 5))

        assert len(report.lines) == 1
        # 100 USD * 4000 COP/USD (from fixture rates for 2026-07-05)
        assert report.lines[0].balance == Decimal("400000")
        assert report.net_worth == Decimal("400000")
        # Currency tag flows from display_currency, not from posting currency.
        assert report.currency == "COP"
