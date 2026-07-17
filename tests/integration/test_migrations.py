"""Integration tests for alembic migrations — schema + starter chart."""

import pytest
from alembic.command import downgrade, upgrade
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.pool import StaticPool

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_config(connection: Connection) -> Config:
    """Build an Alembic config that uses the given *connection*."""
    cfg = Config("alembic.ini")
    cfg.attributes["connection"] = connection
    return cfg


def _count_tables(conn: Connection) -> int:
    """Return the number of user tables in the database."""
    row = conn.execute(
        text(
            "SELECT count(*) FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'alembic_%' AND name != 'sqlite_sequence'"
        )
    ).scalar()
    return row or 0


def _table_exists(conn: Connection, name: str) -> bool:
    """Return True if *name* exists as a table."""
    row = conn.execute(
        text("SELECT count(*) FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": name},
    ).scalar()
    return bool(row)


def _column_type(conn: Connection, table: str, column: str) -> str | None:
    """Return the SQL type of *column* in *table*, or None."""
    row = conn.execute(
        text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table},
    ).scalar()
    if row is None:
        return None
    # Parse the CREATE TABLE statement to find the column type
    for part in row.split(","):
        part = part.strip().strip(")").strip()
        if part.upper().startswith(column.upper()):
            tokens = part.split()
            if len(tokens) >= 2:
                return tokens[1].upper()
    return None


# ── T-1.5: 0001_initial_schema.py — 4 tables, TEXT money ────────────────────


@pytest.mark.integration
class TestMigrationSchema:
    """Verify the initial migration creates the correct schema."""

    @pytest.fixture(autouse=True)
    def _fresh_db(self) -> None:
        """Each test gets a fresh in-memory database."""
        self.engine = Engine  # placeholder; real setup in each test
        self.conn = None

    def _engine(self) -> Engine:
        from sqlalchemy import create_engine
        return create_engine("sqlite://", poolclass=StaticPool)

    def test_upgrade_creates_four_tables(self) -> None:
        """After upgrade(head), 4 user tables exist."""
        engine = self._engine()
        with engine.connect() as conn:
            cfg = _make_config(conn)
            upgrade(cfg, "head")
            assert _count_tables(conn) == 4, "Expected 4 tables (accounts, transactions, postings, rates)"

    def test_accounts_table_columns(self) -> None:
        """accounts table has the expected columns."""
        engine = self._engine()
        with engine.connect() as conn:
            cfg = _make_config(conn)
            upgrade(cfg, "head")
            assert _table_exists(conn, "accounts")
            cols = [
                row[1]
                for row in conn.execute(
                    text("PRAGMA table_info(accounts)")
                ).fetchall()
            ]
            assert "id" in cols
            assert "name" in cols
            assert "parent_id" in cols
            assert "currency" in cols
            assert "depth" in cols
            assert "kind" in cols
            assert "is_archived" in cols
            assert "created_at" in cols

    def test_transactions_table_columns(self) -> None:
        """transactions table has the expected columns."""
        engine = self._engine()
        with engine.connect() as conn:
            cfg = _make_config(conn)
            upgrade(cfg, "head")
            assert _table_exists(conn, "transactions")
            cols = [
                row[1]
                for row in conn.execute(
                    text("PRAGMA table_info(transactions)")
                ).fetchall()
            ]
            assert "id" in cols
            assert "date" in cols
            assert "description" in cols
            assert "created_at" in cols

    def test_postings_table_columns(self) -> None:
        """postings table has the expected columns."""
        engine = self._engine()
        with engine.connect() as conn:
            cfg = _make_config(conn)
            upgrade(cfg, "head")
            assert _table_exists(conn, "postings")
            cols = [
                row[1]
                for row in conn.execute(
                    text("PRAGMA table_info(postings)")
                ).fetchall()
            ]
            assert "id" in cols
            assert "transaction_id" in cols
            assert "account_id" in cols
            assert "amount" in cols
            assert "currency" in cols

    def test_postings_amount_is_text(self) -> None:
        """postings.amount column type is TEXT (not NUMERIC/REAL)."""
        engine = self._engine()
        with engine.connect() as conn:
            cfg = _make_config(conn)
            upgrade(cfg, "head")
            col_type = _column_type(conn, "postings", "amount")
            assert col_type == "TEXT", f"Expected TEXT, got {col_type}"

    def test_rates_table_columns(self) -> None:
        """rates table has the expected columns."""
        engine = self._engine()
        with engine.connect() as conn:
            cfg = _make_config(conn)
            upgrade(cfg, "head")
            assert _table_exists(conn, "rates")
            cols = [
                row[1]
                for row in conn.execute(
                    text("PRAGMA table_info(rates)")
                ).fetchall()
            ]
            assert "id" in cols
            assert "base_currency" in cols
            assert "target_currency" in cols
            assert "rate" in cols
            assert "date" in cols
            assert "source" in cols

    def test_downgrade_drops_tables(self) -> None:
        """After downgrade(base), 0 user tables remain."""
        engine = self._engine()
        with engine.connect() as conn:
            cfg = _make_config(conn)
            upgrade(cfg, "head")
            assert _count_tables(conn) == 4
            downgrade(cfg, "base")
            assert _count_tables(conn) == 0, "All user tables should be dropped"


# ── T-1.6: Starter chart (11 accounts) ──────────────────────────────────────


@pytest.mark.integration
class TestStarterChart:
    """Verify the 11-account starter chart is seeded."""

    def test_starter_chart_has_11_accounts(self) -> None:
        """After upgrade(head), 11 accounts exist."""
        engine = create_engine("sqlite://", poolclass=StaticPool)
        with engine.connect() as conn:
            cfg = _make_config(conn)
            upgrade(cfg, "head")
            count = conn.execute(text("SELECT count(*) FROM accounts")).scalar()
            assert count == 11, f"Expected 11 starter accounts, got {count}"

    def test_equity_opening_balances_present(self) -> None:
        """Equity:OpeningBalances is in the starter chart."""
        engine = create_engine("sqlite://", poolclass=StaticPool)
        with engine.connect() as conn:
            cfg = _make_config(conn)
            upgrade(cfg, "head")
            row = conn.execute(
                text("SELECT name FROM accounts WHERE name = :name"),
                {"name": "Equity:OpeningBalances"},
            ).fetchone()
            assert row is not None, "Equity:OpeningBalances should exist"
            assert row[0] == "Equity:OpeningBalances"

    def test_starter_chart_all_cop(self) -> None:
        """All 11 starter accounts use COP currency."""
        engine = create_engine("sqlite://", poolclass=StaticPool)
        with engine.connect() as conn:
            cfg = _make_config(conn)
            upgrade(cfg, "head")
            rows = conn.execute(
                text("SELECT DISTINCT currency FROM accounts")
            ).fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "COP"


# ── T-1.16: Migration smoke test ────────────────────────────────────────────


@pytest.mark.integration
class TestMigrationSmoke:
    """Verify upgrade/downgrade/upgrade idempotency."""

    def test_upgrade_downgrade_upgrade_idempotent(self) -> None:
        """upgrade head → downgrade base → upgrade head succeeds."""
        engine = create_engine("sqlite://", poolclass=StaticPool)
        with engine.connect() as conn:
            cfg = _make_config(conn)
            upgrade(cfg, "head")
            downgrade(cfg, "base")
            upgrade(cfg, "head")  # second upgrade must succeed
            assert _count_tables(conn) == 4

    def test_upgrade_downgrade_upgrade_starter_chart_persists(self) -> None:
        """After triple cycle, 11 accounts still present."""
        engine = create_engine("sqlite://", poolclass=StaticPool)
        with engine.connect() as conn:
            cfg = _make_config(conn)
            upgrade(cfg, "head")
            downgrade(cfg, "base")
            upgrade(cfg, "head")
            count = conn.execute(text("SELECT count(*) FROM accounts")).scalar()
            assert count == 11
