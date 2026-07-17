"""Integration tests for repository operations — T-2.6 through T-2.10.

All tests use the ``connection`` fixture (Alembic-upgraded in-memory DB
with 11 starter accounts).  Repository functions accept ``Connection``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Connection, text

from pyfintracker.exceptions import (
    AccountNotFoundError,
    InvalidAccountName,
    ValidationError,
)
from pyfintracker.models import Account
from pyfintracker.repository import (
    account_has_postings,
    create_account,
    get_account_by_id,
    get_account_by_name,
    list_accounts,
)


@pytest.mark.integration
class TestCreateAccount:
    """T-2.6: repository.create_account(conn, account) -> Account."""

    def test_create_account(self, connection: Connection) -> None:
        """Happy path — create a new account, returns Account with id."""
        acct = Account(name="Income:Freelance", currency="COP", depth=1, kind="Income")
        result = create_account(connection, acct)
        assert result.id is not None, "Expected an auto-generated id"
        assert result.name == "Income:Freelance"
        assert result.currency == "COP"
        assert result.depth == 1
        assert result.kind == "Income"
        assert result.is_archived is False
        # Verify row exists in DB
        row = connection.execute(
            text("SELECT name, currency, depth, kind, is_archived FROM accounts WHERE id = :id"),
            {"id": result.id},
        ).fetchone()
        assert row is not None
        assert row[0] == "Income:Freelance"

    def test_create_account_with_parent(self, connection: Connection) -> None:
        """Create an account referencing an existing parent by name lookup."""
        # Look up parent first (Expenses:Food:Groceries has id from starter chart)
        parent = connection.execute(
            text("SELECT id FROM accounts WHERE name = 'Expenses:Food:Groceries'"),
        ).fetchone()
        assert parent is not None, "Starter account should exist"
        child = Account(
            name="Expenses:Food:Produce",
            currency="COP",
            depth=2,
            kind="Expenses",
            parent_id=parent[0],
        )
        result = create_account(connection, child)
        assert result.id is not None
        assert result.parent_id == parent[0]

    def test_create_account_parent_must_exist(self, connection: Connection) -> None:
        """Non-existent parent_id raises AccountNotFoundError."""
        acct = Account(
            name="Expenses:Food:Produce",
            currency="COP",
            depth=2,
            kind="Expenses",
            parent_id=999,
        )
        with pytest.raises(AccountNotFoundError, match="Parent account id=999 not found"):
            create_account(connection, acct)

    def test_create_account_duplicate_name(self, connection: Connection) -> None:
        """Duplicate account name raises ValidationError."""
        acct = Account(name="Income:Salary", currency="COP", depth=1, kind="Income")
        with pytest.raises(ValidationError, match="Account 'Income:Salary' already exists"):
            create_account(connection, acct)

    def test_create_account_invalid_name(self, connection: Connection) -> None:
        """Account name failing regex raises InvalidAccountName.

        The Account model itself accepts any non-empty name, so the
        repository must validate the name format before inserting.
        """
        acct = Account(name="assets:checking", currency="COP", depth=1, kind="Assets")
        with pytest.raises(InvalidAccountName):
            create_account(connection, acct)

    def test_create_account_returns_fresh_account(self, connection: Connection) -> None:
        """Returned Account has only the new id — not mutated from input."""
        acct = Account(name="Expenses:Utilities", currency="COP", depth=1, kind="Expenses")
        result = create_account(connection, acct)
        assert acct.id is None  # original unchanged
        assert result.id is not None  # returned has id
        assert result.name == acct.name


@pytest.mark.integration
class TestGetAccountByName:
    """T-2.7: repository.get_account_by_name(conn, name) -> Account | None."""

    def test_found(self, connection: Connection) -> None:
        """Look up an existing starter account by name."""
        acct = get_account_by_name(connection, "Assets:Checking")
        assert acct is not None
        assert acct.name == "Assets:Checking"
        assert acct.kind == "Assets"
        assert acct.currency == "COP"

    def test_not_found(self, connection: Connection) -> None:
        """Non-existent name returns None."""
        acct = get_account_by_name(connection, "Assets:NonExistent")
        assert acct is None

    def test_case_insensitive(self, connection: Connection) -> None:
        """Name lookup is case-insensitive (COLLATE NOCASE)."""
        acct = get_account_by_name(connection, "assets:checking")
        assert acct is not None
        assert acct.name == "Assets:Checking"


@pytest.mark.integration
class TestGetAccountById:
    """T-2.8: repository.get_account_by_id(conn, id) -> Account | None."""

    def test_found(self, connection: Connection) -> None:
        """Look up an existing starter account by id."""
        # Get the id of Assets:Checking first
        row = connection.execute(
            text("SELECT id FROM accounts WHERE name = 'Assets:Checking'"),
        ).fetchone()
        assert row is not None
        acct = get_account_by_id(connection, row[0])
        assert acct is not None
        assert acct.name == "Assets:Checking"
        assert acct.id == row[0]

    def test_not_found(self, connection: Connection) -> None:
        """Non-existent id returns None."""
        acct = get_account_by_id(connection, 9999)
        assert acct is None


@pytest.mark.integration
class TestListAccounts:
    """T-2.9: repository.list_accounts(conn) -> Sequence[Account]."""

    def test_returns_all_starter_accounts(self, connection: Connection) -> None:
        """list_accounts returns all 11 starter accounts."""
        accounts = list_accounts(connection)
        assert len(accounts) == 11
        assert all(isinstance(a, Account) for a in accounts)

    def test_ordering_by_name(self, connection: Connection) -> None:
        """Accounts are ordered alphabetically by name."""
        accounts = list_accounts(connection)
        names = [a.name for a in accounts]
        assert names == sorted(names), "Expected alphabetical order"

    def test_includes_new_account(self, connection: Connection) -> None:
        """After creating a new account, list includes it."""
        acct = Account(name="Assets:NewTest", currency="COP", depth=1, kind="Assets")
        create_account(connection, acct)
        accounts = list_accounts(connection)
        assert len(accounts) == 12
        assert any(a.name == "Assets:NewTest" for a in accounts)


@pytest.mark.integration
class TestAccountHasPostings:
    """T-2.10: repository.account_has_postings(conn, account_id) -> bool."""

    def test_false_for_fresh_account(self, connection: Connection) -> None:
        """Account with no postings returns False."""
        acct_id = connection.execute(
            text("SELECT id FROM accounts WHERE name = 'Assets:Checking'"),
        ).scalar()
        assert acct_id is not None
        assert account_has_postings(connection, acct_id) is False

    def test_false_for_nonexistent_account(self, connection: Connection) -> None:
        """Non-existent account id returns False."""
        assert account_has_postings(connection, 9999) is False

    def test_true_after_adding_posting(self, connection: Connection) -> None:
        """Account with a posting returns True."""
        # Get two accounts and create a transaction with a posting
        checking_id = connection.execute(
            text("SELECT id FROM accounts WHERE name = 'Assets:Checking'"),
        ).scalar()
        salary_id = connection.execute(
            text("SELECT id FROM accounts WHERE name = 'Income:Salary'"),
        ).scalar()
        assert checking_id is not None
        assert salary_id is not None

        # Insert a transaction
        tx_result = connection.execute(
            text("INSERT INTO transactions (date, description) VALUES ('2026-07-17', 'Salary deposit') RETURNING id"),
        ).scalar()

        # Insert a posting for Assets:Checking
        connection.execute(
            text("INSERT INTO postings (transaction_id, account_id, amount, currency) VALUES (:tid, :aid, :amt, :cur)"),
            {"tid": tx_result, "aid": checking_id, "amt": "5000000", "cur": "COP"},
        )

        assert account_has_postings(connection, checking_id) is True
        # Salary account should still have no postings
        assert account_has_postings(connection, salary_id) is False
