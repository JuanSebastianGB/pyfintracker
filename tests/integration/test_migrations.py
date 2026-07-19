"""Integration tests for alembic migrations — schema + starter chart."""

from pathlib import Path

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
            assert _count_tables(conn) == 4, (
                "Expected 4 tables (accounts, transactions, postings, rates)"
            )

    def test_accounts_table_columns(self) -> None:
        """accounts table has the expected columns."""
        engine = self._engine()
        with engine.connect() as conn:
            cfg = _make_config(conn)
            upgrade(cfg, "head")
            assert _table_exists(conn, "accounts")
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(accounts)")).fetchall()]
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
                row[1] for row in conn.execute(text("PRAGMA table_info(transactions)")).fetchall()
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
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(postings)")).fetchall()]
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
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(rates)")).fetchall()]
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
            rows = conn.execute(text("SELECT DISTINCT currency FROM accounts")).fetchall()
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

    def test_migrations_smoke_idempotent_file_db(self, tmp_path: Path) -> None:
        """Triple cycle on file-based DB: upgrade→downgrade→upgrade produces same schema."""
        from pyfintracker.db import make_engine

        db_path = tmp_path / "test_fin.db"
        engine = make_engine(f"sqlite:///{db_path}")

        with engine.connect() as conn:
            cfg = _make_config(conn)
            upgrade(cfg, "head")
            assert _count_tables(conn) == 4, "Expected 4 tables after first upgrade"

        with engine.connect() as conn:
            cfg = _make_config(conn)
            downgrade(cfg, "base")
            assert _count_tables(conn) == 0, "Expected 0 tables after downgrade"

        with engine.connect() as conn:
            cfg = _make_config(conn)
            upgrade(cfg, "head")
            assert _count_tables(conn) == 4, "Expected 4 tables after re-upgrade"

        # Verify starter chart is present
        with engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) FROM accounts")).scalar()
            assert count == 11, f"Expected 11 accounts after re-upgrade, got {count}"


# ── T-A.5: 0002_multi_currency_schema.py — transactions.currency + rates.fetched_at + accounts CHECK widen ──


def _apply_0002(conn: Connection) -> None:
    """Apply 0002 migration on top of 0001 head."""
    cfg = _make_config(conn)
    upgrade(cfg, "0002")


def _downgrade_0001(conn: Connection) -> None:
    """Downgrade from 0002 back to 0001."""
    cfg = _make_config(conn)
    downgrade(cfg, "0001")


def _column_names(conn: Connection, table: str) -> list[str]:
    """Return list of column names for a table."""
    return [row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()]


@pytest.mark.integration
class TestMigration0002:
    """0002 migration: transactions.currency, rates.fetched_at, accounts CHECK."""

    def test_migration_0002_roundtrip(self) -> None:
        """upgrade→downgrade→upgrade idempotent for 0002."""
        engine = create_engine("sqlite://", poolclass=StaticPool)
        with engine.connect() as conn:
            # Start at 0001
            cfg_0001 = _make_config(conn)
            upgrade(cfg_0001, "0001")

            # Upgrade to 0002
            _apply_0002(conn)

            # Verify columns exist after upgrade
            txn_cols = _column_names(conn, "transactions")
            assert "currency" in txn_cols

            rates_cols = _column_names(conn, "rates")
            assert "fetched_at" in rates_cols

            # Downgrade to 0001
            _downgrade_0001(conn)

            # Verify columns removed
            txn_cols = _column_names(conn, "transactions")
            assert "currency" not in txn_cols

            rates_cols = _column_names(conn, "rates")
            assert "fetched_at" not in rates_cols

            # Re-upgrade to 0002
            _apply_0002(conn)

            # Verify columns back
            txn_cols = _column_names(conn, "transactions")
            assert "currency" in txn_cols

            rates_cols = _column_names(conn, "rates")
            assert "fetched_at" in rates_cols

    def test_accounts_check_widened(self) -> None:
        """Wider CHECK allows new currencies after 0002."""
        engine = create_engine("sqlite://", poolclass=StaticPool)
        with engine.connect() as conn:
            cfg = _make_config(conn)
            upgrade(cfg, "0001")

            # CAD should fail before 0002
            with pytest.raises(Exception, match="CHECK"):
                conn.execute(
                    text(
                        "INSERT INTO accounts (name, currency, depth, kind) "
                        "VALUES (:name, :currency, :depth, :kind)"
                    ),
                    {"name": "Expenses:Tesla", "currency": "CAD", "depth": 1, "kind": "Expenses"},
                )

            _apply_0002(conn)

            # CAD should work after 0002
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) "
                    "VALUES (:name, :currency, :depth, :kind)"
                ),
                {"name": "Expenses:Tesla", "currency": "CAD", "depth": 1, "kind": "Expenses"},
            )

    def test_idx_rates_lookup_exists(self) -> None:
        """idx_rates_lookup index exists after 0002 upgrade."""
        engine = create_engine("sqlite://", poolclass=StaticPool)
        with engine.connect() as conn:
            cfg = _make_config(conn)
            upgrade(cfg, "0001")
            _apply_0002(conn)

            rows = conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_rates_lookup'"
                )
            ).fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "idx_rates_lookup"


# ── T-E.9: 0002 idempotent roundtrip with Wave 1 data ─────────────────────────


@pytest.mark.integration
class TestMigration0002IdempotentWithData:
    """0001 → 0002 → 0001 → 0002 roundtrip preserves Wave 1 single-currency data.

    Seeds: 11 starter accounts (COP) + 5 postings on a single transaction.
    Runs: upgrade 0002 (with backfill) → downgrade 0001 → upgrade 0002 (with
    backfill again). Verifies after each leg that the schema AND the data
    are still consistent.
    """

    def _seed_wave1_data(self, conn: Connection) -> None:
        """Insert 5 postings on a single transaction.

        All amounts in COP (single-currency Wave 1 invariant). Uses the 0001
        schema (no transactions.currency column) — the column is added by 0002
        which then backfills it.
        """
        # Get the account IDs we need (starter chart is seeded by 0001)
        rows = conn.execute(
            text("SELECT id, name FROM accounts WHERE name IN (:n1, :n2, :n3, :n4, :n5)"),
            {
                "n1": "Assets:Cash",
                "n2": "Income:Salary",
                "n3": "Expenses:Food:Groceries",
                "n4": "Expenses:Food:Restaurants",
                "n5": "Expenses:Transport",
            },
        ).fetchall()
        ids = {name: id_ for id_, name in rows}
        assert len(ids) == 5, f"Expected 5 starter accounts, got {ids}"

        # Insert a transaction (0001 schema: no currency column)
        result = conn.execute(
            text(
                "INSERT INTO transactions (date, description) "
                "VALUES (:date, :desc) RETURNING id"
            ),
            {"date": "2026-01-15", "desc": "Salary January"},
        )
        txn_id = result.scalar()
        assert txn_id is not None

        # 5 postings summing to zero (Wave 1 invariant)
        postings = [
            (ids["Income:Salary"], "-4000000", "COP"),
            (ids["Assets:Cash"], "3500000", "COP"),
            (ids["Expenses:Food:Groceries"], "300000", "COP"),
            (ids["Expenses:Food:Restaurants"], "100000", "COP"),
            (ids["Expenses:Transport"], "100000", "COP"),
        ]
        # Sum: -4M + 3.5M + 300k + 100k + 100k = 0 ✓
        for account_id, amount, ccy in postings:
            conn.execute(
                text(
                    "INSERT INTO postings (transaction_id, account_id, amount, currency) "
                    "VALUES (:tid, :aid, :amt, :ccy)"
                ),
                {"tid": txn_id, "aid": account_id, "amt": amount, "ccy": ccy},
            )

    def _count_postings_for_txn(self, conn: Connection, txn_date: str) -> int:
        row = conn.execute(
            text(
                "SELECT count(*) FROM postings p "
                "JOIN transactions t ON p.transaction_id = t.id "
                "WHERE t.date = :d"
            ),
            {"d": txn_date},
        ).scalar()
        return row or 0

    def _transactions_currency_value(self, conn: Connection, txn_date: str) -> str | None:
        row = conn.execute(
            text("SELECT currency FROM transactions WHERE date = :d"),
            {"d": txn_date},
        ).fetchone()
        return row[0] if row else None

    def test_0002_idempotent_roundtrip_with_wave1_data(self) -> None:
        """Wave 1 data: 11 COP accounts + 5 postings survives full round-trip.

        upgrade 0002 → downgrade 0001 → upgrade 0002:
        - Schema resets and re-applies cleanly
        - 11 accounts still present (starter chart persists)
        - 5 postings still present (data preserved)
        - accounts.currency CHECK allows the 12-currency widen
        """
        engine = create_engine("sqlite://", poolclass=StaticPool)
        with engine.connect() as conn:
            # ── Leg 1: apply 0001 + seed Wave 1 data + upgrade to 0002 ──
            upgrade(_make_config(conn), "0001")
            self._seed_wave1_data(conn)
            conn.commit()

            _apply_0002(conn)
            # Verify after first upgrade to 0002
            assert _column_names(conn, "transactions") and "currency" in _column_names(
                conn, "transactions"
            )
            assert self._count_postings_for_txn(conn, "2026-01-15") == 5

            # ── Leg 2: downgrade to 0001 (drops transactions.currency) ──
            _downgrade_0001(conn)
            # transactions.currency should be gone, data still here
            assert "currency" not in _column_names(conn, "transactions")
            assert self._count_postings_for_txn(conn, "2026-01-15") == 5

            # ── Leg 3: re-upgrade to 0002 (re-adds transactions.currency,
            # backfills from dominant posting currency = COP) ──
            _apply_0002(conn)
            assert "currency" in _column_names(conn, "transactions")
            assert self._count_postings_for_txn(conn, "2026-01-15") == 5
            # Backfilled currency matches Wave 1 invariant: COP
            assert self._transactions_currency_value(conn, "2026-01-15") == "COP"

            # ── Side-check: accounts.currency CHECK widened to 12 currencies ──
            # Insert CAD account (would fail under 0001's narrow CHECK)
            conn.execute(
                text(
                    "INSERT INTO accounts (name, currency, depth, kind) "
                    "VALUES (:name, :currency, :depth, :kind)"
                ),
                {
                    "name": "Expenses:Intl:Shopping",
                    "currency": "CAD",
                    "depth": 2,
                    "kind": "Expenses",
                },
            )
            conn.commit()
            # Total accounts: 11 starter + 1 CAD = 12
            total = conn.execute(text("SELECT count(*) FROM accounts")).scalar()
            assert total == 12
