"""SQLAlchemy 2.0 Core repository.

All functions accept a ``sqlalchemy.Connection`` (not Session) and operate
on the accounts, transactions, and postings tables defined in migration 0001.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, text

from pyfintracker.exceptions import AccountNotFoundError, ValidationError
from pyfintracker.models import (
    Account,
    Posting,
    Rate,
    RecurringPosting,
    RecurringRule,
    Tag,
    Transaction,
    compute_next_date,
)
from pyfintracker.validation import validate_account_name, validate_tag_name, validate_transaction


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
            raise AccountNotFoundError(f"Parent account id={account.parent_id} not found")

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
            raise ValidationError(f"Account '{account.name}' already exists") from None
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
    rows = conn.execute(text("SELECT * FROM accounts ORDER BY name")).fetchall()
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
    conn: Connection,
    txn: Transaction,
    postings: Sequence[Posting],
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


def create_opening_balance_transaction(
    conn: Connection,
    account: Account,
    amount: Decimal,
) -> int:
    """Create the opening-balance transaction (Dr account, Cr Equity:OpeningBalances).

    Idempotent on the equity account — auto-creates it if missing.
    Returns the new transaction id.
    """
    assert account.id is not None, "account must be persisted before opening balance"
    assert account.currency is not None

    equity = get_account_by_name(conn, "Equity:OpeningBalances")
    if equity is None:
        equity = upsert_account(conn, name="Equity:OpeningBalances", currency=account.currency)
    assert equity.id is not None

    txn = Transaction(
        date=date.today(),
        description=f"Opening balance for {account.name}",
        currency=account.currency,
    )
    postings = [
        Posting(account_id=account.id, amount=amount, currency=account.currency),
        Posting(account_id=equity.id, amount=-amount, currency=account.currency),
    ]
    return create_transaction_with_postings(conn, txn, postings)


# ── Rate repository functions ──────────────────────────────────────────────────


def _row_to_rate(row: Any) -> Rate:
    """Convert a raw DB row to Rate. Delegates type coercion to ``Rate.from_row``."""
    return Rate.from_row(row)


def get_cached_rate(conn: Connection, from_ccy: str, to_ccy: str, on: date) -> Rate | None:
    """Look up a cached rate by (date, base_currency, target_currency).

    Returns None if not found.  Does NOT invert — caller handles inversion.
    Returns Rate with fetched_at populated if the column exists.
    """
    row = conn.execute(
        text(
            "SELECT * FROM rates WHERE base_currency = :base AND target_currency = :target AND date = :dt LIMIT 1"
        ),
        {"base": from_ccy, "target": to_ccy, "dt": str(on)},
    ).fetchone()
    return _row_to_rate(row) if row else None


def upsert_rate(conn: Connection, rate: Rate) -> Rate:
    """Insert or update a rate row. Idempotent on (date, from_ccy, to_ccy).

    Returns the Rate as stored (with id populated).
    When fetched_at is available (after 0002 migration), it is stored and returned.
    """
    params = rate.to_row()
    params.pop("id", None)  # Let DB auto-generate / ignore on conflict
    # Convert typed objects to strings for SQLite TEXT columns
    params["date"] = str(params["date"])
    params["rate"] = str(params.get("rate", ""))

    if params.get("fetched_at") is not None:
        params["fetched_at"] = str(params["fetched_at"])
        row = conn.execute(
            text("""
                INSERT INTO rates (base_currency, target_currency, rate, date, source, fetched_at)
                VALUES (:base_currency, :target_currency, :rate, :date, :source, :fetched_at)
                ON CONFLICT(base_currency, target_currency, date)
                DO UPDATE SET
                    rate = excluded.rate,
                    fetched_at = excluded.fetched_at
                RETURNING id
            """),
            params,
        ).fetchone()
    else:
        row = conn.execute(
            text("""
                INSERT INTO rates (base_currency, target_currency, rate, date, source)
                VALUES (:base_currency, :target_currency, :rate, :date, :source)
                ON CONFLICT(base_currency, target_currency, date)
                DO UPDATE SET rate = excluded.rate
                RETURNING id
            """),
            params,
        ).fetchone()

    assert row is not None
    # Fetch the full row to return complete Rate
    inserted_id = row[0]
    full = conn.execute(
        text("SELECT * FROM rates WHERE id = :id"),
        {"id": inserted_id},
    ).fetchone()
    assert full is not None
    return _row_to_rate(full)


def list_cached_rates(
    conn: Connection,
    *,
    since: date | None = None,
) -> Sequence[Rate]:
    """List all cached rates, optionally filtered by minimum date."""
    if since is not None:
        rows = conn.execute(
            text(
                "SELECT * FROM rates WHERE date >= :since ORDER BY date, base_currency, target_currency"
            ),
            {"since": str(since)},
        ).fetchall()
    else:
        rows = conn.execute(
            text("SELECT * FROM rates ORDER BY date, base_currency, target_currency"),
        ).fetchall()
    return [_row_to_rate(row) for row in rows]


# ── Tag repository functions ──────────────────────────────────────────────────


def create_tag(conn: Connection, tag: Tag) -> Tag:
    """Insert a new tag.  Returns the Tag with its generated id.

    Raises:
        ValueError: if the tag name is invalid.
        ValidationError: if the tag name already exists (UNIQUE constraint).
    """
    validate_tag_name(tag.name)
    try:
        row = conn.execute(
            text("""
                INSERT INTO tags (name, account_id)
                VALUES (:name, :account_id)
                RETURNING id, name, account_id, created_at
            """),
            {"name": tag.name, "account_id": tag.account_id},
        ).fetchone()
        assert row is not None
        return Tag(id=row[0], name=row[1], account_id=row[2], created_at=row[3])
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            from pyfintracker.exceptions import ValidationError

            raise ValidationError(f"Tag '{tag.name}' already exists") from None
        raise


def get_tag_by_name(
    conn: Connection,
    name: str,
    account_id: int | None = None,
) -> Tag | None:
    """Look up a tag by name, optionally filtering by account.

    Returns the Tag or ``None`` if not found.
    """
    if account_id is not None:
        row = conn.execute(
            text("SELECT * FROM tags WHERE name = :name AND account_id = :aid"),
            {"name": name, "aid": account_id},
        ).fetchone()
    else:
        row = conn.execute(
            text("SELECT * FROM tags WHERE name = :name"),
            {"name": name},
        ).fetchone()
    if row is None:
        return None
    return Tag(id=row[0], name=row[1], account_id=row[2], created_at=row[3])


def list_tags(conn: Connection, account_id: int | None = None) -> list[Tag]:
    """Return all tags, optionally filtered by account.  Ordered by name."""
    if account_id is not None:
        rows = conn.execute(
            text("SELECT * FROM tags WHERE account_id = :aid ORDER BY name"),
            {"aid": account_id},
        ).fetchall()
    else:
        rows = conn.execute(text("SELECT * FROM tags ORDER BY name")).fetchall()
    return [Tag(id=r[0], name=r[1], account_id=r[2], created_at=r[3]) for r in rows]


def delete_tag(conn: Connection, tag_id: int) -> None:
    """Delete a tag by id.  Also removes junction rows via CASCADE."""
    conn.execute(text("DELETE FROM tags WHERE id = :id"), {"id": tag_id})


def tag_transaction(conn: Connection, transaction_id: int, tag_id: int) -> None:
    """Attach a tag to a transaction.  Idempotent (no-op on duplicate)."""
    conn.execute(
        text("""
            INSERT OR IGNORE INTO transaction_tags (transaction_id, tag_id)
            VALUES (:txn_id, :tag_id)
        """),
        {"txn_id": transaction_id, "tag_id": tag_id},
    )


def untag_transaction(conn: Connection, transaction_id: int, tag_id: int) -> None:
    """Remove a tag from a transaction."""
    conn.execute(
        text("""
            DELETE FROM transaction_tags
            WHERE transaction_id = :txn_id AND tag_id = :tag_id
        """),
        {"txn_id": transaction_id, "tag_id": tag_id},
    )


def get_transaction_tags(conn: Connection, transaction_id: int) -> list[Tag]:
    """Return all tags attached to a transaction."""
    rows = conn.execute(
        text("""
            SELECT t.id, t.name, t.account_id, t.created_at
            FROM tags t
            JOIN transaction_tags tt ON tt.tag_id = t.id
            WHERE tt.transaction_id = :txn_id
            ORDER BY t.name
        """),
        {"txn_id": transaction_id},
    ).fetchall()
    return [Tag(id=r[0], name=r[1], account_id=r[2], created_at=r[3]) for r in rows]


# ── Search repository functions ──────────────────────────────────────────────


def rebuild_fts(conn: Connection) -> None:
    """Rebuild the FTS5 index (used after bulk import)."""
    conn.execute(text("INSERT INTO transactions_fts(transactions_fts) VALUES('rebuild')"))


def search_transactions(conn: Connection, query: str, limit: int = 20) -> list[Transaction]:
    """Full-text search over transaction descriptions.

    Returns matching transactions ordered by FTS relevance, up to ``limit``.
    """
    rows = conn.execute(
        text("""
            SELECT t.id, t.date, t.description, t.currency
            FROM transactions t
            JOIN transactions_fts fts ON t.id = fts.rowid
            WHERE transactions_fts MATCH :query
            ORDER BY rank
            LIMIT :limit
        """),
        {"query": query, "limit": limit},
    ).fetchall()
    return [Transaction.from_row(r) for r in rows]


# ── Recurring rule repository functions ────────────────────────────────────


def create_recurring_rule(
    conn: Connection,
    rule: RecurringRule,
    postings: Sequence[RecurringPosting],
) -> RecurringRule:
    """Create a recurring rule and its posting templates atomically.

    Returns the ``RecurringRule`` with its generated ``id`` populated.
    """
    params = rule.to_row()
    params.pop("id", None)

    row = conn.execute(
        text("""
            INSERT INTO recurring_rules
                (name, description, frequency, interval_days,
                 day_of_month, day_of_week, start_date, end_date, next_date, is_active)
            VALUES
                (:name, :description, :frequency, :interval_days,
                 :day_of_month, :day_of_week, :start_date, :end_date, :next_date, :is_active)
            RETURNING id
        """),
        params,
    ).fetchone()
    assert row is not None
    rule_id: int = row[0]

    for p in postings:
        p_params = p.to_row()
        p_params.pop("id", None)
        p_params["rule_id"] = rule_id
        conn.execute(
            text("""
                INSERT INTO recurring_postings (rule_id, account_id, amount, currency)
                VALUES (:rule_id, :account_id, :amount, :currency)
            """),
            p_params,
        )

    return RecurringRule(
        id=rule_id,
        name=rule.name,
        description=rule.description,
        frequency=rule.frequency,
        interval_days=rule.interval_days,
        day_of_month=rule.day_of_month,
        day_of_week=rule.day_of_week,
        start_date=rule.start_date,
        end_date=rule.end_date,
        next_date=rule.next_date,
        is_active=rule.is_active,
        created_at="",
    )


def get_recurring_rules(conn: Connection) -> list[RecurringRule]:
    """Return all recurring rules ordered by name."""
    rows = conn.execute(
        text("SELECT * FROM recurring_rules ORDER BY name"),
    ).fetchall()
    return [RecurringRule.from_row(r) for r in rows]


def get_recurring_rule(conn: Connection, rule_id: int) -> RecurringRule | None:
    """Look up a recurring rule by id.  Returns ``None`` if not found."""
    row = conn.execute(
        text("SELECT * FROM recurring_rules WHERE id = :id"),
        {"id": rule_id},
    ).fetchone()
    return RecurringRule.from_row(row) if row else None


def get_recurring_rule_postings(conn: Connection, rule_id: int) -> list[RecurringPosting]:
    """Return all posting templates for a recurring rule."""
    rows = conn.execute(
        text("SELECT * FROM recurring_postings WHERE rule_id = :rid ORDER BY id"),
        {"rid": rule_id},
    ).fetchall()
    return [RecurringPosting.from_row(r) for r in rows]


def update_recurring_rule(conn: Connection, rule: RecurringRule) -> None:
    """Update an existing recurring rule's mutable fields."""
    assert rule.id is not None, "Cannot update a rule without an id"
    conn.execute(
        text("""
            UPDATE recurring_rules SET
                name = :name,
                description = :description,
                frequency = :frequency,
                interval_days = :interval_days,
                day_of_month = :day_of_month,
                day_of_week = :day_of_week,
                start_date = :start_date,
                end_date = :end_date,
                next_date = :next_date,
                is_active = :is_active
            WHERE id = :id
        """),
        rule.to_row(),
    )


def delete_recurring_rule(conn: Connection, rule_id: int) -> None:
    """Delete a recurring rule and its postings (CASCADE)."""
    conn.execute(text("DELETE FROM recurring_rules WHERE id = :id"), {"id": rule_id})


def get_due_recurring_rules(conn: Connection, as_of_date: str) -> list[RecurringRule]:
    """Return active rules whose ``next_date`` is on or before ``as_of_date``."""
    rows = conn.execute(
        text("""
            SELECT * FROM recurring_rules
            WHERE next_date <= :as_of AND is_active = 1
            ORDER BY name
        """),
        {"as_of": as_of_date},
    ).fetchall()
    return [RecurringRule.from_row(r) for r in rows]


def set_next_date(conn: Connection, rule_id: int, next_date: str) -> None:
    """Update the ``next_date`` of a recurring rule."""
    conn.execute(
        text("UPDATE recurring_rules SET next_date = :nd WHERE id = :id"),
        {"nd": next_date, "id": rule_id},
    )


def advance_recurring_rule(conn: Connection, rule_id: int, frequency: str) -> None:
    """Advance ``next_date`` by one period according to ``frequency``.

    Also checks ``end_date``: if the new next_date is past end_date,
    the rule is deactivated (``is_active = 0``).
    """
    row = conn.execute(
        text("SELECT next_date, end_date FROM recurring_rules WHERE id = :id"),
        {"id": rule_id},
    ).fetchone()
    assert row is not None
    current_next = str(row[0])
    end_date: str | None = str(row[1]) if row[1] else None

    new_next = compute_next_date(current_next, frequency)

    if end_date is not None and new_next > end_date:
        conn.execute(
            text("UPDATE recurring_rules SET is_active = 0 WHERE id = :id"),
            {"id": rule_id},
        )
    else:
        conn.execute(
            text("UPDATE recurring_rules SET next_date = :nd WHERE id = :id"),
            {"nd": new_next, "id": rule_id},
        )


__all__ = [
    "account_has_postings",
    "advance_recurring_rule",
    "create_account",
    "create_opening_balance_transaction",
    "create_recurring_rule",
    "create_tag",
    "create_transaction_with_postings",
    "delete_recurring_rule",
    "delete_tag",
    "get_account_by_id",
    "get_account_by_name",
    "get_cached_rate",
    "get_due_recurring_rules",
    "get_recurring_rule",
    "get_recurring_rule_postings",
    "get_recurring_rules",
    "get_tag_by_name",
    "get_transaction_tags",
    "list_accounts",
    "list_cached_rates",
    "list_tags",
    "rebuild_fts",
    "search_transactions",
    "set_next_date",
    "tag_transaction",
    "untag_transaction",
    "upsert_account",
    "upsert_rate",
]
