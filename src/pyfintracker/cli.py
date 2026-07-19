"""Typer CLI application for pyfintracker."""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation
from importlib.metadata import version as pkg_version

import typer
from alembic.command import downgrade, upgrade
from alembic.config import Config
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import Engine, text

from pyfintracker.config import load_settings, source_of
from pyfintracker.db import make_engine
from pyfintracker.exceptions import (
    AccountNotFoundError,
    ConfigError,
    FinanceError,
    InvalidAmount,
    InvalidDate,
    NotInitializedError,
    ReplRequiresTTYError,
    ValidationError,
)
from pyfintracker.fx import convert as fx_convert
from pyfintracker.fx import get_rate as fx_get_rate
from pyfintracker.models import Account, Posting, Transaction
from pyfintracker.reports import (
    compute_balance,
    compute_monthly_report,
    render_balance,
    render_monthly_report,
)
from pyfintracker.repository import (
    create_account,
    create_opening_balance_transaction,
    create_transaction_with_postings,
    get_account_by_name,
    list_accounts,
)
from pyfintracker.validation import (
    validate_account_name,
    validate_amount,
    validate_currency,
    validate_date,
    validate_description,
)

__version__ = pkg_version("pyfintracker")

app = typer.Typer(
    name="fin",
    help="Personal finance CLI with double-entry bookkeeping.",
    pretty_exceptions_show_locals=False,
)

console = Console()

# ── Account sub-app ──────────────────────────────────────────────────────────

account_app = typer.Typer(help="Manage accounts.")
app.add_typer(account_app, name="account")

# ── Report sub-app ───────────────────────────────────────────────────────────

report_app = typer.Typer(help="Financial reports.")
app.add_typer(report_app, name="report")


@app.callback(invoke_without_command=True)
def _main(ctx: typer.Context) -> None:
    """pyfintracker CLI — manage your personal finances."""
    # If no subcommand is given, show help
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


def _render_error(error: FinanceError, console: Console) -> None:
    """Render an error with a styled Rich panel based on its type.

    Panel colors and titles per error class:
    - ValidationError and subclasses → red panel "Validation Error"
    - AccountNotFoundError → red panel "Account Not Found"
    - ConfigError / NotInitializedError → yellow panel "Configuration Error"
    - ReplRequiresTTYError → plain stderr text "REPL Error"
    - Default (FinanceError base) → plain text "Error"
    """
    if isinstance(error, ReplRequiresTTYError):
        console.print(f"[bold]REPL Error:[/bold] {error.message}")
    elif isinstance(error, (ConfigError, NotInitializedError)):
        console.print(Panel(f"[yellow]{error.message}[/yellow]", title="Configuration Error"))
    elif isinstance(error, AccountNotFoundError):
        console.print(Panel(f"[red]{error.message}[/red]", title="Account Not Found"))
    elif isinstance(error, ValidationError):
        console.print(Panel(f"[red]{error.message}[/red]", title="Validation Error"))
    else:
        console.print(f"[bold]Error:[/bold] {error.message}")


def _get_engine() -> Engine:
    """Create a SQLAlchemy engine from the configured db_path."""
    settings = load_settings()
    return make_engine(f"sqlite:///{settings.db_path}")


@app.command()
def convert(
    amount: str = typer.Argument(..., help="Amount to convert"),
    from_ccy: str = typer.Argument(..., help="Source currency ISO code"),
    to_ccy: str = typer.Argument(..., help="Target currency ISO code"),
    on_date: str = typer.Option("", "--date", help="Rate date (YYYY-MM-DD, default: latest)"),
) -> None:
    """Convert an amount between currencies using live FX rates.

    Examples:\n
    fin convert 100 USD COP\n
    fin convert 50000 COP USD --date 2026-07-18
    """
    try:
        validated_from = validate_currency(from_ccy)
        validated_to = validate_currency(to_ccy)
        validated_amount = validate_amount(amount, validated_from)
    except FinanceError as e:
        _render_error(e, console)
        raise typer.Exit(code=1) from None

    on: date | None = None
    if on_date:
        try:
            on = validate_date(on_date)
        except FinanceError as e:
            _render_error(e, console)
            raise typer.Exit(code=1) from None

    try:
        result = fx_convert(validated_amount, validated_from, validated_to, on=on)
    except FinanceError as e:
        _render_error(e, console)
        raise typer.Exit(code=e.code) from None

    try:
        rate_info = fx_get_rate(validated_from, validated_to, on=on)
        rate_str = f"{rate_info.rate} ({rate_info.date}, {rate_info.source})"
    except FinanceError:
        rate_str = "unknown"

    console.print(f"{validated_amount} {validated_from} = {result} {validated_to} (rate {rate_str})")


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
        for ext in ("-wal", "-shm"):
            p = db_path.with_name(db_path.name + ext)
            if p.exists():
                p.unlink()

    db_path.parent.mkdir(parents=True, exist_ok=True)

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
        "display_currency",
        "account_name_max_length",
        "description_max_length",
        "snapshot_width",
        "journal_mode",
    ]:
        value = getattr(settings, field)
        source = source_of(field)
        data[field] = (str(value), source)

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
    try:
        canonical = validate_account_name(name)
        validated_currency = validate_currency(currency)
        if description:
            validate_description(description)
    except FinanceError as e:
        _render_error(e, console)
        raise typer.Exit(code=1) from None

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
                create_opening_balance_transaction(conn, account, validated_amount)
                console.print(
                    f"[green]✓[/green] '{canonical}' created with opening balance "
                    f"{validated_amount} {validated_currency}"
                )
                return

            console.print(f"[green]✓[/green] Account '{canonical}' created ({validated_currency})")

    except (FinanceError, ValueError) as e:
        if isinstance(e, FinanceError):
            _render_error(e, console)
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None


@account_app.command("list")
def account_list() -> None:
    """List all accounts."""
    engine = _get_engine()
    with engine.begin() as conn:
        accounts = list_accounts(conn)

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


# ── `add` command (flag-mode + REPL-mode helpers) ─────────────────────────────


def _add_flag_mode(
    from_account: str,
    to_account: str,
    amount: str,
    currency: str,
    description: str,
) -> None:
    """Add a transaction from explicit CLI flags (non-interactive)."""
    try:
        validated_amount = validate_amount(amount, currency)
        from_name = validate_account_name(from_account)
        to_name = validate_account_name(to_account)
        validated_currency = validate_currency(currency)
        validate_description(description)
    except FinanceError as e:
        _render_error(e, console)
        raise typer.Exit(code=1) from None

    engine = _get_engine()
    try:
        with engine.begin() as conn:
            src = get_account_by_name(conn, from_name)
            if src is None:
                _render_error(AccountNotFoundError(f"Account '{from_name}' not found"), console)
                raise typer.Exit(code=1)
            assert src.id is not None
            dst = get_account_by_name(conn, to_name)
            if dst is None:
                _render_error(AccountNotFoundError(f"Account '{to_name}' not found"), console)
                raise typer.Exit(code=1)
            assert dst.id is not None

            txn = Transaction(
                date=date.today(),
                description=description,
                currency=validated_currency,
            )
            postings = [
                Posting(account_id=src.id, amount=-validated_amount, currency=validated_currency),
                Posting(account_id=dst.id, amount=validated_amount, currency=validated_currency),
            ]

            txn_id = create_transaction_with_postings(conn, txn, postings)

        console.print(
            f"[green]✓[/green] Transaction #{txn_id}: {description} "
            f"({validated_amount} {validated_currency})"
        )

    except (FinanceError, ValueError) as e:
        if isinstance(e, FinanceError):
            _render_error(e, console)
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=getattr(e, "code", 1)) from None


def _add_repl_mode() -> None:
    """Add a transaction through the interactive REPL."""
    engine = _get_engine()

    try:
        with engine.begin() as conn:
            accounts = list_accounts(conn)
            account_names = [a.name for a in accounts]

            def _resolve(name: str) -> int | None:
                acct = get_account_by_name(conn, name)
                if acct is None or acct.id is None:
                    return None
                return acct.id

            txn, postings = repl_add_postings(
                console,
                _stdin_prompt,
                _resolve,
                account_names,
            )
            txn_id = create_transaction_with_postings(conn, txn, postings)

        console.print(f"[green]✓[/green] Transaction #{txn_id}: {txn.description}")
    except FinanceError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=getattr(e, "code", 1)) from None


@app.command()
def add(
    from_account: str | None = typer.Option(None, "--from", help="Source account"),
    to_account: str | None = typer.Option(None, "--to", help="Destination account"),
    amount: str | None = typer.Option(None, "--amount", help="Amount to transfer"),
    currency: str = typer.Option("COP", "--currency", help="Currency"),
    description: str | None = typer.Option(None, "--description", help="Transaction description"),
) -> None:
    """Add a transaction. Use flags for direct entry, or omit flags for REPL."""
    flag_args = [from_account, to_account, amount, description]
    flag_mode = any(a is not None for a in flag_args)

    if not flag_mode:
        _add_repl_mode()
        return

    if not all(a is not None for a in flag_args):
        console.print(
            "[red]Error:[/red] Use all flags (--from, --to, --amount, --description) "
            "or none (for REPL mode)."
        )
        raise typer.Exit(code=2)

    # Narrow types after the all-not-None guard (mypy can't do this)
    assert from_account is not None
    assert to_account is not None
    assert amount is not None
    assert description is not None

    _add_flag_mode(from_account, to_account, amount, currency, description)


# ── Report sub-app commands ──────────────────────────────────────────────────


def _resolve_display_currency(currency: str | None) -> str:
    """Resolve the display currency from CLI --currency flag, config, or default.

    Validates the currency before returning.
    """
    if currency:
        return validate_currency(currency)

    settings = load_settings()
    dsp = settings.display_currency or "COP"
    return validate_currency(dsp)


@report_app.command("month")
def report_month(
    month: str = typer.Option("", "--month", help="Month in YYYY-MM format (default: current)"),
    currency: str | None = typer.Option(None, "--currency", help="Display currency ISO code"),
) -> None:
    """Show income/expense report for a month."""
    try:
        validated_currency = _resolve_display_currency(currency)
    except FinanceError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None

    year_month = month
    if not year_month:
        today = date.today()
        year_month = f"{today.year}-{today.month:02d}"
    elif not re.match(r"^\d{4}-\d{2}$", year_month):
        _render_error(
            InvalidDate(f"Invalid month format '{year_month}'. Expected YYYY-MM."), console
        )
        raise typer.Exit(code=1)

    engine = _get_engine()
    with engine.begin() as conn:
        report = compute_monthly_report(conn, year_month, display_currency=validated_currency)
    render_monthly_report(report, console)


@report_app.command("balance")
def balance(
    account_name: str = typer.Argument(None, help="Filter by account name (optional)"),
    currency: str | None = typer.Option(None, "--currency", help="Display currency ISO code"),
) -> None:
    """Show account balances and net worth."""
    try:
        validated_currency = _resolve_display_currency(currency)
    except FinanceError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None

    engine = _get_engine()
    with engine.begin() as conn:
        report = compute_balance(conn, display_currency=validated_currency)

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
    resolve_account: Callable[[str], int | None] | None = None,
    available_accounts: list[str] | None = None,
) -> tuple[Transaction, list[Posting]]:
    """Interactive REPL for transaction entry.

    Args:
        console: Rich Console for output.
        prompt_fn: Callable accepting (prompt_text, default="") and returning
            user input.  In production wraps questionary / input(); in tests
            returns scripted replies.
        resolve_account: Optional callback to resolve account names to IDs.
            Returns None when the name is unknown; the REPL owns the
            suggestions / re-prompt UX.  When None, account_id is 0
            (for tests).
        available_accounts: Optional list of valid account names for suggestions.

    Returns:
        Tuple of (Transaction, List[Posting]) ready to save.
        When resolve_account is provided, Posting.account_id is the real ID.
    """
    if not sys.stdin.isatty():
        raise ReplRequiresTTYError(
            "REPL requires interactive terminal; use --from/--to for non-interactive entry"
        )

    raw_date = _repl_prompt(prompt_fn, "Date (YYYY-MM-DD)")
    parts = raw_date.split("-")
    txn_date = date(int(parts[0]), int(parts[1]), int(parts[2]))

    description = _repl_prompt(prompt_fn, "Description")
    currency = _repl_prompt(prompt_fn, "Currency", "COP").upper()

    postings: list[Posting] = []
    balance = Decimal("0")

    while True:
        account_name = _repl_prompt(prompt_fn, "Account")
        raw_amount = _repl_prompt(prompt_fn, "Amount")

        amount = _parse_repl_amount(raw_amount)
        amount = validate_amount(amount, currency)

        account_id = 0
        if resolve_account is not None:
            resolved = resolve_account(account_name)
            if resolved is None:
                console.print(f"[red]Error:[/red] Account '{account_name}' not found")
                if available_accounts:
                    suggestions = _suggest_accounts(account_name, available_accounts)
                    if suggestions:
                        console.print(f"  Did you mean: {', '.join(suggestions)}?")
                continue  # re-prompt
            account_id = resolved

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
    alembic_cfg = Config("alembic.ini")

    if action == "status":
        with engine.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
            current_rev = row[0] if row else "(none)"
            print(f"{current_rev} (head)")
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
