"""Typer CLI application for pyfintracker."""

from __future__ import annotations

from importlib.metadata import version as pkg_version

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import Engine

from pyfintracker.config import load_settings, source_of
from pyfintracker.db import make_engine

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
    from_account: str = typer.Option(..., "--from", help="Source account"),
    to_account: str = typer.Option(..., "--to", help="Destination account"),
    amount: str = typer.Option(..., "--amount", help="Amount to transfer"),
    currency: str = typer.Option("COP", "--currency", help="Currency"),
    description: str = typer.Option(..., "--description", help="Transaction description"),
) -> None:
    """Add a two-posting transaction (double-entry)."""
    from datetime import date

    from pyfintracker.exceptions import FinanceError
    from pyfintracker.models import Posting, Transaction
    from pyfintracker.repository import (
        create_transaction_with_postings,
        get_account_by_name,
    )
    from pyfintracker.validation import (
        validate_account_name,
        validate_amount,
        validate_currency,
        validate_description,
    )

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
    "config_show",
    "init",
    "migrate",
    "version",
]
