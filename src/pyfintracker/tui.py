"""Wave 3 TUI spike — validates textual works in the project.

This is a throwaway spike. PR6 replaces it with the full finance browser.
- No imports from src/pyfintracker/ (models, repository, reports, CLI, etc.).
- Mock data only (same data as scripts/prototype_tui.py).
- All money as Decimal, never float.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static

# ── mock data (mirrors scripts/prototype_tui.py) ───────────────────────────

ACCOUNTS: tuple[tuple[str, str, Decimal], ...] = (
    ("Assets:Cash:COP",      "COP", Decimal("3850000")),
    ("Assets:Bank:USD",      "USD", Decimal("1245.50")),
    ("Assets:Bank:EUR",      "EUR", Decimal("320.00")),
    ("Liabilities:Card:COP", "COP", Decimal("-420000")),
    ("Equity:Opening:COP",   "COP", Decimal("-3000000")),
)

INCOME: Decimal = Decimal("4500000")
EXPENSES: Decimal = Decimal("1234567")
NET: Decimal = INCOME - EXPENSES
MONTHLY_CCY: str = "COP"

NET_WORTH_TREND: tuple[tuple[str, Decimal], ...] = (
    ("Feb", Decimal("2750000")),
    ("Mar", Decimal("2920000")),
    ("Apr", Decimal("3010000")),
    ("May", Decimal("3180000")),
    ("Jun", Decimal("3390000")),
    ("Jul", Decimal("3850000")),
)

RECENT_TXNS: tuple[tuple[date, str, Decimal, str], ...] = (
    (date(2026, 7, 18), "Salary July",           Decimal("4500000"),   "COP"),
    (date(2026, 7, 17), "Cafe latte",            Decimal("-12500"),    "COP"),
    (date(2026, 7, 16), "Groceries - Exito",     Decimal("-87000"),    "COP"),
    (date(2026, 7, 15), "Rent July",             Decimal("-1500000"),  "COP"),
    (date(2026, 7, 14), "Internet Claro",        Decimal("-89000"),    "COP"),
    (date(2026, 7, 12), "Freelance invoice #41", Decimal("320.00"),    "USD"),
    (date(2026, 7, 10), "Lunch - Crepes",        Decimal("-28000"),    "COP"),
    (date(2026, 7, 9),  "Transfer USD to COP",   Decimal("-100.00"),   "USD"),
    (date(2026, 7, 5),  "Utilities EPM",         Decimal("-145000"),   "COP"),
    (date(2026, 7, 2),  "Card payment",          Decimal("-420000"),   "COP"),
)


# ── helpers ────────────────────────────────────────────────────────────────

def fmt(value: Decimal, currency: str) -> str:
    """Per-currency precision: COP/JPY=0, USD/EUR/GBP=2. ROUND_HALF_UP."""
    decimals = 0 if currency in ("COP", "JPY") else 2
    quant = Decimal(10) ** -decimals if decimals else Decimal(1)
    return f"{value.quantize(quant, rounding=ROUND_HALF_UP):,} {currency}"


# ── renderers ──────────────────────────────────────────────────────────────

def _render_net_worth() -> str:
    """Text bar chart: 6-month net-worth trend."""
    values = [v for _, v in NET_WORTH_TREND]
    lo, hi = min(values), max(values)
    span = hi - lo or Decimal(1)
    bars: list[str] = []
    for label, v in NET_WORTH_TREND:
        filled = int(
            (Decimal(20) * (v - lo) / span).to_integral_value(rounding=ROUND_HALF_UP)
        )
        bar = "█" * filled + "░" * (20 - filled)
        bars.append(f"  {label:4} {bar}  {fmt(v, 'COP')}")
    return "[bold]Net worth (last 6 months)[/bold]\n" + "\n".join(bars)


def _render_accounts() -> str:
    """Mini accounts table: name, balance, currency."""
    header = f"  {'Account':28} {'Balance':>16} {'CCY':>4}"
    sep = "  " + "─" * 50
    rows: list[str] = [sep, header, sep]
    for name, ccy, bal in ACCOUNTS:
        rows.append(f"  {name:28} {fmt(bal, ccy):>16} {ccy:>4}")
    rows.append(sep)
    return "[bold]Accounts[/bold]\n" + "\n".join(rows)


def _render_txns() -> str:
    """Recent 10 transactions: date, description, right-aligned amount."""
    header = f"  {'Date':10}  {'Description':24}  {'Amount':>20}"
    sep = "  " + "─" * 60
    rows: list[str] = [sep, header, sep]
    for txn_date, desc, amt, ccy in RECENT_TXNS:
        formatted = f"{fmt(amt, ccy):>20}"
        if amt > 0:
            colored = f"[green]{formatted}[/green]"
        elif amt < 0:
            colored = f"[red]{formatted}[/red]"
        else:
            colored = formatted
        rows.append(f"  {txn_date.isoformat():10}  {desc:24}  {colored:>20}")
    rows.append(sep)
    return "[bold]Recent transactions[/bold]\n" + "\n".join(rows)


def _render_summary() -> str:
    """Monthly summary card: INCOME / EXPENSES / NET."""
    return (
        "[bold]Monthly summary[/bold]\n\n"
        f"  INCOME   [bold]{fmt(INCOME, MONTHLY_CCY)}[/bold]\n"
        f"  EXPENSES [bold]{fmt(EXPENSES, MONTHLY_CCY)}[/bold]\n"
        f"  NET      [bold]{fmt(NET, MONTHLY_CCY)}[/bold]\n"
    )


# ── CSS ────────────────────────────────────────────────────────────────────

CSS = """
Dashboard { height: 1fr; padding: 1 2; }
#header { height: auto; margin-bottom: 1; }
#left-pane { width: 60%; }
#right-pane { width: 40%; padding-left: 1; }
"""


# ── widgets ────────────────────────────────────────────────────────────────

class Dashboard(Vertical):
    """Master/detail dashboard: header + left (accounts/txns) + right (summary)."""

    def compose(self) -> ComposeResult:
        yield Static(_render_net_worth(), id="header")
        with Horizontal():
            with Vertical(id="left-pane"):
                yield Static(_render_accounts(), id="accounts")
                yield Static("", classes="spacer")
                yield Static(_render_txns(), id="txns")
            with Vertical(id="right-pane"):
                yield Static(_render_summary(), id="summary")


# ── app ────────────────────────────────────────────────────────────────────

class FinanceApp(App[None]):
    """TUI finance dashboard — Wave 3 spike. PR6 ships the full browser."""

    CSS = CSS
    TITLE = "pyfintracker"

    BINDINGS = [  # noqa: RUF012
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("h", "focus_previous", "Left", show=False),
        Binding("l", "focus_next", "Right", show=False),
        Binding("enter", "drilldown", "Drill down", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Dashboard()
        yield Footer()

    def action_drilldown(self) -> None:
        """Placeholder — full drilldown ships in PR6."""
