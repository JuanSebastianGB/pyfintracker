"""Typer CLI application for pyfintracker."""

from __future__ import annotations

import sys
from collections.abc import Callable
from decimal import Decimal
from importlib.metadata import version as pkg_version
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from pyfintracker.models import Posting, Transaction

from rich.console import Console
from rich.table import Table
from sqlalchemy import Engine

from pyfintracker.config import load_settings, source_of
from pyfintracker.db import make_engine
from pyfintracker.exceptions import ReplRequiresTTYError

__version__ = pkg_version("pyfintracker")

app = typer.Typer(
    name="fin",
    help="Personal finance CLI with double-entry bookkeeping.",
    pretty_exceptions_show_locals=False,
)


@app.callback(invoke_without_command=True)
def _main(ctx: typer.Context) -> None:
    """pyfintracker CLI — manage your personal finances."""
    # If no subcommand is given, show help
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


# ── Account sub-app ──────────────────────────────────────────────────────────


account_app = typer.Typer(help="Manage accounts.")
app.add_typer(account_app, name="account")

# ── Report sub-app ───────────────────────────────────────────────────────────


report_app = typer.Typer(help="Financial reports.")
app.add_typer(report_app, name="report")


def _get_engine() -> Engine:
    """Create a SQLAlchemy engine from the configured db_path."""
    settings = load_settings()
    return make_engine(f"sqlite:///{settings.db_path}")


@app.command()
def version() -> None:
    """Show the installed version."""
    typer.echo(f"pyfintracker v{__version__}")


@app.command()
def init(
    force: bool = typer.Option(False, "--force", help="Recreate existing database (DESTRUCTIVE)"),
) -> None:
    """Initialize the database and seed starter accounts."""
    settings = load_settings()
    db_path = settings.db_path

    if db_path.exists() and not force:
        typer.echo(f"fin already initialized at {db_path}. Use --force to recreate.")
        raise typer.Exit(code=0)

    if force and db_path.exists():
        db_path.unlink()
        # Clean up WAL and SHM files from a previous WAL-mode DB
        for ext in ("-wal", "-shm"):
            p = db_path.with_name(db_path.name + ext)
            if p.exists():
                p.unlink()

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Run migrations via Alembic
    engine = make_engine(f"sqlite:///{db_path}")
    _run_alembic(engine, "up", "head")

    typer.echo(f"fin initialized at {db_path}")


@app.command()
def migrate(
    action: str = typer.Argument(..., help="Action: up, down, or status"),
    revision: str = typer.Argument("head", help="Target revision (default: head)"),
) -> None:
    """Run Alembic migrations (up, down, or status)."""
    settings = load_settings()
    db_path = settings.db_path
    engine = make_engine(f"sqlite:///{db_path}")

    if action == "up":
        _run_alembic(engine, "up", revision)
        typer.echo(f"Migrated to {revision}")
    elif action == "down":
        _run_alembic(engine, "down", revision)
        typer.echo(f"Downgraded to {revision}")
    elif action == "status":
        _run_alembic(engine, "status", revision)
    else:
        typer.echo(f"Unknown action: {action}. Use up, down, or status.", err=True)
        raise typer.Exit(code=1)


@app.command()
def config_show() -> None:
    """Show effective configuration with source for each field."""
    settings = load_settings()

    data = {}
    for field in [
        "db_path",
        "default_currency",
        "account_name_max_length",
        "description_max_length",
        "snapshot_width",
        "journal_mode",
    ]:
        value = getattr(settings, field)
        source = source_of(field)
        data[field] = (str(value), source)

    # Determine column widths
    max_field = max(len(f) for f in data)
    max_val = max(len(v[0]) for v in data.values())
    max_src = max(len(v[1]) for v in data.values())

    typer.echo("Configuration")
    typer.echo("=" * (max_field + max_val + max_src + 6))
    for field, (value, source) in data.items():
        typer.echo(f"{field.ljust(max_field)}  {value.ljust(max_val)}  [{source}]")


@account_app.command("new")
def account_new(
    name: str = typer.Argument(..., help="Account name (e.g. Assets:Cash)"),
    currency: str = typer.Option("COP", "--currency", "-c", help="Currency ISO code"),
    description: str = typer.Option("", help="Optional description"),
    initial: str | None = typer.Option(None, "--initial", help="Opening balance"),
) -> None:
    """Create a new account."""
    from datetime import date

    from pyfintracker.exceptions import FinanceError
    from pyfintracker.models import Account, Posting, Transaction
    from pyfintracker.repository import (
        create_account,
        create_transaction_with_postings,
        get_account_by_name,
        upsert_account,
    )
    from pyfintracker.validation import (
        validate_account_name,
        validate_amount,
        validate_currency,
        validate_description,
    )

    try:
        canonical = validate_account_name(name)
        validated_currency = validate_currency(currency)
        if description:
            validate_description(description)
    except FinanceError as e:
        typer.echo(str(e))
        raise typer.Exit(code=1) from None

    # Derive kind and depth from the colon-separated name
    parts = canonical.split(":")
    kind = parts[0]
    depth = len(parts) - 1

    engine = _get_engine()
    try:
        with engine.begin() as conn:
            account = create_account(
                conn,
                Account(name=canonical, currency=validated_currency, depth=depth, kind=kind),
            )

            if initial is not None:
                validated_amount = validate_amount(initial, validated_currency)

                assert account.id is not None  # freshly created

                equity = get_account_by_name(conn, "Equity:OpeningBalances")
                if equity is None:
                    equity = upsert_account(
                        conn, name="Equity:OpeningBalances",
                        currency=validated_currency,
                    )
                assert equity.id is not None

                txn = Transaction(
                    date=date.today(),
                    description=f"Opening balance for {canonical}",
                    currency=validated_currency,
                )
                postings = [
                    Posting(account_id=account.id, amount=validated_amount, currency=validated_currency),
                    Posting(account_id=equity.id, amount=-validated_amount, currency=validated_currency),
                ]
                create_transaction_with_postings(conn, txn, postings)

                console = Console()
                console.print(f"[green]✓[/green] '{canonical}' created with opening balance {validated_amount} {validated_currency}")
                return

            console = Console()
            console.print(f"[green]✓[/green] Account '{canonical}' created ({validated_currency})")

    except (FinanceError, ValueError) as e:
        console = Console()
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None


@account_app.command("list")
def account_list() -> None:
    """List all accounts."""
    from pyfintracker.repository import list_accounts

    engine = _get_engine()
    with engine.begin() as conn:
        accounts = list_accounts(conn)

    console = Console()
    table = Table(title="Accounts")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="yellow")
    table.add_column("Currency", style="green")
    table.add_column("Depth")

    for acc in accounts:
        table.add_row(
            str(acc.id or ""),
            acc.name,
            acc.kind,
            acc.currency,
            str(acc.depth),
        )

    console.print(table)


@app.command()
def add(
    from_account: str | None = typer.Option(None, "--from", help="Source account"),
    to_account: str | None = typer.Option(None, "--to", help="Destination account"),
    amount: str | None = typer.Option(None, "--amount", help="Amount to transfer"),
    currency: str = typer.Option("COP", "--currency", help="Currency"),
    description: str | None = typer.Option(None, "--description", help="Transaction description"),
) -> None:
    """Add a transaction. Use flags for direct entry, or omit flags for REPL."""
    from datetime import date

    from pyfintracker.exceptions import AccountNotFoundError, FinanceError
    from pyfintracker.models import Posting, Transaction
    from pyfintracker.repository import (
        create_transaction_with_postings,
        get_account_by_name,
        list_accounts,
    )
    from pyfintracker.validation import (
        validate_account_name,
        validate_amount,
        validate_currency,
        validate_description,
    )

    # Detect REPL vs flag mode
    flag_args = [from_account, to_account, amount, description]
    flag_mode = any(a is not None for a in flag_args)

    if not flag_mode:
        # ── REPL mode ───────────────────────────────────────
        # TTY check is inside repl_add_postings — no need to duplicate here.
        console = Console()
        engine = _get_engine()

        try:
            with engine.begin() as conn:
                accounts = list_accounts(conn)
                account_names = [a.name for a in accounts]

                def _resolve(name: str) -> int:
                    acct = get_account_by_name(conn, name)
                    if acct is None:
                        raise AccountNotFoundError(f"Account '{name}' not found")
                    assert acct.id is not None
                    return acct.id

                txn, postings = repl_add_postings(
                    console, _stdin_prompt, _resolve, account_names,
                )
                txn_id = create_transaction_with_postings(conn, txn, postings)

            console.print(f"[green]✓[/green] Transaction #{txn_id}: {txn.description}")
        except FinanceError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=getattr(e, 'code', 1)) from None

        return

    # ── Flag mode — partial flags check ─────────────────────
    if not all(a is not None for a in flag_args):
        Console().print(
            "[red]Error:[/red] Use all flags (--from, --to, --amount, --description) "
            "or none (for REPL mode)."
        )
        raise typer.Exit(code=2)

    # Narrow types after the all-not-None guard (mypy can't do this)
    assert from_account is not None
    assert to_account is not None
    assert amount is not None
    assert description is not None

    try:
        validated_amount = validate_amount(amount, currency)
        from_name = validate_account_name(from_account)
        to_name = validate_account_name(to_account)
        validated_currency = validate_currency(currency)
        validate_description(description)
    except FinanceError as e:
        typer.echo(str(e))
        raise typer.Exit(code=1) from None

    engine = _get_engine()
    try:
        with engine.begin() as conn:
            src = get_account_by_name(conn, from_name)
            if src is None:
                console = Console()
                console.print(f"[red]Error:[/red] Account '{from_name}' not found")
                raise typer.Exit(code=1)
            assert src.id is not None
            dst = get_account_by_name(conn, to_name)
            if dst is None:
                console = Console()
                console.print(f"[red]Error:[/red] Account '{to_name}' not found")
                raise typer.Exit(code=1)
            assert dst.id is not None

            txn = Transaction(
                date=date.today(), description=description, currency=validated_currency,
            )
            postings = [
                Posting(account_id=src.id, amount=-validated_amount, currency=validated_currency),
                Posting(account_id=dst.id, amount=validated_amount, currency=validated_currency),
            ]

            txn_id = create_transaction_with_postings(conn, txn, postings)

        console = Console()
        console.print(f"[green]✓[/green] Transaction #{txn_id}: {description} ({validated_amount} {validated_currency})")

    except (FinanceError, ValueError) as e:
        console = Console()
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=getattr(e, 'code', 1)) from None


# ── Report sub-app commands ──────────────────────────────────────────────────


@report_app.command("month")
def report_month(
    month: str = typer.Option("", "--month", help="Month in YYYY-MM format (default: current)"),
) -> None:
    """Show income/expense report for a month."""
    import re
    from datetime import date

    from rich.console import Console

    from pyfintracker.reports import compute_monthly_report, render_monthly_report

    year_month = month
    if not year_month:
        today = date.today()
        year_month = f"{today.year}-{today.month:02d}"
    elif not re.match(r"^\d{4}-\d{2}$", year_month):
        console = Console()
        console.print(f"[red]Error:[/red] Invalid month format '{year_month}'. Expected YYYY-MM.")
        raise typer.Exit(code=1)

    engine = _get_engine()
    console = Console()
    with engine.begin() as conn:
        report = compute_monthly_report(conn, year_month)
    render_monthly_report(report, console)


@report_app.command("balance")
def balance(
    account_name: str = typer.Argument(None, help="Filter by account name (optional)"),
) -> None:
    """Show account balances and net worth."""
    from rich.console import Console

    from pyfintracker.reports import compute_balance, render_balance

    engine = _get_engine()
    console = Console()
    with engine.begin() as conn:
        report = compute_balance(conn)

    if account_name:
        lower = account_name.lower()
        filtered_lines = [ln for ln in report.lines if lower in ln.account_name.lower()]
        report = report.__class__(
            lines=filtered_lines,
            net_worth=sum((ln.balance for ln in filtered_lines), Decimal("0")),
        )

    render_balance(report, console)


def _parse_repl_amount(raw: str) -> Decimal:
    """Parse REPL amount input: strip commas, reject zero and non-numeric."""
    import re
    from decimal import InvalidOperation

    from pyfintracker.exceptions import InvalidAmount

    cleaned = re.sub(r"[,\s]", "", raw.strip())
    if not cleaned:
        raise InvalidAmount("Amount is empty")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        raise InvalidAmount(f"Invalid amount: '{raw}'") from None
    if amount == Decimal("0"):
        raise InvalidAmount("Amount cannot be zero")
    return amount


def _show_diff(balance: Decimal, currency: str) -> str:
    """Return a formatted guidance line showing the current imbalance."""
    return f"Balance: {balance:+} {currency} (need {-balance:+} to balance)"


def _suggest_accounts(name: str, available: list[str]) -> list[str]:
    """Find closest matching account names (case-insensitive substring match)."""
    lower = name.lower()
    return [a for a in available if lower in a.lower()][:5]


def repl_add_postings(
    console: Console,
    prompt_fn: Callable[..., str],
    resolve_account: Callable[[str], int] | None = None,
    available_accounts: list[str] | None = None,
) -> tuple[Transaction, list[Posting]]:
    """Interactive REPL for transaction entry.

    Args:
        console: Rich Console for output.
        prompt_fn: Callable accepting (prompt_text, default="") and returning
            user input.  In production wraps questionary / input(); in tests
            returns scripted replies.
        resolve_account: Optional callback to resolve account names to IDs.
            When None, account_id is set to 0 (for tests).
        available_accounts: Optional list of valid account names for suggestions.

    Returns:
        Tuple of (Transaction, List[Posting]) ready to save.
        When resolve_account is provided, Posting.account_id is the real ID.
    """
    from datetime import date as dt_date

    from pyfintracker.exceptions import AccountNotFoundError
    from pyfintracker.models import Posting, Transaction
    from pyfintracker.validation import validate_amount

    if not sys.stdin.isatty():
        raise ReplRequiresTTYError(
            "REPL requires interactive terminal; "
            "use --from/--to for non-interactive entry"
        )

    # ── Date ───────────────────────────────────────────────────────────
    raw_date = _repl_prompt(prompt_fn, "Date (YYYY-MM-DD)")
    parts = raw_date.split("-")
    txn_date = dt_date(int(parts[0]), int(parts[1]), int(parts[2]))

    # ── Description ────────────────────────────────────────────────────
    description = _repl_prompt(prompt_fn, "Description")

    # ── Currency ───────────────────────────────────────────────────────
    currency = _repl_prompt(prompt_fn, "Currency", "COP").upper()

    # ── Posting loop ───────────────────────────────────────────────────
    postings: list[Posting] = []
    balance = Decimal("0")

    while True:
        account_name = _repl_prompt(prompt_fn, "Account")
        raw_amount = _repl_prompt(prompt_fn, "Amount")

        amount = _parse_repl_amount(raw_amount)
        amount = validate_amount(amount, currency)

        if resolve_account is not None:
            try:
                account_id = resolve_account(account_name)
            except AccountNotFoundError as e:
                console.print(f"[red]Error:[/red] {e}")
                if available_accounts:
                    suggestions = _suggest_accounts(account_name, available_accounts)
                    if suggestions:
                        console.print(f"  Did you mean: {', '.join(suggestions)}?")
                continue  # re-prompt
        else:
            account_id = 0

        balance += amount
        postings.append(Posting(account_id=account_id, amount=amount, currency=currency))

        if balance == Decimal("0") and len(postings) >= 2:
            console.print("[green]✓ Transaction balanced[/green]")
            break

        if balance != Decimal("0") and len(postings) >= 2:
            console.print(_show_diff(balance, currency))

    txn = Transaction(date=txn_date, description=description, currency=currency)
    return txn, postings


def _stdin_prompt(text: str, default: str = "") -> str:
    """Base prompt function: read input from stdin."""
    try:
        value = input(f"{text}: ")
    except EOFError:
        return default or ""
    return value or default


def _repl_prompt(prompt_fn: Callable[..., str], text: str, default: str = "") -> str:
    """Prompt the user, handling :abort and KeyboardInterrupt."""
    try:
        value = str(prompt_fn(text, default))
    except KeyboardInterrupt:
        confirm = str(prompt_fn("Discard transaction? (y/N)", "n"))
        if confirm.lower().startswith("y"):
            raise SystemExit(130) from None
        return _repl_prompt(prompt_fn, text, default)

    if value.strip().lower() == ":abort":
        raise SystemExit(130)

    return value


def _run_alembic(engine: Engine, action: str, revision: str) -> None:
    """Run an Alembic command on a given engine.

    This helper avoids re-importing Alembic in every command.
    """
    from alembic.command import current, downgrade, upgrade
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")

    if action == "status":
        # current() writes revision info to stdout
        with engine.connect() as conn:
            alembic_cfg.attributes["connection"] = conn
            current(alembic_cfg)
        return

    with engine.connect() as conn:
        alembic_cfg.attributes["connection"] = conn
        if action == "up":
            upgrade(alembic_cfg, revision)
        elif action == "down":
            downgrade(alembic_cfg, revision)


__all__ = [
    "account_app",
    "add",
    "app",
    "balance",
    "config_show",
    "init",
    "migrate",
    "repl_add_postings",
    "report_app",
    "report_month",
    "version",
]
