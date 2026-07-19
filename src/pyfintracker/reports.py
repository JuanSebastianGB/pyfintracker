"""Monthly and balance report logic."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import Connection, text

from pyfintracker.fx import get_rate

# Per-kind sign flip for the balance report.
# Liabilities and Equity carry "negative" balances in double-entry (you owe them /
# they offset Assets), but in a personal-finance balance view they show as
# positive (you owe that much).
SIGN_BY_KIND: dict[str, int] = {"Liabilities": -1, "Equity": -1}


class MonthlyLine(BaseModel):
    """A single line in a monthly report (one account on one day)."""

    model_config = ConfigDict(frozen=True)

    day: int
    label: str
    amount: Decimal
    balance: Decimal


class MonthlyReport(BaseModel):
    """Monthly income/expense report for a given year_month."""

    model_config = ConfigDict(frozen=True)

    year_month: str
    income_lines: list[MonthlyLine]
    expense_lines: list[MonthlyLine]
    income_total: Decimal
    expense_total: Decimal
    net: Decimal
    currency: str = "COP"


class BalanceLine(BaseModel):
    """A single line in a balance report (one account)."""

    model_config = ConfigDict(frozen=True)

    account_name: str
    account_kind: str
    balance: Decimal


class BalanceReport(BaseModel):
    """Balance report showing per-account balances and net worth."""

    model_config = ConfigDict(frozen=True)

    lines: list[BalanceLine]
    net_worth: Decimal
    currency: str = "COP"


def _to_lines(entries: list[dict[str, Any]]) -> list[MonthlyLine]:
    """Aggregate entries by (day, label) and compute a running balance.

    Entries with the same (day, label) key are summed. Output is sorted by
    (day, label) ascending; the balance field is the cumulative sum of
    amounts in that sorted order.
    """
    if not entries:
        return []

    aggregated: dict[tuple[int, str], Decimal] = {}
    for e in entries:
        key = (e["day"], e["label"])
        aggregated[key] = aggregated.get(key, Decimal("0")) + e["amount"]

    sorted_keys = sorted(aggregated, key=lambda k: (k[0], k[1]))
    running = Decimal("0")
    lines: list[MonthlyLine] = []
    for day, label in sorted_keys:
        running += aggregated[(day, label)]
        lines.append(
            MonthlyLine(
                day=day,
                label=label,
                amount=aggregated[(day, label)],
                balance=running,
            )
        )
    return lines


def _convert_amount(
    amount: Decimal,
    from_ccy: str,
    to_ccy: str,
    on: date,
    conn: Connection | None = None,
) -> Decimal:
    """Convert a single posting amount to target display currency.

    Same-currency is a fast-path (no I/O).  Otherwise delegates to fx.convert().
    """
    if from_ccy == to_ccy:
        return amount

    from pyfintracker.fx import convert as fx_convert

    return fx_convert(amount, from_ccy, to_ccy, on=on, _conn=conn)


def compute_monthly_report(
    conn: Connection,
    year_month: str,
    *,
    display_currency: str = "COP",
) -> MonthlyReport:
    """Compute a monthly income/expense report for the given ``year_month``.

    Args:
        conn: SQLAlchemy connection.
        year_month: ISO ``"YYYY-MM"`` format string.
        display_currency: Target currency for all amounts (default: COP).

    Returns:
        A ``MonthlyReport`` with income/expense lines, totals, and net.

    Raises:
        ValueError: if ``year_month`` is not in ``"YYYY-MM"`` format.
    """
    if (
        len(year_month) != 7
        or year_month[4] != "-"
        or not year_month[:4].isdigit()
        or not year_month[5:].isdigit()
    ):
        raise ValueError(f"Invalid year_month format: '{year_month}'. Expected YYYY-MM.")

    year = int(year_month[:4])
    month = int(year_month[5:])

    rows = conn.execute(
        text("""
            SELECT p.amount, p.currency, a.name, a.kind, t.date
            FROM postings p
            JOIN transactions t ON p.transaction_id = t.id
            JOIN accounts a ON p.account_id = a.id
            WHERE strftime('%Y', t.date) = :year
              AND strftime('%m', t.date) = :month
            ORDER BY t.date, a.name
        """),
        {"year": str(year), "month": f"{month:02d}"},
    ).fetchall()

    # Pre-fetch all distinct rate pairs if cross-currency (cache fill only)
    needs_conversion = any(row.currency != display_currency for row in rows)
    if needs_conversion:
        pairs: set[tuple[str, str, date]] = set()
        for row in rows:
            posting_ccy: str = row.currency
            if posting_ccy != display_currency:
                txn_date = date.fromisoformat(row.date)
                pairs.add((posting_ccy, display_currency, txn_date))
        for from_ccy, to_ccy, d in pairs:
            get_rate(from_ccy, to_ccy, on=d, _conn=conn)

    income_entries: list[dict[str, Any]] = []
    expense_entries: list[dict[str, Any]] = []

    for row in rows:
        kind: str = row.kind
        day: int = int(row.date.split("-")[2])
        amount_str: str = row.amount
        amount = Decimal(amount_str)
        label: str = row.name
        posting_ccy = row.currency

        # Convert to display currency if needed
        if posting_ccy != display_currency:
            txn_date = date.fromisoformat(row.date)
            amount = _convert_amount(amount, posting_ccy, display_currency, txn_date, conn=conn)

        if kind == "Income":
            # Income postings are credits (negative) — negate for positive income
            income_entries.append({"day": day, "label": label, "amount": -amount})
        elif kind == "Expenses":
            # Expense postings are debits (positive) — use as-is
            expense_entries.append({"day": day, "label": label, "amount": amount})

    income_lines = _to_lines(income_entries)
    expense_lines = _to_lines(expense_entries)

    income_total = sum((line.amount for line in income_lines), Decimal("0"))
    expense_total = sum((line.amount for line in expense_lines), Decimal("0"))

    return MonthlyReport(
        year_month=year_month,
        income_lines=income_lines,
        expense_lines=expense_lines,
        income_total=income_total,
        expense_total=expense_total,
        net=income_total - expense_total,
        currency=display_currency,
    )


def compute_balance(
    conn: Connection,
    *,
    display_currency: str = "COP",
    as_of: date | None = None,
) -> BalanceReport:
    """Compute per-account balances and net worth.

    Assets, Liabilities, and Equity accounts are included with positive sign
    convention (positive means you have it). Income and Expenses accounts are
    excluded (P&L, reset each period). Zero-balance accounts are omitted.

    When ``display_currency`` differs from a posting's native currency, the
    posting is converted at its transaction date (NOT the ``as_of`` date).

    Args:
        conn: SQLAlchemy connection.
        display_currency: Target currency for all amounts (default: COP).
        as_of: If provided, only considers postings on or before this date.

    Returns:
        A ``BalanceReport`` with per-account lines and net worth.
    """
    # ponytail: per-posting path handles both single-currency and cross-currency.
    # Single-path avoids dual SQL implementations that drift apart.
    sql = """
        SELECT a.name, a.kind, p.currency as posting_ccy, p.amount, t.date
        FROM postings p
        JOIN accounts a ON p.account_id = a.id
        JOIN transactions t ON p.transaction_id = t.id
        WHERE a.kind NOT IN ('Income', 'Expenses')
    """
    params: dict[str, str] = {}
    if as_of is not None:
        sql += " AND t.date <= :as_of"
        params["as_of"] = str(as_of)

    rows = conn.execute(text(sql), params).fetchall()

    # Pre-fetch rates if cross-currency (cache fill only)
    pairs: set[tuple[str, str, date]] = set()
    for row in rows:
        txn_date = date.fromisoformat(row.date)
        if row.posting_ccy != display_currency:
            pairs.add((row.posting_ccy, display_currency, txn_date))
    for from_ccy, to_ccy, d in pairs:
        get_rate(from_ccy, to_ccy, on=d, _conn=conn)

    # Aggregate per account with conversion + per-kind sign flip
    acct_balances: dict[str, dict[str, Any]] = {}
    for row in rows:
        name: str = row.name
        amount = Decimal(row.amount)
        txn_date = date.fromisoformat(row.date)
        posting_ccy: str = row.posting_ccy

        if posting_ccy != display_currency:
            amount = _convert_amount(amount, posting_ccy, display_currency, txn_date, conn=conn)

        if name not in acct_balances:
            acct_balances[name] = {"kind": row.kind, "balance": Decimal("0")}

        acct_balances[name]["balance"] += SIGN_BY_KIND.get(row.kind, 1) * amount

    lines = [
        BalanceLine(account_name=name, account_kind=data["kind"], balance=data["balance"])
        for name, data in acct_balances.items()
        if data["balance"] != Decimal("0")
    ]
    lines.sort(key=lambda ln: ln.account_name)

    net_worth = sum((line.balance for line in lines), Decimal("0"))
    return BalanceReport(lines=lines, net_worth=net_worth, currency=display_currency)


# ── Render functions ───────────────────────────────────────────────────────


def _fmt(amount: Decimal) -> str:
    """Format a Decimal amount with thousands separator."""
    # ponytail: simple string formatting, no locale
    s = f"{amount:,.2f}"
    if s.endswith(".00"):
        s = s[:-3]
    return s


def _style_amount(amount: Decimal, console: Console) -> str:
    """Return a Rich-markup string for an amount, green if positive else red."""
    color = "green" if amount >= 0 else "red"
    return f"[{color}]{_fmt(amount)}[/{color}]"


def render_monthly_report(report: MonthlyReport, console: Console) -> None:
    """Render a ``MonthlyReport`` as a Rich layout.

    Prints:
        - Title panel: "Monthly Report — YYYY-MM"
        - Income table (Day | Account | Amount | Balance)
        - Expenses table (Day | Account | Amount | Balance)
        - Net summary line

    Args:
        report: The monthly report to render.
        console: Rich console to print to.
    """
    # ── Title ───────────────────────────────────────────────────────────
    title = f"Monthly Report — {report.year_month}"
    if report.currency != "COP":
        title += f" ({report.currency})"
    console.print(Panel(title))

    # ── Helper to render one section ────────────────────────────────────
    def _render_section(title: str, lines: list[MonthlyLine], total: Decimal) -> None:
        if not lines:
            console.print(f"\n[bold]{title}[/bold] — [dim]No transactions[/dim]")
            return

        table = Table(title=title, title_style="bold")
        table.add_column("Day", style="dim", justify="right")
        table.add_column("Account", style="cyan")
        table.add_column("Amount", justify="right")
        table.add_column("Balance", justify="right")

        for line in lines:
            table.add_row(
                str(line.day),
                line.label,
                _style_amount(line.amount, console),
                _style_amount(line.balance, console),
            )

        # Footer: bold total
        table.add_row(
            "",
            "[bold]Total[/bold]",
            _style_amount(total, console),
            "",  # last col empty
        )
        table.columns[2].footer = _fmt(total)
        console.print(table)

    _render_section("Income", report.income_lines, report.income_total)
    _render_section("Expenses", report.expense_lines, report.expense_total)

    # ── Net summary ─────────────────────────────────────────────────────
    net_color = "green" if report.net >= 0 else "red"
    ccy_tag = f" {report.currency}" if report.currency != "COP" else ""
    console.print(f"\n[bold]Net: [{net_color}]{_fmt(report.net)}[/{net_color}]{ccy_tag}[/bold]")


def render_balance(report: BalanceReport, console: Console) -> None:
    """Render a ``BalanceReport`` as a grouped Rich table.

    Groups lines by ``account_kind`` (Assets, Liabilities, Equity), prints
    a sub-table per group, then a bold net-worth footer.

    Args:
        report: The balance report to render.
        console: Rich console to print to.
    """
    # ── Title ───────────────────────────────────────────────────────────
    console.print(Panel("[bold]Balance Report[/bold]"))

    # Group lines by account_kind
    groups: dict[str, list[BalanceLine]] = {}
    for line in report.lines:
        groups.setdefault(line.account_kind, []).append(line)

    sorted_kinds = sorted(groups.keys())

    for kind in sorted_kinds:
        lines = groups[kind]
        table = Table(title=kind, title_style="bold")
        table.add_column("Account", style="cyan")
        table.add_column("Balance", justify="right")

        for line in lines:
            table.add_row(line.account_name, _style_amount(line.balance, console))

        console.print(table)

    # ── Net worth footer ────────────────────────────────────────────────
    nw_color = "green" if report.net_worth >= 0 else "red"
    ccy_tag = f" {report.currency}" if report.currency != "COP" else ""
    console.print(f"[bold]Net worth: [{nw_color}]{_fmt(report.net_worth)}[/{nw_color}]{ccy_tag}[/bold]")


__all__ = [
    "BalanceLine",
    "BalanceReport",
    "MonthlyLine",
    "MonthlyReport",
    "compute_balance",
    "compute_monthly_report",
    "render_balance",
    "render_monthly_report",
]
