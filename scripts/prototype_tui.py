# PROTOTYPE — throwaway. Wave 3 F3 TUI dashboard variant spiking.
# Delete after the design review. Not part of the shipped package.
# - No imports from src/pyfintracker/.
# - No DB. No tests. No persistence. Mock Decimal data only.
# - textual is installed in the venv; this prototype IS the PR1 spike validation.
# - Run: uv run python scripts/prototype_tui.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from time import monotonic

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Footer, Header, Static

D = Decimal


# --- mock data -------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Account:
    name: str
    currency: str
    balance: Decimal  # per-currency, no float


@dataclass(frozen=True, slots=True)
class Txn:
    txn_date: date
    description: str
    amount: Decimal
    currency: str


ACCOUNTS: tuple[Account, ...] = (
    Account("Assets:Cash:COP",      "COP", D("3850000")),
    Account("Assets:Bank:USD",      "USD", D("1245.50")),
    Account("Assets:Bank:EUR",      "EUR", D("320.00")),
    Account("Liabilities:Card:COP", "COP", D("-420000")),
    Account("Equity:Opening:COP",  "COP", D("-3000000")),
)


INCOME   = D("4500000")
EXPENSES = D("1234567")
NET      = INCOME - EXPENSES
MONTHLY_CCY = "COP"

NET_WORTH_TREND: tuple[tuple[str, Decimal], ...] = (
    ("Feb", D("2750000")),
    ("Mar", D("2920000")),
    ("Apr", D("3010000")),
    ("May", D("3180000")),
    ("Jun", D("3390000")),
    ("Jul", D("3850000")),
)


RECENT_TXNS: tuple[Txn, ...] = (
    Txn(date(2026, 7, 18), "Salary July",           D("4500000"),   "COP"),
    Txn(date(2026, 7, 17), "Cafe latte",            D("-12500"),    "COP"),
    Txn(date(2026, 7, 16), "Groceries - Exito",     D("-87000"),    "COP"),
    Txn(date(2026, 7, 15), "Rent July",             D("-1500000"),  "COP"),
    Txn(date(2026, 7, 14), "Internet Claro",        D("-89000"),    "COP"),
    Txn(date(2026, 7, 12), "Freelance invoice #41", D("320.00"),    "USD"),
    Txn(date(2026, 7, 10), "Lunch - Crepes",        D("-28000"),    "COP"),
    Txn(date(2026, 7, 9),  "Transfer USD to COP",   D("-100.00"),   "USD"),
    Txn(date(2026, 7, 5),  "Utilities EPM",         D("-145000"),   "COP"),
    Txn(date(2026, 7, 2),  "Card payment",          D("-420000"),   "COP"),
)


def fmt(amount: Decimal, currency: str) -> str:
    """Per-currency precision: COP/JPY=0, USD/EUR/GBP=2. Decimal only, no float."""
    decimals = 0 if currency in ("COP", "JPY") else 2
    quant = Decimal(10) ** -decimals if decimals else Decimal(1)
    return f"{amount.quantize(quant):,} {currency}"


def net_worth_bar(trend: tuple[tuple[str, Decimal], ...], width: int = 32) -> str:
    """Tiny text-histogram for net worth. Linear mapping; fine for 6 bars."""
    if not trend:
        return ""
    values = [v for _, v in trend]
    lo, hi = min(values), max(values)
    span = hi - lo or D(1)
    lines = []
    for label, v in trend:
        # ponytail: O(n) over a fixed 6; the canvas width is the actual ceiling.
        filled = int((D(width) * (v - lo) / span).to_integral_value())
        bar = "#" * filled + "." * (width - filled)
        lines.append(f"{label} {bar} {fmt(v, 'COP')}")
    return "\n".join(lines)


# --- variant label set (also drives the footer) -----------------------------

VARIANT_LABELS = {
    "a": "A - Master/detail",
    "b": "B - Single scrollable dashboard",
    "c": "C - Modal-first / vim-style",
}


# --- variants --------------------------------------------------------------

class VariantAMasterDetail(Container):
    """Sidebar (accounts + recent txns) / right pane (monthly + selected txn)."""

    BINDINGS = [  # noqa: RUF012 (Textual convention: class-level BINDINGS)
        Binding("tab", "focus_next", "Next panel", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal(id="a-grid"):
            with Vertical(id="a-left", classes="panel"):
                yield Static("[b]Accounts[/b]", classes="panel-title")
                yield Static(_render_accounts_brief(), id="a-accounts")
                yield Static("\n[b]Recent transactions[/b]", classes="panel-title")
                yield Static(_render_txns_brief(), id="a-txns")
            with Vertical(id="a-right", classes="panel"):
                yield Static("[b]Monthly summary[/b]", classes="panel-title")
                yield Static(_render_monthly_card(), id="a-monthly")
                yield Static("\n[b]Selected transaction[/b]", classes="panel-title")
                yield Static(_render_selected_txn(RECENT_TXNS[1]), id="a-selected")


class VariantBScroll(Container):
    """Everything visible, top to bottom. Scrollable. Glance = full picture."""

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="b-scroll"):
            yield Static("[b]Net worth (last 6 months)[/b]", classes="panel-title")
            yield Static(net_worth_bar(NET_WORTH_TREND), id="b-bar")
            yield Static(_render_monthly_card(big=True), id="b-monthly")
            yield Static("[b]Accounts[/b]", classes="panel-title")
            yield Static(_render_accounts_table(), id="b-accounts")
            yield Static("[b]Recent transactions[/b]", classes="panel-title")
            yield Static(_render_txns_table(), id="b-txns")


class VariantCVimModes(Container):
    """One focused view at a time; mode shown in the status line."""

    current_mode: reactive[str] = reactive("Dashboard")

    def compose(self) -> ComposeResult:
        yield Static(self._mode_line(), id="c-mode")
        yield Container(id="c-body")

    def on_mount(self) -> None:
        self._render_mode()

    def _mode_line(self) -> str:
        return (
            f"[reverse] MODE: {self.current_mode} [/reverse]   "
            f"(gd dashboard | ga accounts | gt txns | gs search)"
        )

    def _render_mode(self) -> None:
        body = self.query_one("#c-body", Container)
        body.remove_children()
        rendered = {
            "Dashboard":    _render_dashboard_single,
            "Accounts":     _render_accounts_table,
            "Transactions": _render_txns_table,
            "Search":       _render_search_placeholder,
        }[self.current_mode]()
        body.mount(Static(rendered, id=f"c-{self.current_mode.lower()}"))
        self.query_one("#c-mode", Static).update(self._mode_line())

    def set_mode(self, name: str) -> None:
        self.current_mode = name

    def watch_current_mode(self, _: str) -> None:
        if self.is_mounted:
            self._render_mode()


# --- renderers (shared strings) -------------------------------------------

def _render_accounts_brief() -> str:
    return "\n".join(f" {a.name:28} {fmt(a.balance, a.currency)}" for a in ACCOUNTS)


def _render_txns_brief() -> str:
    rows = []
    for t in RECENT_TXNS[:6]:
        sign = "+" if t.amount >= 0 else ""
        rows.append(f" {t.txn_date}  {t.description:24} {sign}{fmt(t.amount, t.currency)}")
    return "\n".join(rows)


def _render_accounts_table() -> str:
    header = f" {'Name':28} {'Balance':>16} {'CCY':>4}"
    sep = " " + "-" * 52
    rows = [header, sep] + [
        f" {a.name:28} {a.balance:>16} {a.currency:>4}" for a in ACCOUNTS
    ]
    return "\n".join(rows)


def _render_txns_table() -> str:
    header = f" {'Date':10}  {'Description':24}  {'Amount':>20}"
    sep = " " + "-" * 60
    rows = [header, sep]
    for t in RECENT_TXNS:
        sign = "+" if t.amount >= 0 else ""
        rows.append(
            f" {t.txn_date.isoformat():10}  {t.description:24}  "
            f"{sign}{fmt(t.amount, t.currency):>20}"
        )
    return "\n".join(rows)


def _render_monthly_card(*, big: bool = False) -> str:
    def row(label: str, amount: Decimal) -> str:
        if big:
            return f" {label:10} [b reverse]{fmt(amount, MONTHLY_CCY)}[/b reverse]"
        return f" {label:10} [b]{fmt(amount, MONTHLY_CCY)}[/b]"
    return (
        f"\n{row('INCOME',   INCOME)}\n"
        f"{row('EXPENSES', EXPENSES)}\n"
        f"{row('NET',      NET)}\n"
    )


def _render_selected_txn(t: Txn) -> str:
    return (
        f" Date:        {t.txn_date.isoformat()}\n"
        f" Description: {t.description}\n"
        f" Amount:      {fmt(t.amount, t.currency)}\n"
    )


def _render_dashboard_single() -> str:
    return (
        "\n[b]Net worth (last 6 months)[/b]\n"
        + net_worth_bar(NET_WORTH_TREND)
        + "\n\n[b]Monthly summary[/b]\n"
        + _render_monthly_card(big=True)
        + "\n[b]Recent transactions[/b]\n"
        + _render_txns_brief()
    )


def _render_search_placeholder() -> str:
    return (
        "\n[dim]Search screen would render FTS5 hits from PR3 here.[/dim]\n"
        "\nFor this prototype: press 'g d' to return to the dashboard view.\n"
    )


# --- app -------------------------------------------------------------------

VARIANT_REGISTRY = {
    "a": VariantAMasterDetail,
    "b": VariantBScroll,
    "c": VariantCVimModes,
}


class PrototypeApp(App[None]):
    CSS = """
    Screen { layout: vertical; }
    #main { height: 1fr; padding: 1 2; }
    .panel { border: round $accent; padding: 1 2; height: 100%; }
    .panel-title { text-style: bold; padding-bottom: 1; }
    Header { dock: top; }
    Footer { dock: bottom; }

    /* A: split master/detail */
    #a-grid { height: 100%; }
    #a-left, #a-right { width: 1fr; padding: 0 1; }

    /* B: single column scroll */
    #b-scroll { height: 100%; }

    /* C: status line + body */
    #c-mode { dock: top; height: 1; padding: 0 1; }
    #c-body { padding: 1 2; height: auto; }
    """

    G_PREFIX_TIMEOUT = 1.0
    _g_prefix_armed: reactive[float | None] = reactive(None)

    BINDINGS = [  # noqa: RUF012 (Textual convention: class-level BINDINGS)
        Binding("1",  "switch_a",      "Variant A"),
        Binding("2",  "switch_b",      "Variant B"),
        Binding("3",  "switch_c",      "Variant C"),
        Binding("q",  "quit",          "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.title = "pyfintracker dashboard prototype"
        self.sub_title = f"{VARIANT_LABELS['a']}  |  Press 1/2/3 to switch"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Container(id="main"):
            yield VariantAMasterDetail()
        yield Footer()

    async def on_key(self, event: events.Key) -> None:
        key = event.key
        armed = self._g_prefix_armed
        if armed is not None and monotonic() - armed > self.G_PREFIX_TIMEOUT:
            self._g_prefix_armed = None
            armed = None

        if armed is not None:
            if key in {"shift", "ctrl", "alt", "meta", "super"}:
                return
            self._g_prefix_armed = None
            action = {
                "d": "vim_dashboard",
                "a": "vim_accounts",
                "t": "vim_txns",
                "s": "vim_search",
            }.get(key)
            if action is not None:
                await self.run_action(action)
                event.prevent_default()
                event.stop()
            return

        if key == "g" and self._c_widget() is not None:
            self._g_prefix_armed = monotonic()
            event.prevent_default()
            event.stop()

    def _mount_variant(self, key: str) -> None:
        if key not in VARIANT_REGISTRY:
            return
        main = self.query_one("#main", Container)
        # ponytail: drop every previous variant widget, mount the new one. No id collisions.
        for child in list(main.children):
            child.remove()
        main.mount(VARIANT_REGISTRY[key]())
        self.sub_title = f"{VARIANT_LABELS[key]}  |  Press 1/2/3 to switch"

    def action_switch_a(self) -> None:
        self._mount_variant("a")

    def action_switch_b(self) -> None:
        self._mount_variant("b")

    def action_switch_c(self) -> None:
        self._mount_variant("c")

    # ponytail: vim-mode keys live on the App so they fire regardless of focus,
    # but each action is a no-op unless variant C is the rendered widget.
    def _c_widget(self) -> VariantCVimModes | None:
        try:
            return self.query_one(VariantCVimModes)
        except Exception:
            return None

    def action_vim_dashboard(self) -> None:
        w = self._c_widget()
        if w is not None:
            w.set_mode("Dashboard")

    def action_vim_accounts(self) -> None:
        w = self._c_widget()
        if w is not None:
            w.set_mode("Accounts")

    def action_vim_txns(self) -> None:
        w = self._c_widget()
        if w is not None:
            w.set_mode("Transactions")

    def action_vim_search(self) -> None:
        w = self._c_widget()
        if w is not None:
            w.set_mode("Search")


if __name__ == "__main__":
    PrototypeApp().run()
