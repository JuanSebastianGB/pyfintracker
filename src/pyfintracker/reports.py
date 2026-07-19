"""Monthly and balance report logic."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import Connection, text


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


def compute_monthly_report(
    conn: Connection, year_month: str
) -> MonthlyReport:
    """Compute a monthly income/expense report for the given ``year_month``.

    Args:
        conn: SQLAlchemy connection.
        year_month: ISO ``"YYYY-MM"`` format string.

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
        raise ValueError(
            f"Invalid year_month format: '{year_month}'. Expected YYYY-MM."
        )

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

    income_entries: list[dict[str, Any]] = []
    expense_entries: list[dict[str, Any]] = []

    for row in rows:
        kind: str = row.kind
        day: int = int(row.date.split("-")[2])
        amount_str: str = row.amount
        amount = Decimal(amount_str)
        label: str = row.name

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
    )


def compute_balance(conn: Connection) -> BalanceReport:
    """Compute per-account balances and net worth.

    Assets, Liabilities, and Equity accounts are included with positive sign
    convention (positive means you have it). Income and Expenses accounts are
    excluded (P&L, reset each period). Zero-balance accounts are omitted.

    Args:
        conn: SQLAlchemy connection.

    Returns:
        A ``BalanceReport`` with per-account lines and net worth.
    """
    rows = conn.execute(
        text("""
            SELECT a.id, a.name, a.kind, COALESCE(SUM(p.amount), '0') as balance
            FROM accounts a
            LEFT JOIN postings p ON a.id = p.account_id
            GROUP BY a.id
            ORDER BY a.name
        """),
    ).fetchall()

    lines: list[BalanceLine] = []
    for row in rows:
        if row.kind in ("Income", "Expenses"):
            continue  # P&L accounts excluded from balance

        balance = Decimal(row.balance) if row.balance else Decimal("0")

        # Liability and Equity accounts have credit balances (negative postings)
        # Negate to show positive (positive = you have it)
        if row.kind in ("Liabilities", "Equity"):
            balance = -balance

        if balance == Decimal("0"):
            continue  # skip zero-balance accounts

        lines.append(
            BalanceLine(
                account_name=row.name,
                account_kind=row.kind,
                balance=balance,
            )
        )

    net_worth = sum((line.balance for line in lines), Decimal("0"))

    return BalanceReport(lines=lines, net_worth=net_worth)


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
    console.print(Panel(f"Monthly Report — {report.year_month}"))

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
            "", "[bold]Total[/bold]", _style_amount(total, console), "",  # last col empty
        )
        table.columns[2].footer = _fmt(total)
        console.print(table)

    _render_section("Income", report.income_lines, report.income_total)
    _render_section("Expenses", report.expense_lines, report.expense_total)

    # ── Net summary ─────────────────────────────────────────────────────
    net_color = "green" if report.net >= 0 else "red"
    console.print(f"\n[bold]Net: [{net_color}]{_fmt(report.net)}[/{net_color}][/bold]")


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
    console.print(f"[bold]Net worth: [{nw_color}]{_fmt(report.net_worth)}[/{nw_color}][/bold]")


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
