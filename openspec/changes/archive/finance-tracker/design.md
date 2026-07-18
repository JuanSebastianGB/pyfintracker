---
type: design
id: finance-tracker-design
status: draft
tags: [python, cli, finance, double-entry, sqlite, mvp, design]
parent_proposal: finance-tracker
parent_spec: finance-tracker-spec
parent_tasks: null
---

# Design — finance-tracker (Wave 1 MVP Estricto)

Source of truth: engram obs `anvil/finance-tracker/design`. This file mirrors for downstream consumption.

## 1. Module Map

8 modules per spec B1 (frozen dataclass domain, Pydantic envelopes, `pydantic-settings` config). All under `src/pyfintracker/`. `__init__.py` empty.

### `models.py` — frozen domain entities
- **Purpose**: Hold the four domain entities (Account, Transaction, Posting, Rate) as immutable dataclasses. No I/O. All amounts `Decimal`.
- **Public interface**:
  ```python
  @dataclass(frozen=True, slots=True)
  class Account:
      id: int | None           # None until persisted
      name: str                # canonical PascalCase
      currency: str            # ISO 4217 (3-letter)
      description: str         # default ""
      parent_id: int | None    # None = root
      parent_name: str | None  # populated on read; not persisted

      def to_row(self) -> dict[str, Any]: ...
      @classmethod
      def from_row(cls, row: Mapping[str, Any]) -> "Account": ...
      def depth(self) -> int: ...  # counts ":" segments

  @dataclass(frozen=True, slots=True)
  class Transaction:
      id: int | None
      date: date               # ISO date, no tz
      description: str         # max 256
      currency: str            # txn-level currency (D6)

      def to_row(self) -> dict[str, Any]: ...

  @dataclass(frozen=True, slots=True)
  class Posting:
      id: int | None
      transaction_id: int | None
      account_id: int
      amount: Decimal          # signed, DecimalAsText-serialized

      def to_row(self) -> dict[str, Any]: ...

  @dataclass(frozen=True, slots=True)
  class Rate:
      id: int | None
      date: date
      from_ccy: str
      to_ccy: str
      rate: Decimal
      # Wave 2 will use; defined now to lock schema.
  ```
  No `__post_init__` validation here — pure data shape. Validation lives in `validation.py`.
- **Deps**: stdlib only (`dataclasses`, `datetime`, `decimal`).
- **Helpers**: `_canonicalize_name(s: str) -> str` (PascalCase per segment; raise `ValueError` on empty).
- **Tests**: `tests/unit/test_models.py` (constructor + to/from_row roundtrip).

### `db.py` — engine + session factory
- **Purpose**: Centralize SQLAlchemy engine creation, PRAGMA setup, `:memory:` test helper.
- **Public interface**:
  ```python
  def make_engine(url: str, *, echo: bool = False, apply_pragmas: bool = True) -> Engine: ...
  def get_session(engine: Engine) -> Iterator[Connection]: ...   # `with engine.begin()` wrapper
  def make_test_engine() -> Engine: ...   # :memory: + StaticPool + pragmas
  def apply_pragmas(conn: Connection) -> None: ...   # WAL + foreign_keys
  ```
- **Deps**: stdlib + `sqlalchemy`. PRAGMAs: `journal_mode=WAL` (D1), `foreign_keys=ON`.
- **Internal**: `_register_engine_event_listeners(engine)` sets PRAGMA on `connect` event so WAL applies even on first connection of a fresh DB.
- **Tests**: `tests/integration/test_db.py` (engine creation, WAL applied, `:memory:` shared across connections).

### `config.py` — pydantic-settings loader
- **Purpose**: Load settings with XDG file < env < flag precedence (B1). One `Settings` model.
- **Public interface**:
  ```python
  class Settings(BaseSettings):
      db_path: Path                       # ~/.local/share/fin/fin.db default
      default_currency: str = "COP"       # ISO 4217
      journal_mode: Literal["WAL", "DELETE"] = "WAL"
      snapshot_width: int = 120
      account_name_max_length: int = 64
      description_max_length: int = 256
      no_color: bool = False

      model_config = SettingsConfigDict(
          env_prefix="FIN_",
          toml_file=xdg_config_path(),  # computed property
          extra="ignore",
      )

      def source_of(self, field: str) -> Literal["default","file","env","flag"]: ...

  def load_settings(cli_overrides: dict[str, Any] | None = None) -> Settings: ...
  ```
- **Deps**: `pydantic`, `pydantic_settings`, stdlib.
- **Helpers**: `_xdg_config_path() -> Path` (respects `XDG_CONFIG_HOME`).
- **Precedence**: defaults < TOML < `FIN_*` env < `cli_overrides` (last wins).
- **Tests**: `tests/unit/test_config.py` (precedence matrix), `tests/integration/test_config_toml.py` (real file).

### `validation.py` — invariant validators
- **Purpose**: Pure validators for accounts, amounts, postings, transactions. Returns canonical values or raises typed `FinanceError` subclasses.
- **Public interface**:
  ```python
  PER_CURRENCY_DECIMALS: Final[dict[str, int]] = {"COP": 0, "JPY": 0, "USD": 2, "EUR": 2, "GBP": 2, ...}

  def validate_account_name(name: str) -> str: ...           # returns canonical
  def validate_currency(code: str) -> str: ...                # 3-letter ISO, uppercased
  def validate_date(s: str | date) -> date: ...               # strict ISO YYYY-MM-DD
  def validate_amount(value: Any, currency: str) -> Decimal: ...   # rejects float/NaN/Inf, quantizes
  def validate_posting(posting: Posting, account: Account) -> None: ...   # currency coherence (D6)
  def validate_transaction(tx: Transaction, postings: Sequence[Posting]) -> None: ...  # contract b order
  def quantize_for_currency(amount: Decimal, currency: str) -> Decimal: ...  # ROUND_HALF_UP
  def normalize_currency_decimals() -> dict[str, int]: ...    # for test introspection
  ```
- **Deps**: stdlib + `decimal` + `pydantic` (for `Money` type below).
- **Pydantic envelope**:
  ```python
  Money = Annotated[Decimal, BeforeValidator(_coerce_money), PlainSerializer(_serialize_money)]
  ```
  Validator `_coerce_money(v)` rejects `float` with `TypeError`, accepts `str`/`int`/`Decimal`, quantizes per currency.
- **Tests**: `tests/unit/test_validation.py` (per-validator unit), `tests/property/test_validation_props.py` (hypothesis fuzzing).

### `repository.py` — data access (SQLAlchemy 2.0 Core)
- **Purpose**: All SQL lives here. Atomic multi-row writes via `with engine.begin()`. Accepts frozen dataclasses, returns dataclasses.
- **Public interface** (all `Connection`-first):
  ```python
  # accounts
  def upsert_account(conn: Connection, *, name: str, currency: str, parent_name: str | None = None,
                     description: str = "") -> Account: ...
  def get_account_by_name(conn: Connection, name: str) -> Account | None: ...
  def get_account_by_id(conn: Connection, account_id: int) -> Account | None: ...
  def list_accounts(conn: Connection, *, root: str | None = None) -> Sequence[Account]: ...
  def account_has_postings(conn: Connection, account_id: int) -> bool: ...

  # transactions
  def create_transaction_with_postings(
      conn: Connection, tx: Transaction, postings: Sequence[Posting],
  ) -> int: ...   # returns new txn id; atomic

  # reads
  def get_postings_by_account(
      conn: Connection, account_id: int, *, date_from: date | None = None,
      date_to: date | None = None,
  ) -> Sequence[Posting]: ...

  def get_balance(conn: Connection, account_id: int, *, as_of: date | None = None) -> Decimal: ...

  def get_net_worth(conn: Connection, *, as_of: date | None = None,
                    currency: str = "COP") -> Decimal: ...
  ```
- **Deps**: stdlib + `sqlalchemy` + project (`models`, `validation`).
- **Atomicity**: every multi-step write wraps in `with engine.begin():` externally or `with conn.begin():` internally when called from `cli` layer.
- **Idempotency**: `upsert_account` returns existing on duplicate (D8).
- **Tests**: `tests/integration/test_repository.py` (CliRunner + raw `engine`), `tests/property/test_repository_props.py`.

### `reports.py` — monthly + balance aggregation + rendering
- **Purpose**: Pure aggregation (returns Pydantic `MonthlyReport` / `BalanceReport`) + Rich rendering. No DB calls inside aggregation functions — caller passes data.
- **Public interface**:
  ```python
  class MonthlyLine(BaseModel):
      account_name: str
      total: Decimal
      per_day: list[Decimal]   # length = days_in_month, zero-padded
      is_rollup: bool

  class MonthlyReport(BaseModel):
      year: int; month: int
      income: list[MonthlyLine]; expenses: list[MonthlyLine]
      net: Decimal; currency: str; rollup: bool

  class BalanceLine(BaseModel):
      account_name: str; root: str; balance: Decimal; currency: str

  class BalanceReport(BaseModel):
      as_of: date | None; lines: list[BalanceLine]; net_worth: Decimal; currency: str

  def compute_monthly_report(
      postings: Sequence[Posting], accounts: Mapping[int, Account],
      *, year: int, month: int, rollup: bool = True,
  ) -> MonthlyReport: ...

  def compute_balance(
      postings: Sequence[Posting], accounts: Mapping[int, Account],
      *, as_of: date | None = None, currency: str = "COP",
  ) -> BalanceReport: ...

  def render_monthly_report(report: MonthlyReport, console: Console) -> None: ...
  def render_balance(report: BalanceReport, console: Console) -> None: ...
  ```
- **Deps**: stdlib + `pydantic` + `rich`.
- **Tests**: `tests/unit/test_reports.py` (rollup, ordering, sparkline padding), `tests/snapshots/test_reports_snap.py` (syrupy), `tests/integration/test_reports_cli.py` (CliRunner).

### `cli.py` — Typer app
- **Purpose**: User surface. Maps CLI flags to repository calls + report rendering. Exit codes per B2.
- **Public interface**:
  ```python
  app: typer.Typer
  # sub-apps
  account_app: typer.Typer
  report_app: typer.Typer
  config_app: typer.Typer
  migrate_app: typer.Typer

  @app.callback()
  def main(ctx: typer.Context, no_color: bool = False) -> None: ...

  @app.command()
  def init(force: bool = typer.Option(False, "--force", help="DESTRUCTIVE: drop + recreate")) -> None: ...

  @app.command()
  def version() -> None: ...

  # account_app
  @account_app.command("new")
  def account_new(
      name: str,
      currency: str = typer.Option("COP"),
      parent: str | None = typer.Option(None),
      description: str = typer.Option(""),
      initial: Decimal | None = typer.Option(None),
      initial_currency: str | None = typer.Option(None),
      date: str = typer.Option("", help="ISO YYYY-MM-DD, default today"),
  ) -> None: ...

  @account_app.command("list")
  def account_list(root: str | None = typer.Option(None), currency: str | None = typer.Option(None)) -> None: ...

  # add
  @app.command()
  def add(
      date: str = "",
      description: str = "",
      amount: Decimal | None = None,
      currency: str = "",
      from_account: str | None = typer.Option(None, "--from"),
      to_account: str | None = typer.Option(None, "--to"),
  ) -> None: ...   # if --from/--to: flag mode; else REPL

  # report_app
  @report_app.command("month")
  def report_month(
      month: str = "",          # YYYY-MM, default current
      no_rollup: bool = typer.Option(False, "--no-rollup"),
  ) -> None: ...

  @app.command()
  def balance(as_of: str = "") -> None: ...

  # config_app
  @config_app.command("show")
  def config_show() -> None: ...

  # migrate_app
  @migrate_app.command("up")
  def migrate_up() -> None: ...
  @migrate_app.command("down")
  def migrate_down() -> None: ...
  @migrate_app.command("status")
  def migrate_status() -> None: ...
  ```
- **Deps**: stdlib + `typer` + `rich` + project.
- **REPL helper**: `repl_add_postings(console: Console, prompt_fn: Callable[[str], str] = typer.prompt) -> Transaction` — injectable for tests.
- **Exit codes (B2)**: 0=ok · 1=`ValidationError`/`InvariantError`/`AccountNotFoundError` · 2=runtime (REPL non-TTY) · 3=`NotInitializedError`/`ConfigError` · 130=abort.
- **Tests**: `tests/integration/test_cli_*.py` per command (CliRunner), `tests/unit/test_repl.py` (prompt_fn injection).

## 2. Data Model — `models.py` (exact)

All 4 entities are `@dataclass(frozen=True, slots=True)`. **No validation in `__post_init__`**; pure data shapes only. **Validation lives in `validation.py`** for testability and layering (per B1).

Field table:

| Entity | Field | Type | Default | Notes |
|---|---|---|---|---|
| `Account` | `id` | `int \| None` | `None` | assigned on persist |
| | `name` | `str` | — | canonical PascalCase, regex-validated upstream |
| | `currency` | `str` | — | ISO 4217, immutable |
| | `description` | `str` | `""` | ≤256 chars |
| | `parent_id` | `int \| None` | `None` | root has no parent |
| | `parent_name` | `str \| None` | `None` | populated on read; not persisted |
| `Transaction` | `id` | `int \| None` | `None` | auto-increment |
| | `date` | `date` | — | strict ISO, no tz |
| | `description` | `str` | `""` | ≤256 chars |
| | `currency` | `str` | — | txn-level (D6) |
| `Posting` | `id` | `int \| None` | `None` | |
| | `transaction_id` | `int \| None` | `None` | set inside save txn |
| | `account_id` | `int` | — | FK to accounts |
| | `amount` | `Decimal` | — | `DecimalAsText` roundtrip |
| `Rate` | `id` | `int \| None` | `None` | |
| | `date` | `date` | — | |
| | `from_ccy`, `to_ccy` | `str` | — | ISO 4217 |
| | `rate` | `Decimal` | — | Wave 2; schema lives now |

`__hash__`: auto (frozen dataclass). Ordering: only via natural `id`. `to_row()`/`from_row()` roundtrip exactly for all fields.

## 3. SQLAlchemy Schema (first migration, HAND-WRITTEN)

### Rationale (per spec R1)

Alembic autogenerate reads the Python-side `Type` declaration to emit SQL. If we declare columns as `sqlalchemy.Numeric(...)`, autogenerate emits `NUMERIC(precision, scale)` which SQLite stores internally as REAL → precision loss. **First migration is hand-written** to declare money columns as `TEXT` and bind them to the `DecimalAsText` `TypeDecorator`. Subsequent migrations may use autogenerate **iff they don't touch money columns**; a pre-commit guard enforces.

### DDL — `migrations/versions/0001_initial_schema.py`

```sql
-- accounts
CREATE TABLE accounts (
    id          INTEGER       PRIMARY KEY AUTOINCREMENT,
    name        VARCHAR(64)   NOT NULL UNIQUE COLLATE NOCASE,  -- case-insensitive uniqueness on canonical
    currency    VARCHAR(3)    NOT NULL,
    description VARCHAR(256)  NOT NULL DEFAULT '',
    parent_id   INTEGER       REFERENCES accounts(id) ON DELETE RESTRICT,
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_accounts_parent ON accounts(parent_id);

-- transactions
CREATE TABLE transactions (
    id          INTEGER       PRIMARY KEY AUTOINCREMENT,
    date        DATE          NOT NULL,
    description VARCHAR(256)  NOT NULL DEFAULT '',
    currency    VARCHAR(3)    NOT NULL,
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_transactions_date ON transactions(date);

-- postings
CREATE TABLE postings (
    id              INTEGER       PRIMARY KEY AUTOINCREMENT,
    transaction_id  INTEGER       NOT NULL REFERENCES transactions(id) ON DELETE RESTRICT,
    account_id      INTEGER       NOT NULL REFERENCES accounts(id)     ON DELETE RESTRICT,
    amount          TEXT          NOT NULL,   -- DecimalAsText (NEVER NUMERIC; SQLite would coerce to REAL)
    CHECK (amount <> '0')                                       -- no zero-amount postings (contract b)
);
CREATE INDEX idx_postings_account        ON postings(account_id);
CREATE INDEX idx_postings_account_date   ON postings(account_id, transaction_id);
CREATE INDEX idx_postings_transaction    ON postings(transaction_id);

-- rates (schema only, no Wave 1 writes)
CREATE TABLE rates (
    id          INTEGER       PRIMARY KEY AUTOINCREMENT,
    date        DATE          NOT NULL,
    from_ccy    VARCHAR(3)    NOT NULL,
    to_ccy      VARCHAR(3)    NOT NULL,
    rate        TEXT          NOT NULL,   -- DecimalAsText
    UNIQUE (date, from_ccy, to_ccy)
);
```

**Constraints chosen**: `ON DELETE RESTRICT` everywhere (no cascades in Wave 1; spec C contract b + D8). `UNIQUE COLLATE NOCASE` on `accounts.name` gives case-insensitive lookup at DB level. `CHECK (amount <> '0')` is defence-in-depth for contract b rule 2.

### Starter chart — inline in `0001` (decision pinned)

The 11-account starter chart (proposal listing) is inserted via raw SQL in the SAME migration file's `data_migration()` step. **Decision**: single source of truth for schema + seed. Separate migration (0002) was rejected — extra noise, no reversible benefit (chart creation is idempotent via `upsert_account`).

**Starter chart (11 accounts)**: `Assets:Checking`, `Assets:Savings`, `Assets:Cash`, `Liabilities:CreditCard`, `Income:Salary`, `Expenses:Food:Groceries`, `Expenses:Food:Restaurants`, `Expenses:Rent`, `Expenses:Transport`, `Expenses:Subscriptions`, `Equity:OpeningBalances`. **Resolves proposal's "10" discrepancy**: includes `Equity:OpeningBalances` per spec B4. (Tracked as `open_question #1`.)

### `DecimalAsText` TypeDecorator

```python
class DecimalAsText(TypeDecorator):
    impl = Text
    cache_ok = True
    def process_bind_param(self, value, dialect): return None if value is None else str(value)
    def process_result_value(self, value, dialect): return None if value is None else Decimal(value)
```

Format pinned: **canonical string form of `Decimal`** — `'123.45'`, `'-50000'`, `'0'`. Period decimal, no thousands separator. (Resolves `open_question #2`.)

## 4. `validation.py` — Validators + Exception Tree

### Validators

| Function | Returns | Raises | Notes |
|---|---|---|---|
| `validate_account_name(name)` | `str` (canonical) | `InvalidAccountName` | regex match, PascalCase normalize |
| `validate_currency(code)` | `str` (uppercase) | `InvalidCurrency` | 3-letter ISO |
| `validate_date(s \| date)` | `date` | `InvalidDate` | strict ISO `YYYY-MM-DD` |
| `validate_amount(value, currency)` | `Decimal` | `InvalidAmount` | rejects `float`, `NaN`, `Infinity`; quantizes |
| `validate_posting(posting, account)` | `None` | `CurrencyMismatchError` | contract b rule 3 (D6) |
| `validate_transaction(tx, postings)` | `None` | `InvariantError` family | order: count → zero → currency → sum (b rules 1–4) |
| `quantize_for_currency(amount, currency)` | `Decimal` | `UnknownCurrency` | uses `PER_CURRENCY_DECIMALS` |
| `_coerce_money(v)` (Pydantic validator) | `Decimal` | `TypeError` | Pydantic boundary (B1) |

### `PER_CURRENCY_DECIMALS`

```python
PER_CURRENCY_DECIMALS: Final[Mapping[str, int]] = MappingProxyType({
    "COP": 0, "JPY": 0, "KRW": 0,        # zero-decimal currencies
    "USD": 2, "EUR": 2, "GBP": 2, "CAD": 2, "AUD": 2, "CHF": 2,
})
```
Unknown currency → `UnknownCurrency` (exit 1).

### Exception tree (exit-code mapped, B2)

```
FinanceError(Exception)
├── ValidationError(FinanceError)              -> exit 1
│   ├── InvalidAccountName(ValidationError)
│   ├── InvalidCurrency(ValidationError)
│   ├── UnknownCurrency(ValidationError)
│   ├── InvalidDate(ValidationError)
│   ├── InvalidAmount(ValidationError)        # float / NaN / Inf
│   └── InvalidDescription(ValidationError)
├── InvariantError(FinanceError)               -> exit 1
│   ├── TooFewPostings(InvariantError)         # contract b rule 1
│   ├── ZeroAmountPosting(InvariantError)      # contract b rule 2
│   ├── CurrencyMismatchError(InvariantError)  # contract b rule 3 (also used by validate_posting)
│   └── UnbalancedTransaction(InvariantError)  # contract b rule 4
├── AccountNotFoundError(FinanceError)         -> exit 1
├── AlreadyInitializedError(FinanceError)      -> exit 1
├── NotInitializedError(FinanceError)          -> exit 3
├── ConfigError(FinanceError)                  -> exit 3
├── ReplRequiresTTYError(FinanceError)         -> exit 2
└── AlembicError(FinanceError)                 -> exit 2
```

CLI translates `FinanceError` → exit code via `err.code` attribute. Rich panel rendering: red panel for `ValidationError`/`InvariantError`, yellow for `ConfigError`/`NotInitializedError`, plain stderr for `ReplRequiresTTYError`.

## 5. `repository.py` — Operations + Atomicity

| Op | Signature | Atomicity | Notes |
|---|---|---|---|
| `upsert_account` | `(conn, *, name, currency, parent_name=None, description="") -> Account` | single insert; idempotent via `SELECT … WHERE name = ? COLLATE NOCASE` first | returns existing on duplicate (D8) |
| `get_account_by_name` | `(conn, name) -> Account \| None` | single SELECT | case-insensitive lookup |
| `get_account_by_id` | `(conn, id) -> Account \| None` | single SELECT | |
| `list_accounts` | `(conn, *, root=None) -> Sequence[Account]` | single SELECT | filter by root prefix |
| `account_has_postings` | `(conn, account_id) -> bool` | single SELECT COUNT | used by contract c rule 5 |
| `create_transaction_with_postings` | `(conn, tx, postings) -> int` | **single `with conn.begin():`** wrapping INSERT transactions + N INSERTs postings | returns new txn id |
| `get_postings_by_account` | `(conn, account_id, *, date_from=None, date_to=None) -> Sequence[Posting]` | single SELECT + JOIN transactions (for date filter) | |
| `get_balance` | `(conn, account_id, *, as_of=None) -> Decimal` | single SELECT SUM | if `as_of` None → all dates |
| `get_net_worth` | `(conn, *, as_of=None, currency="COP") -> Decimal` | single SELECT SUM over postings JOIN accounts | signs per account type |

**Atomicity rule**: every CLI command that does multi-row writes wraps the call in `with engine.begin():`. Repository functions accept an open `Connection` (from `engine.begin()`) so the boundary is at the CLI layer. Tests can pass either a fresh connection or one inside an outer `begin()`.

**Index alignment**: `idx_postings_account_date` covers `(account_id, transaction_id)` join + date filter for `get_balance` and `get_postings_by_account`. `idx_transactions_date` covers monthly report range scan.

## 6. `cli.py` — Commands + Exit Codes

Per command: signature, behavior, exit code path. B2 mapping in section 4.

| Command | Behavior | Exit code paths |
|---|---|---|
| `fin init [--force]` | check XDG data dir; if `fin.db` exists and not `--force` → exit 1 with `ConfigError`-like message (`AlreadyInitializedError`); else `make_engine` + `alembic.command.upgrade("head")` (library call, not subprocess) + seed chart (already in 0001) | 0=ok, 1=exists |
| `fin version` | print `pyfintracker X.Y.Z` from `pyproject.toml` | 0 |
| `fin account new <name> [--currency COP] [--parent NAME] [--description ""] [--initial AMT CCY] [--date YYYY-MM-DD]` | validate (contract a); if `--initial` → contract c flow (auto-create `Equity:OpeningBalances` if missing, build opening txn, atomic `with engine.begin():`) | 0=ok / created idempotent, 1=`ValidationError`, 1=`AlreadyInitializedError` |
| `fin account list [--root TYPE] [--currency CCY]` | query → render Rich `Table` grouped by root, sorted by depth then name | 0 |
| `fin add [DATE DESC AMOUNT CCY] [--from ACCT] [--to ACCT]` | if `--from` and `--to` present → flag mode (build 2-posting txn, validate, save); else → REPL via `repl_add_postings` | 0=ok, 1=`InvariantError`, 130=abort, 2=`ReplRequiresTTYError` |
| `fin report month [--month YYYY-MM] [--no-rollup]` | default month = current; reject malformed `--month`; compute `MonthlyReport` (D3 Console); render | 0, 1=`InvalidDate`, 1=`NotInitializedError` |
| `fin balance [--as-of YYYY-MM-DD]` | compute `BalanceReport` (postings sum + net worth); render two-column Rich table grouped by root, footer bold net worth | 0, 1, 3 |
| `fin config show` | print each field with `source_of(field)` annotation: `[default]`, `[file: ~/.config/fin/config.toml]`, `[env: FIN_X]`, `[flag: --x]` | 0 |
| `fin migrate up\|down\|status` | thin wrapper: `alembic.command.upgrade("head")` / `downgrade("base")` / `current()` | 0, 2=`AlembicError` |

Output formatting: errors via `rich.console.Console(stderr=True).print(Panel(..., style="red"))` for `ValidationError`/`InvariantError`, yellow for config/init, plain for runtime. All tables width=120 from settings.

## 7. `config.py` — Settings + Precedence

`Settings(BaseSettings)` fields (already in section 1 module map). **`SettingsConfigDict`**:

```python
SettingsConfigDict(
    env_prefix="FIN_",
    toml_file=_xdg_config_path(),   # env var XDG_CONFIG_HOME override allowed
    extra="ignore",
    case_sensitive=False,
)
```

**Explicit precedence (custom `settings_customise_sources`)**:

1. `init_kwargs` / defaults (class default)
2. TOML file at `_xdg_config_path()`
3. Env vars `FIN_<FIELD_UPPER>`
4. CLI overrides via `load_settings(cli_overrides=...)` — last to merge, wins

`source_of(field)` introspects which source last touched the field by re-running resolution and tagging. Implementation: cache a `dict[str, Literal["default","file","env","flag"]]` populated during merge.

**Loader**: `load_settings(cli_overrides: dict | None = None) -> Settings` — entrypoint used by `cli.main(ctx)`. `ctx.default_map` from Typer populates `cli_overrides`.

## 8. `reports.py` — Exact Formulas

### Monthly report (`compute_monthly_report`)

1. Filter `postings` whose `tx.date` is in `(year, month)`.
2. Group postings by `account_id` → per-account `{total: Decimal, per_day: list[Decimal]}` (per_day length = days in month; default 0).
3. For each account root-type:
   - `Income:*` → `income` section.
   - `Expenses:*` → `expenses` section (sign flipped to negative for display).
   - Others → ignored for monthly view (assets/liabilities tracked via `balance` command).
4. **Rollup** (default ON):
   - For each parent account present in section lines, `parent_total = sum(child_totals)`.
   - Output includes parent lines + leaf lines indented one level (`│   {child}`).
   - `--no-rollup` → leaves only.
5. Sort each section by `abs(total)` descending.
6. **Net** = `sum(income_totals) + sum(expense_totals)` (expenses already negative).
7. Sparkline per line: `per_day` array, rendered via `rich.sparkline.Sparkline(per_day, width=10)`; for short months the inner code pads with `─` prefix to align (rich handles this internally when `min_width` is set; we set `Sparkline(min_width=10)`).

**Algebraic identity**: `income_sum + (-expense_sum) == net` (testable claim, contract d).

### Balance report (`compute_balance`)

For each account (all non-zero):
- `balance(account) = SUM(postings.amount WHERE account_id = X AND tx.date <= as_of)` (default `as_of=None` → all dates).
- Sign convention (spec R7 resolution, **pinned**):
  - `Assets:*` → balance = `+SUM` (positive = held wealth)
  - `Liabilities:*` → balance = `+SUM` (positive = owed)
  - `Equity:*` → balance = `+SUM` (positive = retained)
  - `Income:*` → excluded from balance (period flow, not stock)
  - `Expenses:*` → excluded from balance (period flow, not stock)
- **Net worth** = `SUM(balance(assets)) - SUM(balance(liabilities)) + SUM(balance(equity))`.
- **Display**: per-account balance line; net worth footer bold.

## 9. Test Fixture Architecture

### `tests/conftest.py`

```python
@pytest.fixture
def engine() -> Engine:
    eng = make_test_engine()   # :memory: + StaticPool + pragmas (D2)
    # migrations applied? — NO, tests build schema via `Base.metadata.create_all`
    # for speed; integration tests that exercise migrations use a separate fixture.
    return eng

@pytest.fixture
def conn(engine) -> Iterator[Connection]:
    with engine.begin() as c:
        yield c

@pytest.fixture
def sample_accounts(conn) -> dict[str, Account]:
    """Seed the 11 starter accounts; return name -> Account map."""
    ...

@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner(mix_stderr=False)

@pytest.fixture
def prompt_fn():
    """Returns a callable; tests override via closure."""
    raise RuntimeError("prompt_fn must be overridden in REPL tests")
```

### Per-layer conventions

| Layer | Imports allowed | DB? | Markers |
|---|---|---|---|
| `tests/unit/` | `models`, `validation`, `reports.compute_*` only | no | `@pytest.mark.unit` |
| `tests/integration/` | anything; uses `engine` fixture | yes (per-test `:memory:`) | `@pytest.mark.integration` |
| `tests/property/` | `validation`, `models` + hypothesis strategies | no | `@pytest.mark.property` |
| `tests/snapshots/` | report rendering with `Console(file=StringIO(), no_color=True, force_terminal=False, width=120)` (D3) | no | `@pytest.mark.snapshot` |

### Required property tests (pin spec)

| File | Property | Generator |
|---|---|---|
| `tests/property/test_double_entry_invariant.py` | `∀ random postings summing to 0: validate_transaction() succeeds` | balanced random txn (positive ints split into N postings) |
| `tests/property/test_decimal_quantization.py` | `∀ random Decimal + currency: roundtrip exact, quantized to precision` | per-currency Decimal strategies |
| `tests/property/test_account_name_regex.py` | `∀ random string: re.fullmatch(REGEX, normalize(s)) iff valid` | random strings with case + segments |
| `tests/property/test_decimal_text_roundtrip.py` | `Decimal → str → Decimal == Decimal` | random Decimal strategies |
| `tests/unit/test_no_float_amounts.py` | AST scan of `models.py` + `repository.py` + `validation.py` for `float` annotations | n/a |

### Required unit tests

- `tests/unit/test_models.py` — constructor + to/from_row roundtrip per entity.
- `tests/unit/test_validation.py` — one test per validator; one test per exception subclass.
- `tests/unit/test_repl.py` — `prompt_fn` mock + `:abort` + CTRL-C paths.

## 10. Migration Strategy (per spec R1)

| Item | Decision |
|---|---|
| First migration | Hand-written `migrations/versions/0001_initial_schema.py`. Money columns declared `TEXT`. |
| Autogenerate | Allowed for tables NOT touching money columns. Forbidden on `postings.amount`, `rates.rate`. |
| CI guard | Smoke test: `alembic upgrade head && alembic downgrade base && alembic upgrade head` in `tests/integration/test_migrations.py`. |
| Pre-commit guard | `tests/unit/test_no_float_amounts.py` (AST scan) + `tests/unit/test_money_columns_text.py` (grep migration for `NUMERIC`/`REAL` on money columns → fail). |
| Downgrade | `0001` includes `downgrade()` that drops all 4 tables; chart seed inserted with `IF NOT EXISTS` so upgrade→downgrade→upgrade is idempotent. |

**Rationale (per R1)**: autogenerate emits SQL based on the Python-side column type. Since we use `TypeDecorator`, autogenerate sees `Text` and emits `TEXT` — **for new migrations**. But on the FIRST migration, the model metadata doesn't yet exist, so we hand-write to avoid surprises. After the initial schema is locked, autogenerate is safe for additive changes (new tables, new non-money columns).

## 11. Chained PR Plan (7 PRs, ≤400 lines each)

| PR | Scope | Files | Deps | Lines (est.) |
|---|---|---|---|---|
| **PR 1 — Skeleton** | `db.py`, `config.py`, `validation.py` (stubs + `PER_CURRENCY_DECIMALS` + exception tree), `models.py` (empty dataclasses), `migrations/env.py` + `alembic.ini`, `0001_initial_schema.py`, `cli.py` (`init` + `version` + `migrate`), `pyproject.toml` (entry point already there), `conftest.py`, `tests/unit/test_smoke.py` | — | ~350 |
| **PR 2 — Account rules** | `validation.validate_account_name/currency/date`, `repository.upsert_account/get_account_by_name/list_accounts`, `cli account new/list`, property test for regex, no-float scan test | PR 1 | ~380 |
| **PR 3 — Decimal pipeline** | `validation.validate_amount/quantize_for_currency`, `DecimalAsText` TypeDecorator in `db.py`, `Money` Pydantic type, property tests for quantization + roundtrip, unit test for NaN/Inf rejection | PR 1 | ~280 |
| **PR 4 — Transactions + double-entry** | `validation.validate_posting/validate_transaction`, `repository.create_transaction_with_postings`, `cli add --from/--to` flag mode, contract c `--initial` opening-balance builder, integration tests, property test for sum-zero invariant | PR 2, PR 3 | ~400 |
| **PR 5 — REPL** | `cli add` REPL branch, `repl_add_postings(console, prompt_fn)`, prompt_fn injection fixture, `:abort` and CTRL-C handling, TTY detection (`sys.stdin.isatty()`) | PR 4 | ~250 |
| **PR 6 — Reports** | `reports.py` compute + render, `cli report month`, `cli balance`, snapshot tests, sparkline padding test, integration tests against seeded DB | PR 2 | ~380 |
| **PR 7 — Hardening** | cross-cutting acceptance per proposal §13, README, error UX polish, exit-code assertions in integration tests, CI smoke migration test | all | ~300 |

Total: ~7 PRs, each ≤400 lines, each independently mergeable, each tied to ≥1 contract. PR ordering respects dependency graph.

## 12. Open Design Questions (resolve during apply)

1. **Starter chart count (10 vs 11)** — proposal says "10", listing includes 11 (with `Equity:OpeningBalances`). **Resolution**: 11; document deviation in PR 1 commit message.
2. **Decimal text format** — pinned: `str(Decimal)` canonical form (period decimal, no thousands). Single helper `_format_decimal_for_storage` for consistency.
3. **Validation timing** — pinned: Pydantic validator at CLI boundary + repository-level pre-insert validation + DB-level `CHECK` constraint. Three layers (defence-in-depth, matches spec R-layer reasoning).
4. **Snapshot filename convention** — `tests/snapshots/__snapshots__/<test_module>/<test_name>.ambr` (syrupy default). Test names encode scenario: `test_empty_month`, `test_rollup_default`, `test_expense_with_sparkline`.
5. **Alembic invocation** — pinned: **library** (`alembic.command.upgrade("head")`), not subprocess. Deterministic, testable, no PATH dep. Test fixtures import `alembic.command` directly.
6. **`:save-and-quit` draft** — explicitly deferred (per spec D9). No draft state in DB.
7. **`fin balance` scope** — pinned: per-account balance (any account with postings) + net worth (formula in section 8). No time-series snapshots (F6).
8. **REPL non-TTY error code** — pinned: `ReplRequiresTTYError` → exit 2 (runtime), with stderr message `REPL requires interactive terminal; use --from/--to for non-interactive entry`.
9. **CLI flag-mode precedence** — pinned: if BOTH `--from`/`--to` AND REPL positional args present → flag mode wins; REPL positional args ignored with stderr warning.
10. **Account depth regex check** — anchored in regex (max 2 children) AND re-checked in `validate_account_name` (defence-in-depth) using `name.count(":") <= 2`.

## Constraints honoured

- Greenfield confirmed (only `__init__.py` in `src/pyfintracker/`).
- All 4 entities frozen `@dataclass`, all amounts `Decimal`, never `float`.
- Money columns `TEXT`, never `NUMERIC`.
- Hand-written first migration.
- Single `engine.begin()` per multi-row write.
- Pydantic for envelopes + config; Typer for CLI; SQLAlchemy Core (no ORM).
- No DDD layers (matches proposal "lazy-clean").
- Test pyramid: unit / integration / property / snapshot.
- ≥90% coverage on `models.py`+`repository.py`+`validation.py`; ≥70% global.