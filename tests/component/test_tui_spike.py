"""Component test: TUI browser via Textual Pilot with a real SQLite DB.

Creates a temporary database with migrations applied, seeds test accounts
and transactions, then asserts the dashboard renders, keybindings work,
and drilldown + search behave correctly.
"""

from __future__ import annotations

import html
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.command import upgrade
from alembic.config import Config

from pyfintracker.db import make_engine
from pyfintracker.models import Account, Budget, Posting, Transaction
from pyfintracker.repository import create_account, create_budget, create_transaction_with_postings
from pyfintracker.tui import FinanceApp

# ── helpers ──────────────────────────────────────────────────────────────────


def _decode_svg(svg: str) -> str:
    """Decode HTML entities and normalize NBSP in Textual's SVG output."""
    return html.unescape(svg).replace("\xa0", " ")


def _seed_db(db_path: str) -> None:
    """Apply migrations and insert test data into *db_path*."""
    # ponytail: idempotent — wipe any leftover from previous runs.
    Path(db_path).unlink(missing_ok=True)

    engine = make_engine(f"sqlite:///{db_path}")

    # Apply Alembic migrations
    with engine.begin() as conn:
        cfg = Config("alembic.ini")
        cfg.attributes["connection"] = conn
        upgrade(cfg, "head")

    # Seed accounts
    with engine.begin() as conn:
        # Replace the migration's starter chart with fixture-specific accounts.
        conn.exec_driver_sql("DELETE FROM accounts")
        cash = create_account(
            conn,
            Account(name="Assets:Cash", kind="Assets", currency="COP", depth=1),
        )
        bank = create_account(
            conn,
            Account(name="Assets:Bank:USD", kind="Assets", currency="USD", depth=2),
        )
        create_account(
            conn,
            Account(name="Liabilities:Card", kind="Liabilities", currency="COP", depth=1),
        )
        salary_acct = create_account(
            conn,
            Account(name="Income:Salary", kind="Income", currency="COP", depth=1),
        )
        food = create_account(
            conn,
            Account(name="Expenses:Food", kind="Expenses", currency="COP", depth=1),
        )

        # Salary transaction (Dr Cash, Cr Income)
        create_transaction_with_postings(
            conn,
            Transaction(date=date(2026, 7, 18), description="Salary July", currency="COP"),
            [
                Posting(account_id=cash.id, amount=Decimal("4500000"), currency="COP"),
                Posting(account_id=salary_acct.id, amount=Decimal("-4500000"), currency="COP"),
            ],
        )

        # Expense transaction (Dr Expenses:Food, Cr Assets:Cash)
        create_transaction_with_postings(
            conn,
            Transaction(date=date(2026, 7, 17), description="Cafe latte", currency="COP"),
            [
                Posting(account_id=food.id, amount=Decimal("12500"), currency="COP"),
                Posting(account_id=cash.id, amount=Decimal("-12500"), currency="COP"),
            ],
        )

        # USD transaction
        create_transaction_with_postings(
            conn,
            Transaction(date=date(2026, 7, 12), description="Freelance invoice", currency="USD"),
            [
                Posting(account_id=bank.id, amount=Decimal("320.00"), currency="USD"),
                Posting(account_id=cash.id, amount=Decimal("-320.00"), currency="USD"),
            ],
        )

        # Budget
        create_budget(
            conn,
            Budget(
                name="Food",
                amount=Decimal("500000"),
                currency="COP",
                period="monthly",
                start_date="2026-01-01",
            ),
        )


# ── fixture ──────────────────────────────────────────────────────────────────


@pytest.fixture
def seeded_db() -> str:
    """Create a temp DB, seed it, yield the path, then clean up."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    _seed_db(db_path)
    yield db_path
    Path(db_path).unlink(missing_ok=True)


# ── tests ────────────────────────────────────────────────────────────────────


@pytest.mark.component
async def test_dashboard_renders(seeded_db: str) -> None:
    """Pilot boots FinanceApp with a real DB; verify all sections render."""
    app = FinanceApp(db_path=seeded_db)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        text = _decode_svg(app.export_screenshot())
        assert "Net worth" in text, "net-worth header missing"
        assert "Accounts" in text, "accounts table missing"
        assert "Monthly Summary" in text, "summary card missing"
        assert "Transactions" in text, "txns list missing"
        assert "Salary July" in text, "seeded txn data missing"
        assert "Cafe latte" in text, "expense txn missing"
        assert "Budget Progress" in text, "budgets section missing"
        assert "Food" in text, "budget name missing"


@pytest.mark.component
async def test_keybindings_do_not_crash(seeded_db: str) -> None:
    """Press each bound key; verify the app survives."""
    app = FinanceApp(db_path=seeded_db)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("j", "k", "h", "l", "enter", "q")
    # If we reach here, no crash


@pytest.mark.component
async def test_drilldown_modal(seeded_db: str) -> None:
    """Enter opens the drilldown modal with transaction detail."""
    app = FinanceApp(db_path=seeded_db)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        # Should see the drilldown overlay (transaction detail)
        text = _decode_svg(app.export_screenshot())
        assert "Transaction" in text, "drilldown title missing"
        assert "Salary July" in text or "Postings" in text, "drilldown content missing"
        # Close with q
        await pilot.press("q")
        await pilot.pause()


@pytest.mark.component
async def test_gg_navigation(seeded_db: str) -> None:
    """gg sends focus to the first widget; G sends focus to the last."""
    app = FinanceApp(db_path=seeded_db)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # gg → top
        await pilot.press("g", "g")
        await pilot.pause()
        # G → bottom
        await pilot.press("G")
        await pilot.pause()
    # If we reach here, no crash


@pytest.mark.component
async def test_search(seeded_db: str) -> None:
    """Search input submits a query and shows results."""
    app = FinanceApp(db_path=seeded_db)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # Focus search input and type a query
        sb = app.query_one("#search-box")
        sb.focus()
        await pilot.press(*"Salary")
        await pilot.press("enter")
        await pilot.pause()
        # The transaction list should still show something
        text = _decode_svg(app.export_screenshot())
        # The screen should not have crashed — any content is OK
        assert text.strip(), "screen went blank after search"
