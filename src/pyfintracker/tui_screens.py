"""Screen classes for the Textual TUI browser.

DashboardScreen — main dashboard with net-worth header, accounts grouped by
kind, recent transactions (or FTS search results), monthly summary card, and
budget progress bars.  DrilldownScreen — transaction detail modal on Enter.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from contextlib import suppress
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import Connection, text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Footer, Header, Input, Static

from pyfintracker.db import make_engine
from pyfintracker.models import Transaction
from pyfintracker.reports import compute_balance, compute_monthly_report
from pyfintracker.repository import get_budget_spending, get_budgets, search_transactions

# ── helpers ──────────────────────────────────────────────────────────────────


def _fmt(value: Decimal, currency: str, /) -> str:
    """Per-currency precision: COP/JPY=0, USD/EUR/GBP=2. ROUND_HALF_UP."""
    decimals = 0 if currency in ("COP", "JPY") else 2
    quant = Decimal(10) ** -decimals if decimals else Decimal(1)
    sign = "" if value >= 0 else "-"
    q = value.quantize(quant, rounding=ROUND_HALF_UP)
    return f"{sign}{abs(q):,} {currency}"


class FocusableStatic(Static):
    """Static widget that can receive keyboard focus for vim-style navigation."""

    can_focus = True


# ── Dashboard screen ─────────────────────────────────────────────────────────


class DashboardScreen(Widget):
    """Master/detail dashboard: net-worth header, accounts, txns, summary, budgets.

    Reads from a real SQLite database (read-only).  The search bar at the top
    runs FTS5 queries; when empty the 10 most recent transactions are shown.
    Press Enter on any focused section to open the DrilldownScreen overlay.
    """

    CSS = """
    DashboardScreen {
        background: #1a1b26;
    }
    #search-box {
        margin: 0 1;
    }
    #net-worth-header {
        height: auto;
        margin-bottom: 1;
        padding: 0 1;
    }
    #left-pane {
        width: 60%;
        padding: 0 1;
    }
    #right-pane {
        width: 40%;
        padding: 0 1;
    }
    Static:focus {
        text-style: reverse;
    }
    """

    def __init__(self, db_path: str) -> None:
        super().__init__()
        self._db_path = db_path
        self._engine = make_engine(f"sqlite:///{db_path}")
        self._search_query: str = ""
        self._txn_ids: list[int] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Input(placeholder="Search transactions...  (type and press Enter)", id="search-box")
        yield FocusableStatic("", id="net-worth-header")
        with Horizontal():
            with Vertical(id="left-pane"):
                yield FocusableStatic("", id="accounts-section")
                yield FocusableStatic("", id="txns-section")
            with Vertical(id="right-pane"):
                yield FocusableStatic("", id="summary-section")
                yield FocusableStatic("", id="budgets-section")
        yield Footer()

    def on_mount(self) -> None:
        """Load data and populate widgets after mount."""
        self._refresh()

    # ── search ────────────────────────────────────────────────────────────

    @on(Input.Submitted, "#search-box")
    def _on_search(self, event: Input.Submitted) -> None:
        """Run FTS5 search and re-render the transaction list."""
        self._search_query = event.value
        self._refresh()

    # ── data loading ──────────────────────────────────────────────────────

    def _refresh(self) -> None:
        """Load all data from the DB and push it into each widget."""
        try:
            with self._engine.connect() as conn:
                data = self._load_data(conn)
            self._txn_ids = data.get("txn_ids", [])
            self._update_ui(data)
        except Exception as exc:
            self.query_one("#net-worth-header", FocusableStatic).update(
                f"[red]Error: {exc}[/red]"
            )

    def _load_data(self, conn: Connection) -> dict[str, Any]:
        """Load all dashboard data in one pass.  Returns a flat dict."""
        c = conn

        txn_ids: list[int] = []

        # ── net-worth trend (6 months) ────────────────────────────────────
        today = date.today()
        trend: list[tuple[str, Decimal]] = []
        for i in range(5, -1, -1):
            m = today.month - i
            y = today.year
            while m < 1:
                m += 12
                y -= 1
            last_day = calendar.monthrange(y, m)[1]
            as_of = date(y, m, last_day)
            nw = Decimal("0")
            try:
                report = compute_balance(c, as_of=as_of)
                nw = report.net_worth
            except Exception:
                # Historical-month failures fall back to 0 so the trend
                # chart still renders; details are not actionable here.
                pass
            trend.append((calendar.month_abbr[m], nw))

        current_nw = trend[-1][1] if trend else Decimal("0")

        # ── monthly summary ───────────────────────────────────────────────
        year_month = f"{today.year}-{today.month:02d}"
        monthly = None
        with suppress(Exception):
            monthly = compute_monthly_report(c, year_month)

        # ── accounts (grouped by kind) ────────────────────────────────────
        balance = None
        with suppress(Exception):
            balance = compute_balance(c)
        groups: dict[str, list[tuple[str, Decimal]]] = {}
        if balance is not None:
            for line in balance.lines:
                groups.setdefault(line.account_kind, []).append(
                    (line.account_name, line.balance)
                )

        # ── recent transactions / search results ──────────────────────────
        recent_rows: list[tuple[Transaction, Any]] = []
        try:
            if self._search_query:
                results = search_transactions(c, self._search_query, limit=10)
                for txn in results:
                    row = c.execute(
                        text(
                            "SELECT p.amount, p.currency, a.name "
                            "FROM postings p "
                            "JOIN accounts a ON a.id = p.account_id "
                            "WHERE p.transaction_id = :tid ORDER BY p.id LIMIT 1"
                        ),
                        {"tid": txn.id},
                    ).fetchone()
                    recent_rows.append((txn, dict(row._mapping) if row else None))
                    if txn.id is not None:
                        txn_ids.append(txn.id)
            else:
                rows = c.execute(
                    text(
                        "SELECT t.id, t.date, t.description, "
                        "       p.amount, p.currency, a.name "
                        "FROM transactions t "
                        "JOIN postings p "
                        "  ON p.transaction_id = t.id AND p.id = ("
                        "    SELECT MIN(p2.id) FROM postings p2"
                        "     WHERE p2.transaction_id = t.id"
                        "  ) "
                        "JOIN accounts a ON a.id = p.account_id "
                        "ORDER BY t.date DESC, t.id DESC LIMIT 10"
                    ),
                ).fetchall()
                for row in rows:
                    txn = Transaction(
                        id=row.id,
                        date=row.date,
                        description=row.description,
                    )
                    recent_rows.append((txn, row))
                    txn_ids.append(row.id)
        except Exception:
            # Recent-transactions lookup is a non-essential dashboard panel;
            # surface an empty list rather than crashing the whole screen.
            pass

        # ── budgets ───────────────────────────────────────────────────────
        budget_data: list[tuple[str, Decimal, Decimal]] = []
        try:
            budgets = get_budgets(c)
            for b in budgets:
                spent = get_budget_spending(c, b, today.isoformat())
                budget_data.append((b.name, b.amount, spent))
        except Exception:
            # Budgets are an optional dashboard panel; render nothing
            # rather than tearing down the rest of the dashboard.
            pass

        return {
            "trend": trend,
            "current_nw": current_nw,
            "monthly": monthly,
            "groups": groups,
            "recent": recent_rows,
            "budgets": budget_data,
            "year_month": year_month,
            "txn_ids": txn_ids,
        }

    # ── render helpers ────────────────────────────────────────────────────

    def _update_ui(self, data: dict[str, Any]) -> None:
        """Push rendered markup into every widget."""
        self.query_one("#net-worth-header", FocusableStatic).update(self._render_net_worth(data))
        self.query_one("#accounts-section", FocusableStatic).update(self._render_accounts(data))
        self.query_one("#txns-section", FocusableStatic).update(self._render_txns(data))
        self.query_one("#summary-section", FocusableStatic).update(self._render_summary(data))
        self.query_one("#budgets-section", FocusableStatic).update(self._render_budgets(data))

    @staticmethod
    def _render_net_worth(data: dict[str, Any]) -> str:
        trend = data.get("trend", [])
        current_nw = data.get("current_nw", Decimal("0"))
        if not trend:
            return "[bold]Net worth[/bold]\n  [dim]No data[/dim]"

        values = [v for _, v in trend]
        lo, hi = min(values), max(values) if values else Decimal("1")
        span = hi - lo or Decimal("1")
        bars: list[str] = []
        for label, v in trend:
            filled = int(
                (Decimal(20) * (v - lo) / span).to_integral_value(
                    rounding=ROUND_HALF_UP
                )
            )
            bar = "█" * filled + "░" * (20 - filled)
            color = "green" if v >= 0 else "red"
            bars.append(f"  {label:4} {bar}  [{color}]{_fmt(v, 'COP')}[/{color}]")
        c = "bold green" if current_nw >= 0 else "bold red"
        return (
            "[bold]Net worth (last 6 months)[/bold]\n"
            + "\n".join(bars)
            + f"\n\n[bold]Current: [{c}]{_fmt(current_nw, 'COP')}[/{c}][/bold]"
        )

    @staticmethod
    def _render_summary(data: dict[str, Any]) -> str:
        monthly = data.get("monthly")
        if monthly is None:
            return "[bold]Monthly Summary[/bold]\n  [dim]No data[/dim]"
        ccy = monthly.currency
        net_c = "green" if monthly.net >= 0 else "red"
        return (
            f"[bold]Monthly Summary — {monthly.year_month}[/bold]\n\n"
            f"  INCOME   [bold green]{_fmt(monthly.income_total, ccy):>16}[/bold green]\n"
            f"  EXPENSES [bold red]{_fmt(monthly.expense_total, ccy):>16}[/bold red]\n"
            f"  NET      [bold {net_c}]{_fmt(monthly.net, ccy):>16}[/bold {net_c}]\n"
        )

    @staticmethod
    def _render_accounts(data: dict[str, Any]) -> str:
        groups = data.get("groups", {})
        if not groups:
            return "[bold]Accounts[/bold]\n  [dim]No accounts[/dim]"
        parts: list[str] = ["[bold]Accounts[/bold]"]
        for kind in ("Assets", "Liabilities", "Equity", "Income", "Expenses"):
            items = groups.get(kind, [])
            if not items:
                continue
            parts.append(f"\n  [bold underline]{kind}[/bold underline]")
            for name, bal in items:
                color = "green" if bal >= 0 else "red"
                parts.append(
                    f"  {name:30} [{color}]{_fmt(bal, 'COP'):>16}[/{color}]"
                )
        return "\n".join(parts)

    @staticmethod
    def _render_txns(data: dict[str, Any]) -> str:
        recent = data.get("recent", [])
        if not recent:
            return "[bold]Transactions[/bold]\n  [dim]None found[/dim]"
        header = f"  {'Date':10}  {'Description':24}  {'Amount':>18}"
        sep = "  " + "─" * 56
        parts: list[str] = ["[bold]Transactions[/bold]", sep, header, sep]
        for txn, row in recent:
            if row is None:
                parts.append(
                    f"  {(txn.date or '')!s:10}  {txn.description:24}  [dim]N/A[/dim]"
                )
                continue
            amt = Decimal(str(row.amount))
            ccy = str(row.currency)
            formatted = f"{_fmt(amt, ccy):>18}"
            if amt > 0:
                colored = f"[green]{formatted}[/green]"
            elif amt < 0:
                colored = f"[red]{formatted}[/red]"
            else:
                colored = formatted
            parts.append(
                f"  {(txn.date or '')!s:10}  {txn.description:24}  {colored}"
            )
        parts.append(sep)
        return "\n".join(parts)

    @staticmethod
    def _render_budgets(data: dict[str, Any]) -> str:
        budgets = data.get("budgets", [])
        if not budgets:
            return "[bold]Budgets[/bold]\n  [dim]No budgets[/dim]"
        parts: list[str] = ["[bold]Budget Progress[/bold]"]
        for name, limit, spent in budgets:
            if limit <= Decimal("0"):
                continue
            pct = (spent / limit) * 100
            bar_len = 20
            filled = min(int(pct / 100 * bar_len), bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)
            if pct < 80:
                color = "green"
            elif pct < 100:
                color = "yellow"
            else:
                color = "red"
            parts.append(f"  {name:16} [{color}]{bar}[/{color}] {pct:.0f}%")
        return "\n".join(parts)

    # ── actions ───────────────────────────────────────────────────────────

    def action_focus_search(self) -> None:
        """Focus the search input bar."""
        sb = self.query_one("#search-box", Input)
        sb.focus()

    def action_drilldown(self) -> None:
        """Open the drilldown modal for the first transaction in view."""
        if self._txn_ids:
            self.app.push_screen(
                DrilldownScreen(self._db_path, self._txn_ids[0])
            )

    def go_top(self) -> None:
        """Move focus to the first focusable widget."""
        foc = self.query(Static).exclude("#search-box")
        if foc:
            foc.first().focus()

    def go_bottom(self) -> None:
        """Move focus to the last focusable widget."""
        foc = self.query(Static).exclude("#search-box")
        if foc:
            foc.last().focus()


# ── Drilldown modal screen ───────────────────────────────────────────────────


class DrilldownScreen(ModalScreen[None]):
    """Transaction detail overlay — shown when Enter is pressed on a txn."""

    CSS = """
    DrilldownScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #drilldown-box {
        width: 70;
        height: auto;
        padding: 1 2;
        background: #1a1b26;
        border: solid $primary;
    }
    """

    def __init__(self, db_path: str, txn_id: int | None = None) -> None:
        super().__init__()
        self._db_path = db_path
        self._txn_id = txn_id

    def compose(self) -> ComposeResult:
        if self._txn_id is None:
            yield Static(
                "[bold]Transaction Detail[/bold]\n\n[dim]No transaction selected.[/dim]",
                id="drilldown-box",
            )
            return

        engine = make_engine(f"sqlite:///{self._db_path}")
        with engine.connect() as conn:
            txn_row = conn.execute(
                text("SELECT * FROM transactions WHERE id = :id"),
                {"id": self._txn_id},
            ).fetchone()
            if txn_row is None:
                yield Static(
                    f"[red]Transaction #{self._txn_id} not found.[/red]",
                    id="drilldown-box",
                )
                return

            txn = Transaction.from_row(txn_row)
            postings = conn.execute(
                text(
                    "SELECT p.id, p.transaction_id, p.account_id, p.amount,"
                    "       p.currency, a.name AS account_name "
                    "FROM postings p "
                    "JOIN accounts a ON a.id = p.account_id "
                    "WHERE p.transaction_id = :tid ORDER BY p.id"
                ),
                {"tid": self._txn_id},
            ).fetchall()

            tags: list[str] = []
            try:
                from pyfintracker.repository import get_transaction_tags

                tag_objs = get_transaction_tags(conn, self._txn_id)
                tags = [t.name for t in tag_objs]
            except Exception:
                # Tags feature may be absent on older schemas; the modal
                # still renders the transaction details without them.
                pass

        yield Static(self._render_detail(txn, postings, tags), id="drilldown-box")

    @staticmethod
    def _render_detail(txn: Transaction, postings: Iterable[Any], tags: list[str]) -> str:
        lines: list[str] = [
            f"[bold]Transaction #{txn.id}[/bold]",
            f"  Date:        [cyan]{txn.date}[/cyan]",
            f"  Description: {txn.description}",
            "",
            "[bold]Postings:[/bold]",
            f"  {'Account':30} {'Amount':>16}",
            "  " + "─" * 48,
        ]
        for p in postings:
            amt = Decimal(str(p.amount))
            ccy = str(p.currency)
            acct = str(p.account_name)
            formatted = f"{_fmt(amt, ccy):>16}"
            if amt > 0:
                formatted = f"[green]{formatted}[/green]"
            elif amt < 0:
                formatted = f"[red]{formatted}[/red]"
            lines.append(f"  {acct:30} {formatted}")

        if tags:
            lines.append("")
            lines.append(f"[bold]Tags:[/bold] {', '.join(tags)}")

        lines.extend(["", "[dim]Press q or Esc to close[/dim]"])
        return "\n".join(lines)

    def key_q(self) -> None:
        """Close the drilldown modal."""
        self.dismiss()

    def key_escape(self) -> None:
        """Close the drilldown modal."""
        self.dismiss()
