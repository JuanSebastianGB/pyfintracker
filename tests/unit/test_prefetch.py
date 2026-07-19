"""Cross-currency prefetch tests for compute_balance and compute_monthly_report.

These tests verify that the FX rate prefetch loop runs and warms the cache
before per-row conversion. Regression: catches mutmut_25/31/33/35/38 which
disable or invert the prefetch guards.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from pyfintracker.db import get_session

# ── Monthly report prefetch ──────────────────────────────────────────────────


class TestMonthlyReportPrefetch:
    """T-6.2 (prefetch): compute_monthly_report FX prefetch."""

    def test_cross_currency_prefetch_required(self, reports_engine_with_rates) -> None:
        """Cross-currency reporting must trigger the FX prefetch path."""
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
                {"tid": txn_id, "aid": accts["Income:Salary"], "amt": "-10", "cur": "USD"},
            )
            conn.execute(
                text(
                    "INSERT INTO postings (transaction_id, account_id, amount, currency) VALUES (:tid, :aid, :amt, :cur)"
                ),
                {"tid": txn_id, "aid": accts["Assets:Checking"], "amt": "10", "cur": "USD"},
            )

        with get_session(eng) as conn:
            report_default = compute_monthly_report(conn, "2026-07")
            report_cop = compute_monthly_report(conn, "2026-07", display_currency="COP")

        # Default currency is COP; USD income is converted at txn date (4000 COP/USD)
        assert report_default.income_total == Decimal("40000")
        # Explicit display_currency=COP must match the default
        assert report_cop.income_total == Decimal("40000")
        assert report_cop.currency == "COP"

    def test_cross_currency_prefetch_calls_get_rate_once(
        self,
        reports_engine_with_rates,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cross-currency prefetch must warm the cache so per-row converts reuse it.

        Regression: kills mutmut_33/35/38 (prefetch disabled or inverted).
        """
        from pyfintracker.fx import get_rate as fx_get_rate
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
            for acct, amt in [("Income:Salary", "-10"), ("Assets:Checking", "10")]:
                conn.execute(
                    text(
                        "INSERT INTO postings (transaction_id, account_id, amount, currency) "
                        "VALUES (:tid, :aid, :amt, :cur)"
                    ),
                    {"tid": txn_id, "aid": accts[acct], "amt": amt, "cur": "USD"},
                )

        call_count = [0]
        original = fx_get_rate

        def counting(*args, **kwargs):
            call_count[0] += 1
            return original(*args, **kwargs)

        # Patch both call sites: reports.get_rate (prefetch, module-level
        # import) and fx.get_rate (per-row via fx.convert, looked up in fx.globals).
        monkeypatch.setattr("pyfintracker.reports.get_rate", counting)
        monkeypatch.setattr("pyfintracker.fx.get_rate", counting)

        with get_session(eng) as conn:
            compute_monthly_report(conn, "2026-07", display_currency="COP")

        # 1 prefetch call (USD→COP) + 2 per-row calls = 3 total.
        # Without prefetch (mutmut_33/35/38) the count drops to 2.
        assert call_count[0] == 3

    def test_prefetch_only_includes_foreign_currencies(self, reports_engine_with_rates) -> None:
        """Mixed-native and foreign postings must be converted independently."""
        from pyfintracker.reports import compute_monthly_report

        eng = reports_engine_with_rates
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Income:Salary', 'COP', 1, 'Income')"
                ),
            )
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Income:Bonus', 'USD', 1, 'Income')"
                ),
            )
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:Checking', 'COP', 1, 'Assets')"
                ),
            )
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES ('Assets:UsdBank', 'USD', 1, 'Assets')"
                ),
            )
            accts = {
                r.name: r.id for r in conn.execute(text("SELECT id, name FROM accounts")).fetchall()
            }

            txn_id = conn.execute(
                text(
                    "INSERT INTO transactions (date, description) VALUES ('2026-07-05', 'Multi') RETURNING id"
                ),
            ).scalar()
            for acct, amt, ccy in [
                ("Income:Salary", "-100000", "COP"),
                ("Assets:Checking", "100000", "COP"),
            ]:
                conn.execute(
                    text(
                        "INSERT INTO postings (transaction_id, account_id, amount, currency) "
                        "VALUES (:tid, :aid, :amt, :cur)"
                    ),
                    {"tid": txn_id, "aid": accts[acct], "amt": amt, "cur": ccy},
                )

            txn2_id = conn.execute(
                text(
                    "INSERT INTO transactions (date, description) VALUES ('2026-07-10', 'Bonus') RETURNING id"
                ),
            ).scalar()
            for acct, amt, ccy in [
                ("Income:Bonus", "-50", "USD"),
                ("Assets:UsdBank", "50", "USD"),
            ]:
                conn.execute(
                    text(
                        "INSERT INTO postings (transaction_id, account_id, amount, currency) "
                        "VALUES (:tid, :aid, :amt, :cur)"
                    ),
                    {"tid": txn2_id, "aid": accts[acct], "amt": amt, "cur": ccy},
                )

        with get_session(eng) as conn:
            report = compute_monthly_report(conn, "2026-07", display_currency="USD")

        # COP income: 100000 COP * 0.00025 (2026-07-05) = 25.00 USD (native prefetch)
        # USD income: 50 USD (no conversion)
        assert report.income_total == Decimal("75.00")


# ── Balance report prefetch ──────────────────────────────────────────────────


class TestBalanceReportPrefetch:
    """T-6.3 (prefetch): compute_balance FX prefetch."""

    def test_compute_balance_cross_currency_prefetch_calls_get_rate_once(
        self,
        reports_engine_with_rates,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cross-currency prefetch must warm the cache before per-row conversion.

        Regression: kills mutmut_25 (`!=` → `==` on the outer prefetch guard) and
        mutmut_31 (inverted inner pairing condition) which skip the prefetch
        without affecting per-row output.
        """
        from pyfintracker.fx import get_rate as fx_get_rate
        from pyfintracker.reports import compute_balance

        eng = reports_engine_with_rates
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES "
                    "('Assets:UsdAccount', 'USD', 1, 'Assets')"
                ),
            )
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) VALUES "
                    "('Assets:CopAccount', 'COP', 1, 'Assets')"
                ),
            )
            accts = {
                r.name: r.id for r in conn.execute(text("SELECT id, name FROM accounts")).fetchall()
            }
            for date_lbl, entries in [
                ("2026-07-05", [("Assets:UsdAccount", "100", "USD")]),
                ("2026-07-05", [("Assets:CopAccount", "100000", "COP")]),
            ]:
                txn_id = conn.execute(
                    text(
                        "INSERT INTO transactions (date, description) VALUES (:d, 'd') RETURNING id"
                    ),
                    {"d": date_lbl},
                ).scalar()
                for acct, amt, ccy in entries:
                    conn.execute(
                        text(
                            "INSERT INTO postings (transaction_id, account_id, amount, currency) "
                            "VALUES (:tid, :aid, :amt, :cur)"
                        ),
                        {"tid": txn_id, "aid": accts[acct], "amt": amt, "cur": ccy},
                    )

        call_count = [0]
        original = fx_get_rate

        def counting(*args, **kwargs):
            call_count[0] += 1
            return original(*args, **kwargs)

        # Patch both call sites: reports.get_rate (prefetch, module-level
        # import) and fx.get_rate (per-row via fx.convert, looked up in fx.globals).
        monkeypatch.setattr("pyfintracker.reports.get_rate", counting)
        monkeypatch.setattr("pyfintracker.fx.get_rate", counting)

        with get_session(eng) as conn:
            compute_balance(conn, display_currency="USD")

        # 1 prefetch call (COP→USD) + 1 per-row call (the COP posting
        # converts; the USD posting matches display_currency and is a fast-path
        # no-op) = 2 total.
        # Mutant mutmut_25 (outer `!=` → `==`) skips prefetch → 1 call.
        # Mutant mutmut_31 (inner `!=` → `==`) adds the USD==USD pair which the
        # fast-path returns immediately, so prefetch effectively does nothing →
        # 1 call.
        assert call_count[0] == 2
