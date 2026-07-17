"""SQLAlchemy 2.0 Core repository.

All functions accept a ``sqlalchemy.Connection`` (not Session) and operate
on the accounts, transactions, and postings tables defined in migration 0001.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Connection, text

from pyfintracker.exceptions import AccountNotFoundError, ValidationError
from pyfintracker.models import Account, Posting, Transaction
from pyfintracker.validation import validate_account_name, validate_transaction


def create_account(conn: Connection, account: Account) -> Account:
    """Insert a new account. Returns the Account with its generated id.

    Raises:
        InvalidAccountName: if the account name doesn't match the regex.
        AccountNotFoundError: if ``parent_id`` references a non-existent account.
        ValidationError: if the account name already exists (UNIQUE constraint).
    """
    validate_account_name(account.name)

    if account.parent_id is not None:
        result = conn.execute(
            text("SELECT id FROM accounts WHERE id = :id"),
            {"id": account.parent_id},
        ).fetchone()
        if result is None:
            raise AccountNotFoundError(
                f"Parent account id={account.parent_id} not found"
            )

    params = account.to_row()
    params.pop("id", None)  # let DB auto-generate
    params.setdefault("parent_id", None)  # ensure key even when None

    try:
        insert_result = conn.execute(
            text("""
                INSERT INTO accounts (name, parent_id, currency, depth, kind, is_archived)
                VALUES (:name, :parent_id, :currency, :depth, :kind, :is_archived)
                RETURNING id
            """),
            params,
        )
        row = insert_result.fetchone()
        assert row is not None
        return Account(
            id=row[0],
            name=account.name,
            parent_id=account.parent_id,
            currency=account.currency,
            depth=account.depth,
            kind=account.kind,
            is_archived=account.is_archived,
        )
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            raise ValidationError(
                f"Account '{account.name}' already exists"
            ) from None
        raise


def get_account_by_name(conn: Connection, name: str) -> Account | None:
    """Look up an account by exact name (case-insensitive via COLLATE NOCASE).

    Returns the Account or ``None`` if not found.
    """
    row = conn.execute(
        text("SELECT * FROM accounts WHERE name = :name"),
        {"name": name},
    ).fetchone()
    return Account.from_row(row) if row else None


def get_account_by_id(conn: Connection, id: int) -> Account | None:
    """Look up an account by its primary key id.

    Returns the Account or ``None`` if not found.
    """
    row = conn.execute(
        text("SELECT * FROM accounts WHERE id = :id"),
        {"id": id},
    ).fetchone()
    return Account.from_row(row) if row else None


def list_accounts(conn: Connection) -> Sequence[Account]:
    """Return all accounts ordered alphabetically by name."""
    rows = conn.execute(
        text("SELECT * FROM accounts ORDER BY name")
    ).fetchall()
    return [Account.from_row(row) for row in rows]


def account_has_postings(conn: Connection, account_id: int) -> bool:
    """Return True if any posting references the given account id."""
    result = conn.execute(
        text("SELECT 1 FROM postings WHERE account_id = :id LIMIT 1"),
        {"id": account_id},
    ).fetchone()
    return result is not None


def upsert_account(conn: Connection, name: str, currency: str) -> Account:
    """Get an existing account by name or create a new one.

    Returns the existing account if found, otherwise creates a new one
    with auto-derived kind and depth.
    """
    existing = get_account_by_name(conn, name)
    if existing is not None:
        return existing

    parts = name.split(":")
    kind = parts[0]
    depth = len(parts) - 1
    return create_account(
        conn,
        Account(name=name, currency=currency, depth=depth, kind=kind),
    )


def create_transaction_with_postings(
    conn: Connection, txn: Transaction, postings: Sequence[Posting],
) -> int:
    """Create a transaction with its postings in a single atomic write.

    Validates the transaction first, then inserts both the transaction
    and its postings. Returns the new transaction ID.
    """
    validate_transaction(txn, postings)

    result = conn.execute(
        text("""
            INSERT INTO transactions (date, description)
            VALUES (:date, :description)
        """),
        {"date": str(txn.date), "description": txn.description},
    )
    txn_id = result.lastrowid

    for p in postings:
        conn.execute(
            text("""
                INSERT INTO postings (transaction_id, account_id, amount, currency)
                VALUES (:transaction_id, :account_id, :amount, :currency)
            """),
            {
                "transaction_id": txn_id,
                "account_id": p.account_id,
                "amount": str(p.amount),
                "currency": p.currency,
            },
        )

    return txn_id


__all__ = [
    "account_has_postings",
    "create_account",
    "create_transaction_with_postings",
    "get_account_by_id",
    "get_account_by_name",
    "list_accounts",
    "upsert_account",
]
