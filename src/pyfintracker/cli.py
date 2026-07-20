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
from pyfintracker.models import (
    Account,
    Budget,
    Posting,
    RecurringPosting,
    RecurringRule,
    Tag,
    Transaction,
)
from pyfintracker.reports import (
    compute_balance,
    compute_monthly_report,
    render_balance,
    render_monthly_report,
)
from pyfintracker.repository import (
    advance_recurring_rule,
    create_account,
    create_budget,
    create_opening_balance_transaction,
    create_recurring_rule,
    create_tag,
    create_transaction_with_postings,
    delete_budget,
    delete_recurring_rule,
    delete_tag,
    get_account_by_name,
    get_budget,
    get_budget_spending,
    get_budgets,
    get_due_recurring_rules,
    get_recurring_rule,
    get_recurring_rule_postings,
    get_recurring_rules,
    get_tag_by_name,
    list_accounts,
    list_tags,
    search_transactions,
    tag_transaction,
    untag_transaction,
)
from pyfintracker.validation import (
    validate_account_name,
    validate_amount,
    validate_currency,
    validate_date,
    validate_description,
    validate_tag_name,
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

# ── Tag sub-app ────────────────────────────────────────────────────────────

tag_app = typer.Typer(help="Manage tags.")
app.add_typer(tag_app, name="tag")

# ── Budget sub-app ─────────────────────────────────────────────────────────

budget_app = typer.Typer(help="Manage spending budgets.")
app.add_typer(budget_app, name="budget")

# ── Recurring sub-app ──────────────────────────────────────────────────────

recurring_app = typer.Typer(help="Manage recurring transaction rules.")
app.add_typer(recurring_app, name="recurring")


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
def search(
    query: str = typer.Argument(..., help="Search query (FTS5 syntax)"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
) -> None:
    """Search transactions by description.

    Uses FTS5 full-text search supporting AND/OR, quoted phrases,
    and prefix matching.  Example queries:\n
    \b
    fin search coffee
    fin search "café latte"
    fin search coffee AND groceries
    fin search "coffee*"
    """
    engine = _get_engine()
    with engine.connect() as conn:
        results = search_transactions(conn, query, limit=limit)

        if not results:
            console.print("No matching transactions found.")
            return

        table = Table(title=f"Search results for '{query}'")
        table.add_column("ID", style="dim")
        table.add_column("Date", style="cyan")
        table.add_column("Description", style="white")
        table.add_column("Account", style="yellow")
        table.add_column("Amount", style="green")
        table.add_column("Currency", style="blue")

        for txn in results:
            assert txn.id is not None
            row = conn.execute(
                text("""
                    SELECT a.name, p.amount
                    FROM postings p
                    JOIN accounts a ON a.id = p.account_id
                    WHERE p.transaction_id = :tid
                    LIMIT 1
                """),
                {"tid": txn.id},
            ).fetchone()
            account_name = row[0] if row else ""
            amount = row[1] if row else ""

            table.add_row(
                str(txn.id),
                str(txn.date or ""),
                txn.description,
                account_name,
                amount,
                txn.currency,
            )

        console.print(table)


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
    tags: list[str] | None = None,
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

            # Attach tags
            if tags:
                for tag_name in tags:
                    validated_tag = validate_tag_name(tag_name)
                    tag = get_tag_by_name(conn, validated_tag)
                    if tag is None:
                        console.print(f"[red]Error:[/red] Tag '{tag_name}' not found")
                        raise typer.Exit(code=1)
                    assert tag.id is not None
                    tag_transaction(conn, txn_id, tag.id)

        msg = (
            f"[green]✓[/green] Transaction #{txn_id}: {description} "
            f"({validated_amount} {validated_currency})"
        )
        if tags:
            msg += f" tags: {', '.join(tags)}"
        console.print(msg)

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
    tags: list[str] | None = typer.Option(None, "--tag", help="Tag(s) to attach (repeatable)"),  # noqa: B008
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

    _add_flag_mode(from_account, to_account, amount, currency, description, tags=tags)


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


# ── Tag sub-app commands ─────────────────────────────────────────────────


def _resolve_account_id(engine: Engine, name: str) -> int | None:
    """Resolve an account name to its id.  Returns None if not found."""
    with engine.connect() as conn:
        acct = get_account_by_name(conn, name)
        return acct.id if acct else None


@tag_app.command("create")
def tag_create(
    name: str = typer.Argument(..., help="Tag name"),
    account: str | None = typer.Option(None, "--account", help="Optional account scope"),
) -> None:
    """Create a new tag."""
    try:
        validated = validate_tag_name(name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None

    engine = _get_engine()
    try:
        account_id: int | None = None
        if account:
            acct = _resolve_account_id(engine, account)
            if acct is None:
                console.print(f"[red]Error:[/red] Account '{account}' not found")
                raise typer.Exit(code=1)
            account_id = acct

        with engine.begin() as conn:
            tag = create_tag(conn, Tag(name=validated, account_id=account_id))
        console.print(
            f"[green]✓[/green] Tag '{tag.name}' created (id={tag.id})"
        )
    except FinanceError as e:
        _render_error(e, console)
        raise typer.Exit(code=e.code) from None


@tag_app.command("list")
def tag_list(
    account: str | None = typer.Option(None, "--account", help="Filter by account"),
) -> None:
    """List all tags."""
    engine = _get_engine()
    try:
        account_id: int | None = None
        if account:
            acct = _resolve_account_id(engine, account)
            if acct is None:
                console.print(f"[red]Error:[/red] Account '{account}' not found")
                raise typer.Exit(code=1)
            account_id = acct

        with engine.connect() as conn:
            tags = list_tags(conn, account_id=account_id)

        if not tags:
            console.print("No tags found.")
            return

        from rich.table import Table

        table = Table(title="Tags")
        table.add_column("ID", style="dim")
        table.add_column("Name", style="cyan")
        table.add_column("Account ID")
        table.add_column("Created")
        for t in tags:
            table.add_row(
                str(t.id or ""),
                t.name,
                str(t.account_id or ""),
                t.created_at,
            )
        console.print(table)
    except FinanceError as e:
        _render_error(e, console)
        raise typer.Exit(code=e.code) from None


@tag_app.command("delete")
def tag_delete(
    name: str = typer.Argument(..., help="Tag name to delete"),
    account: str | None = typer.Option(None, "--account", help="Account scope"),
) -> None:
    """Delete a tag by name."""
    try:
        validated = validate_tag_name(name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None

    engine = _get_engine()
    try:
        account_id: int | None = None
        if account:
            acct = _resolve_account_id(engine, account)
            if acct is None:
                console.print(f"[red]Error:[/red] Account '{account}' not found")
                raise typer.Exit(code=1)
            account_id = acct

        with engine.begin() as conn:
            tag = get_tag_by_name(conn, validated, account_id=account_id)
            if tag is None:
                console.print(f"[red]Error:[/red] Tag '{name}' not found")
                raise typer.Exit(code=1)
            assert tag.id is not None
            delete_tag(conn, tag.id)
        console.print(f"[green]✓[/green] Tag '{name}' deleted")
    except FinanceError as e:
        _render_error(e, console)
        raise typer.Exit(code=e.code) from None


@tag_app.command("add")
def tag_add(
    tag_name: str = typer.Argument(..., help="Tag name"),
    transaction_id: int = typer.Argument(..., help="Transaction ID"),
) -> None:
    """Tag an existing transaction."""
    try:
        validated = validate_tag_name(tag_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None

    engine = _get_engine()
    try:
        with engine.begin() as conn:
            tag = get_tag_by_name(conn, validated)
            if tag is None:
                console.print(f"[red]Error:[/red] Tag '{tag_name}' not found")
                raise typer.Exit(code=1)
            assert tag.id is not None
            tag_transaction(conn, transaction_id, tag.id)
        console.print(
            f"[green]✓[/green] Tag '{tag_name}' added to transaction #{transaction_id}"
        )
    except FinanceError as e:
        _render_error(e, console)
        raise typer.Exit(code=e.code) from None


@tag_app.command("remove")
def tag_remove(
    tag_name: str = typer.Argument(..., help="Tag name"),
    transaction_id: int = typer.Argument(..., help="Transaction ID"),
) -> None:
    """Remove a tag from a transaction."""
    try:
        validated = validate_tag_name(tag_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None

    engine = _get_engine()
    try:
        with engine.begin() as conn:
            tag = get_tag_by_name(conn, validated)
            if tag is None:
                console.print(f"[red]Error:[/red] Tag '{tag_name}' not found")
                raise typer.Exit(code=1)
            assert tag.id is not None
            untag_transaction(conn, transaction_id, tag.id)
        console.print(
            f"[green]✓[/green] Tag '{tag_name}' removed from transaction #{transaction_id}"
        )
    except FinanceError as e:
        _render_error(e, console)
        raise typer.Exit(code=e.code) from None


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


# ── Register command ────────────────────────────────────────────────────────────


@app.command()
def register(
    description: str = typer.Argument(..., help="Transaction description"),
    amount: str = typer.Argument(..., help="Amount"),
    account: str = typer.Option(..., "--account", "-a", help="Account name"),
    currency: str = typer.Option("COP", "--currency", "-c", help="Currency ISO code"),
    date_str: str = typer.Option("", "--date", help="Transaction date (YYYY-MM-DD)"),
    tags: list[str] = typer.Option([], "--tag", help="Tags to attach (repeat or comma-separated)"),  # noqa: B008
) -> None:
    """Register a transaction with optional tags.

    Creates a balanced transaction debiting the given account and crediting
    Equity:Registered (auto-created).  Attaches any specified tags.
    """
    try:
        validated_currency = validate_currency(currency)
        validated_amount = validate_amount(amount, validated_currency)
        validated_description = validate_description(description)
        account_name = validate_account_name(account)
        txn_date: date = date.today()
        if date_str:
            txn_date = validate_date(date_str)
    except FinanceError as e:
        _render_error(e, console)
        raise typer.Exit(code=1) from None

    # Parse tags list — support both --tag t1 --tag t2 and --tag "t1,t2"
    parsed_tags: list[str] = []
    for t in tags:
        for part in t.split(","):
            part = part.strip()
            if part:
                try:
                    parsed_tags.append(validate_tag_name(part))
                except ValueError as e:
                    console.print(f"[red]Error:[/red] {e}")
                    raise typer.Exit(code=1) from None

    engine = _get_engine()
    try:
        with engine.begin() as conn:
            src = get_account_by_name(conn, account_name)
            if src is None:
                _render_error(AccountNotFoundError(f"Account '{account_name}' not found"), console)
                raise typer.Exit(code=1)
            assert src.id is not None

            # Get or create the equity counterpart
            equity = get_account_by_name(conn, "Equity:Registered")
            if equity is None:
                equity = create_account(
                    conn,
                    Account(name="Equity:Registered", currency=validated_currency, depth=1, kind="Equity"),
                )
            assert equity.id is not None

            txn = Transaction(
                date=txn_date,
                description=validated_description,
                currency=validated_currency,
            )
            postings = [
                Posting(account_id=src.id, amount=validated_amount, currency=validated_currency),
                Posting(account_id=equity.id, amount=-validated_amount, currency=validated_currency),
            ]

            txn_id = create_transaction_with_postings(conn, txn, postings)

            # Attach tags
            for tag_name in parsed_tags:
                tag = create_tag(conn, Tag(name=tag_name))
                assert tag.id is not None
                tag_transaction(conn, txn_id, tag.id)

            tag_msg = f" with tags: {', '.join(parsed_tags)}" if parsed_tags else ""
            console.print(
                f"[green]✓[/green] Transaction #{txn_id}: {validated_description} "
                f"({validated_amount} {validated_currency}){tag_msg}"
            )

    except (FinanceError, ValueError) as e:
        if isinstance(e, FinanceError):
            _render_error(e, console)
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=getattr(e, "code", 1)) from None


# ── Budget sub-app commands ──────────────────────────────────────────────


def _budget_spending_bar(spent: Decimal, limit: Decimal) -> str:
    """Return a color-coded progress bar string.

    Green (<80%), yellow (80-100%), red (>100%).
    """
    if limit <= Decimal("0"):
        return "[dim]N/A[/dim]"

    pct = (spent / limit) * 100
    bar_len = 20
    filled = min(int(pct / 100 * bar_len), bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)

    if pct < 80:
        return f"[green]{bar}[/green]"
    if pct < 100:
        return f"[yellow]{bar}[/yellow]"
    return f"[red]{bar}[/red]"


def _budget_pct_color(spent: Decimal, limit: Decimal) -> str:
    """Return a style string for the percentage column."""
    if limit <= Decimal("0"):
        return "dim"
    pct = (spent / limit) * 100
    if pct < 80:
        return "green"
    if pct < 100:
        return "yellow"
    return "red"


def _budget_scope_str(budget: Budget) -> str:
    """Return a string describing the budget's scope."""
    parts: list[str] = []
    if budget.account_id is not None:
        parts.append(f"acct#{budget.account_id}")
    if budget.tag_id is not None:
        parts.append(f"tag#{budget.tag_id}")
    return ", ".join(parts) if parts else "all"


@budget_app.command("create")
def budget_create(
    name: str = typer.Argument(..., help="Budget name"),
    amount: str = typer.Argument(..., help="Budget limit amount"),
    currency: str = typer.Option("COP", "--currency", "-c", help="Currency ISO code"),
    period: str = typer.Option("monthly", "--period", "-p", help="Period: monthly or yearly"),
    account_id: int | None = typer.Option(None, "--account", "-a", help="Account ID scope"),
    tag_id: int | None = typer.Option(None, "--tag", "-t", help="Tag ID scope"),
    start_date: str = typer.Option("", "--start-date", help="Start date (YYYY-MM-DD, default: today)"),
) -> None:
    """Create a new spending budget."""
    if period not in ("monthly", "yearly"):
        console.print(f"[red]Error:[/red] Invalid period '{period}'. Must be 'monthly' or 'yearly'.")
        raise typer.Exit(code=1)

    try:
        validated_amount = validate_amount(amount, currency)
        validated_currency = validate_currency(currency)
    except FinanceError as e:
        _render_error(e, console)
        raise typer.Exit(code=1) from None

    if not start_date:
        start_date = date.today().isoformat()
    else:
        try:
            validate_date(start_date)
        except FinanceError as e:
            _render_error(e, console)
            raise typer.Exit(code=1) from None

    budget = Budget(
        name=name,
        amount=validated_amount,
        currency=validated_currency,
        period=period,
        account_id=account_id,
        tag_id=tag_id,
        start_date=start_date,
        is_active=True,
    )

    engine = _get_engine()
    try:
        with engine.begin() as conn:
            created = create_budget(conn, budget)
        console.print(
            f"[green]✓[/green] Budget #{created.id} '{name}' created "
            f"({validated_amount} {validated_currency}/{period})"
        )
    except (FinanceError, ValueError) as e:
        if isinstance(e, FinanceError):
            _render_error(e, console)
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None


@budget_app.command("list")
def budget_list() -> None:
    """List all budgets with spending vs limit."""
    engine = _get_engine()
    with engine.connect() as conn:
        budgets = get_budgets(conn)

        if not budgets:
            from rich.text import Text

            console.print(Text("No budgets found.", style="dim"))
            return

        table = Table(title="Budgets")
        table.add_column("ID", style="dim")
        table.add_column("Name", style="cyan")
        table.add_column("Scope")
        table.add_column("Period", style="blue")
        table.add_column("Spent", style="yellow")
        table.add_column("Limit", style="green")
        table.add_column("Progress", width=24)

        today = date.today().isoformat()
        for b in budgets:
            spent = get_budget_spending(conn, b, today)
            bar = _budget_spending_bar(spent, b.amount)
            scope = _budget_scope_str(b)
            table.add_row(
                str(b.id or ""),
                b.name,
                scope,
                b.period,
                f"{spent:f}",
                f"{b.amount:f}",
                bar,
            )
    console.print(table)


@budget_app.command("report")
def budget_report(
    month: str = typer.Option("", "--month", help="Month in YYYY-MM format (default: current)"),
) -> None:
    """Show detailed budget status for a given month."""
    year_month = month
    if not year_month:
        today = date.today()
        year_month = f"{today.year}-{today.month:02d}"
    elif not re.match(r"^\d{4}-\d{2}$", year_month):
        _render_error(
            InvalidDate(f"Invalid month format '{year_month}'. Expected YYYY-MM."), console
        )
        raise typer.Exit(code=1)

    as_of_date = f"{year_month}-28"  # safe for month extraction
    engine = _get_engine()
    with engine.connect() as conn:
        budgets = get_budgets(conn)

        if not budgets:
            console.print("[dim]No budgets found.[/dim]")
            return

        table = Table(title=f"Budget Report — {year_month}")
        table.add_column("Name", style="cyan")
        table.add_column("Scope")
        table.add_column("Period", style="blue")
        table.add_column("Spent", style="yellow")
        table.add_column("Limit", style="green")
        table.add_column("Remaining")
        table.add_column("%", justify="right")

        for b in budgets:
            spent = get_budget_spending(conn, b, as_of_date)
            remaining = max(b.amount - spent, Decimal("0"))
            if b.amount > Decimal("0"):
                pct = (spent / b.amount) * 100
                pct_str = f"{pct:.1f}%"
            else:
                pct_str = "N/A"
            pct_style = _budget_pct_color(spent, b.amount)
            scope = _budget_scope_str(b)
            remaining_style = "red" if remaining <= Decimal("0") else "green"

            table.add_row(
                b.name,
                scope,
                b.period,
                f"{spent:f}",
                f"{b.amount:f}",
                f"[{remaining_style}]{remaining:f}[/{remaining_style}]",
                f"[{pct_style}]{pct_str}[/{pct_style}]",
            )
    console.print(table)


@budget_app.command("delete")
def budget_delete(
    budget_id: int = typer.Argument(..., help="Budget ID to delete"),
) -> None:
    """Delete a budget."""
    engine = _get_engine()
    with engine.begin() as conn:
        existing = get_budget(conn, budget_id)
        if existing is None:
            console.print(f"[red]Error:[/red] Budget #{budget_id} not found.")
            raise typer.Exit(code=1)
        delete_budget(conn, budget_id)
    console.print(f"[green]✓[/green] Budget #{budget_id} deleted.")


@app.command()
def tui(
    db_path: str | None = typer.Option(
        None, "--db", help="Database path (default: XDG data dir)"
    ),
) -> None:
    """Launch the Textual TUI browser."""
    from pyfintracker.tui import run_tui

    run_tui(db_path)


# ── Recurring sub-app commands ─────────────────────────────────────────────


@recurring_app.command("create")
def recurring_create(
    name: str = typer.Argument(..., help="Rule name"),
    frequency: str = typer.Argument(..., help="Frequency: daily|weekly|monthly|yearly"),
    amount: str = typer.Argument(..., help="Amount per posting"),
    account: str = typer.Argument(..., help="Account name for the posting"),
    description: str = typer.Option("", "--description", "-d", help="Rule description"),
    start_date: str = typer.Option("", "--start-date", help="Start date (YYYY-MM-DD, default: today)"),
    end_date: str | None = typer.Option(None, "--end-date", help="End date (YYYY-MM-DD, optional)"),
    currency: str = typer.Option("COP", "--currency", "-c", help="Currency ISO code"),
) -> None:
    """Create a recurring rule with one posting template.

    The rule will generate transactions automatically via ``fin recurring generate``.
    """
    valid_frequencies = ("daily", "weekly", "monthly", "yearly")
    if frequency not in valid_frequencies:
        console.print(
            f"[red]Error:[/red] Invalid frequency '{frequency}'. "
            f"Must be one of {', '.join(valid_frequencies)}."
        )
        raise typer.Exit(code=1)

    engine = _get_engine()
    try:
        validated_currency = validate_currency(currency)
        validated_amount = validate_amount(amount, validated_currency)
        validated_account = validate_account_name(account)

        txn_date: str
        if start_date:
            validate_date(start_date)
            txn_date = start_date
        else:
            txn_date = date.today().isoformat()

        if end_date:
            validate_date(end_date)

        with engine.begin() as conn:
            # Resolve the account
            src = get_account_by_name(conn, validated_account)
            if src is None:
                _render_error(
                    AccountNotFoundError(f"Account '{validated_account}' not found"), console
                )
                raise typer.Exit(code=1)
            assert src.id is not None

            rule = RecurringRule(
                name=name,
                description=description,
                frequency=frequency,
                start_date=txn_date,
                next_date=txn_date,
                end_date=end_date if end_date else None,
                is_active=True,
            )
            posting = RecurringPosting(
                account_id=src.id,
                amount=validated_amount,
                currency=validated_currency,
            )
            created = create_recurring_rule(conn, rule, [posting])

        console.print(
            f"[green]✓[/green] Recurring rule #{created.id} '{name}' created "
            f"({frequency}, {validated_amount} {validated_currency})"
        )

    except FinanceError as e:
        _render_error(e, console)
        raise typer.Exit(code=1) from None


@recurring_app.command("list")
def recurring_list() -> None:
    """List all recurring rules."""
    engine = _get_engine()
    with engine.connect() as conn:
        rules = get_recurring_rules(conn)

    if not rules:
        console.print("No recurring rules found.")
        return

    table = Table(title="Recurring Rules")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Frequency", style="yellow")
    table.add_column("Next Date", style="green")
    table.add_column("Active", style="blue")
    table.add_column("Description")
    for r in rules:
        active = "[green]✓[/green]" if r.is_active else "[red]✗[/red]"
        table.add_row(
            str(r.id or ""),
            r.name,
            r.frequency,
            r.next_date,
            active,
            r.description,
        )
    console.print(table)


@recurring_app.command("due")
def recurring_due(
    date_str: str = typer.Option("", "--date", "-d", help="Check date (YYYY-MM-DD, default: today)"),
) -> None:
    """List recurring rules that are due on or before a given date."""
    as_of: str = date_str if date_str else date.today().isoformat()

    engine = _get_engine()
    with engine.connect() as conn:
        rules = get_due_recurring_rules(conn, as_of)

    if not rules:
        console.print(f"No rules due on or before {as_of}.")
        return

    table = Table(title=f"Due Recurring Rules (as of {as_of})")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Frequency", style="yellow")
    table.add_column("Next Date", style="green")
    for r in rules:
        table.add_row(
            str(r.id or ""),
            r.name,
            r.frequency,
            r.next_date,
        )
    console.print(table)


@recurring_app.command("generate")
def recurring_generate(
    date_str: str = typer.Option("", "--date", "-d", help="Generation date (YYYY-MM-DD, default: today)"),
) -> None:
    """Generate transactions for all due recurring rules.

    For each due rule, creates one balanced transaction with the rule's
    postings, then advances the rule's ``next_date``.  Each rule is processed
    atomically: all-or-nothing within a single rule.
    """
    as_of: str = date_str if date_str else date.today().isoformat()

    engine = _get_engine()
    generated = 0

    with engine.begin() as conn:
        rules = get_due_recurring_rules(conn, as_of)

        for rule in rules:
            assert rule.id is not None
            postings = get_recurring_rule_postings(conn, rule.id)

            if not postings:
                continue

            # Build a balanced transaction: the rule's postings sum to zero
            # by creating an offsetting Equity:Registered posting if needed.
            txn_postings: list[Posting] = []
            for rp in postings:
                txn_postings.append(
                    Posting(
                        account_id=rp.account_id,
                        amount=rp.amount,
                        currency=rp.currency,
                    )
                )

            total = sum(p.amount for p in txn_postings)
            if total != Decimal("0"):
                # Add offsetting posting to Equity:Registered
                equity = get_account_by_name(conn, "Equity:Registered")
                if equity is None:
                    eq_currency = postings[0].currency if postings else "COP"
                    validate_currency(eq_currency)
                    equity = create_account(
                        conn,
                        Account(name="Equity:Registered", currency=eq_currency, depth=1, kind="Equity"),
                    )
                assert equity is not None and equity.id is not None
                txn_postings.append(
                    Posting(account_id=equity.id, amount=Decimal(-total), currency=postings[0].currency),
                )

            txn = Transaction(
                date=date.fromisoformat(as_of),
                description=f"Recurring: {rule.name}",
            )
            create_transaction_with_postings(conn, txn, txn_postings)

            # Advance next_date (deactivates if past end_date)
            advance_recurring_rule(conn, rule.id, rule.frequency)
            generated += 1

    if generated:
        console.print(f"[green]✓[/green] Generated {generated} transaction(s) from recurring rules.")
    else:
        console.print("No due rules to generate transactions for.")


@recurring_app.command("delete")
def recurring_delete(
    rule_id: int = typer.Argument(..., help="Rule ID to delete"),
) -> None:
    """Delete a recurring rule and its posting templates."""
    engine = _get_engine()
    with engine.begin() as conn:
        rule = get_recurring_rule(conn, rule_id)
        if rule is None:
            console.print(f"[red]Error:[/red] Rule #{rule_id} not found.")
            raise typer.Exit(code=1)
        delete_recurring_rule(conn, rule_id)
    console.print(f"[green]✓[/green] Recurring rule #{rule_id} deleted.")


__all__ = [
    "account_app",
    "add",
    "app",
    "balance",
    "budget_app",
    "config_show",
    "init",
    "migrate",
    "recurring_app",
    "register",
    "repl_add_postings",
    "report_app",
    "report_month",
    "search",
    "tag_add",
    "tag_app",
    "tag_create",
    "tag_delete",
    "tag_list",
    "tag_remove",
    "version",
]
