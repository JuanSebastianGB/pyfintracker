---
type: design
id: multi-moneda-design
status: draft
tags: [python, cli, finance, fx, multi-currency, frankfurter, design, wave-2]
parent_proposal: multi-moneda
parent_spec: multi-moneda-spec
parent_tasks: null
---

# Design — multi-moneda (Wave 2A)

Source of truth: engram obs `anvil/multi-moneda/design`. This file mirrors for downstream consumption.

## 1. Overview

Wave 2A delivers honest display-layer multi-currency on top of Wave 1's single-currency-per-account invariant. Add a Frankfurter v2 HTTP client (`fx.py`), a `Rate` dataclass + persistent cache backed by the existing `rates` table (with new `fetched_at` TTL column), a pure `Decimal` `convert()` function, three new exception classes (exit codes 4/5/6), the `fin convert` CLI command, and `--currency` flags on `report month` + `balance`. Each posting converts via transaction-date rate before aggregation (D8 AST guard prevents raw cross-currency sums). Schema adds `transactions.currency` + widens `accounts.currency` CHECK from 5 to 12 curated currencies.

## 2. Module Map

| Module | Action | Purpose |
|---|---|---|
| `src/pyfintracker/fx.py` | Create | Frankfurter v2 client, `get_rate()`, `convert()`, TTL fallback, stdlib logging for warnings |
| `src/pyfintracker/models.py` | Modify | Add `Rate` frozen dataclass; `fetched_at: datetime \| None` field |
| `src/pyfintracker/validation.py` | Modify | Extend `PER_CURRENCY_DECIMALS` from 5 to 12 currencies (B3) |
| `src/pyfintracker/repository.py` | Modify | Add `get_cached_rate`, `upsert_rate`, `list_cached_rates`, `get_rate_at_date` |
| `src/pyfintracker/reports.py` | Modify | `compute_*` accept `display_currency`; pre-fetch rates by `(date, from_ccy)` group; convert before aggregate |
| `src/pyfintracker/cli.py` | Modify | New `convert` command; `--currency` on `report month` + `balance`; `config_show` lists `display_currency` |
| `src/pyfintracker/config.py` | Modify | Rename `default_currency` → `display_currency`; env `FIN_DISPLAY_CURRENCY`; deprecation log for old key |
| `src/pyfintracker/exceptions.py` | Modify | Add `RateNotFoundError` (code=4), `InvalidCurrencyError` (code=5, FX-context only), `FxUnavailableError` (code=6) |
| `migrations/versions/0002_multi_currency_schema.py` | Create | Add `transactions.currency` + backfill; `rates.fetched_at` + index; widen `accounts.currency` CHECK |
| `tests/unit/test_no_float_amounts.py` | Modify | Extend AST scan to `fx.py` |
| `tests/unit/test_no_raw_currency_sum.py` | Create | D8 AST guard: no `Decimal.__add__` of postings from different account currencies without convert |
| `tests/integration/test_fx_cache.py`, `test_convert_cli.py`, `test_reports_multi_currency.py` | Create | Per-contract integration |

## 3. Data Model

### `Rate` (new in `models.py`)

```python
@dataclass(frozen=True, slots=True)
class Rate:
    id: int | None = None
    date: date                    # API effective date (NOT requested date)
    from_ccy: str = ""            # ISO 4217; "from_ccy" avoids Python keyword
    to_ccy: str = ""
    rate: Decimal = Decimal("0")
    fetched_at: datetime | None = None  # populated on read; cache TTL
    source: str = "frankfurter"
```

`to_row()` / `from_row()` map `from_ccy`/`to_ccy` → DB columns `base_currency`/`target_currency` (schema names unchanged — minimises migration risk; R-decision A1).

### `transactions.currency` (new column)

`TEXT NOT NULL DEFAULT 'COP'` (migration 0002 backfills dominant posting currency per B4).

## 4. Migrations

### `0002_multi_currency_schema.py` (single combined migration; per R7 decision below)

```sql
-- up
ALTER TABLE transactions ADD COLUMN currency TEXT NOT NULL DEFAULT 'COP';
UPDATE transactions
SET currency = (
    SELECT p.currency FROM postings p
    WHERE p.transaction_id = transactions.id
    GROUP BY p.currency ORDER BY COUNT(*) DESC LIMIT 1
);
CREATE INDEX IF NOT EXISTS idx_transactions_currency ON transactions(currency);

ALTER TABLE rates ADD COLUMN fetched_at TEXT NOT NULL DEFAULT (datetime('now'));
CREATE INDEX IF NOT EXISTS idx_rates_lookup
    ON rates(base_currency, target_currency, date);

-- Widen accounts.currency CHECK (SQLite recreate-table dance)
CREATE TABLE accounts_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    parent_id INTEGER REFERENCES accounts(id) ON DELETE RESTRICT,
    currency TEXT NOT NULL DEFAULT 'COP'
        CHECK(currency IN ('COP','USD','EUR','GBP','JPY','CAD','AUD','CHF','MXN','BRL','INR','CNY')),
    depth INTEGER NOT NULL DEFAULT 0 CHECK(depth >= 0 AND depth <= 2),
    kind TEXT NOT NULL CHECK(kind IN ('Assets','Liabilities','Equity','Income','Expenses')),
    is_archived INTEGER NOT NULL DEFAULT 0 CHECK(is_archived IN (0,1)),
    created_at TEXT NOT NULL DEFAULT (date('now'))
);
INSERT INTO accounts_new SELECT * FROM accounts;
DROP TABLE accounts;
ALTER TABLE accounts_new RENAME TO accounts;
CREATE INDEX idx_accounts_parent ON accounts(parent_id);
CREATE INDEX idx_accounts_kind ON accounts(kind);
CREATE INDEX idx_accounts_currency ON accounts(currency);

-- down (reverse)
-- DROP indexes; restore 5-currency CHECK via recreate; DROP fetched_at via recreate
```

**R7 resolution**: keep 0002 combined (transactions + rates + accounts) — all three are additive, ~60 lines SQL, well under PR A budget. Splitting to 0003 buys nothing.

## 5. Validation Rules

| Rule | Source | Failure |
|---|---|---|
| 12-currency allowlist (`COP,USD,EUR,GBP,JPY,CAD,AUD,CHF,MXN,BRL,INR,CNY`) | B3 | `InvalidCurrency` exit 1 (validate_currency) |
| `rate > 0` | FX-1 | `RateNotFoundError` exit 4 |
| `from_ccy == to_ccy` → fast-path `Decimal("1")`; no I/O | FX-1 edge | n/a |
| Same-currency `convert(X, X)` → `quantize_for_currency(X)`; no I/O | FX-3 rule 7 | n/a |
| Future `on > today` → reject (never zero/negative) | FX-2 rule 3 | `RateNotFoundError` exit 4 |
| Result quantized to `PER_CURRENCY_DECIMALS[to_ccy]`, `ROUND_HALF_UP` | FX-3 rule 6 | n/a |
| Inverse rate: `1 / rate` quantized to `PER_CURRENCY_DECIMALS[from_ccy]` | FX-1 edge | n/a |
| Negative/zero amount: allowed (CLI doesn't error) | FX-3 edge | n/a |
| Historical rates: TTL ignored (cached forever) | FX-5 rule 2 | n/a |
| Latest rates: cache iff `now - fetched_at <= 24h` | FX-5 rule 1 | n/a |

Exception hierarchy (new in `exceptions.py`):
```
FinanceError
├── RateNotFoundError(FinanceError)        # code=4
├── InvalidCurrencyError(FinanceError)     # code=5 (FX-only; distinct from InvalidCurrency)
└── FxUnavailableError(FinanceError)       # code=6
```

## 6. Repository (new functions)

```python
def get_cached_rate(conn, from_ccy: str, to_ccy: str, on: date) -> Rate | None
def get_cached_rate(conn, from_ccy, to_ccy, on, *, ttl: timedelta | None = None) -> Rate | None  # latest
def upsert_rate(conn, rate: Rate) -> Rate                    # idempotent on (date, base_ccy, target_ccy)
def list_cached_rates(conn, *, since: date | None = None) -> Sequence[Rate]
def get_rate_at_date(conn, from_ccy, to_ccy, on: date) -> Rate | None  # raw read, no TTL
```

`upsert_rate` SQL: `INSERT ... ON CONFLICT(base_currency, target_currency, date) DO UPDATE SET rate=excluded.rate, fetched_at=excluded.fetched_at; RETURNING ...`. Returns the existing row on conflict (idempotent).

`get_cached_rate` for latest: `WHERE base=? AND target=? ORDER BY date DESC LIMIT 1` then Python-side TTL check via `fetched_at`. Index covers it.

## 7. FX Module (`fx.py`)

```python
DEFAULT_TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0)
BASE_URL: ClassVar[str] = "https://api.frankfurter.dev/v2"

class FrankfurterClient:
    def __init__(self, *, timeout=DEFAULT_TIMEOUT, transport: httpx.BaseTransport | None = None) -> None
    def fetch_latest(self, from_ccy: str, to_ccy: str) -> Rate
    def fetch_historical(self, from_ccy: str, to_ccy: str, on: date) -> Rate
    def list_currencies(self) -> dict[str, str]

# Module-level singleton (lazy-instantiated); overridable for tests via fx.set_client()
def get_rate(from_ccy, to_ccy, on: date | None = None, *, allow_stale: bool = False) -> Rate
def convert(amount: Decimal, from_ccy: str, to_ccy: str, *, on: date | None = None) -> Decimal
def list_supported_currencies() -> frozenset[str]
```

**Cache strategy** (`get_rate`):
1. If `from_ccy == to_ccy` → return `Rate(rate=Decimal("1"))`.
2. Try cache: direct `(from_ccy, to_ccy, on)`; if latest (`on is None`), enforce TTL; else TTL-ignored.
3. Cache miss: try inverse `(to_ccy, from_ccy, on)`; if found, return `1/rate` quantized to `from_ccy` precision.
4. Both miss: call `client.fetch_*`; parse `Decimal(str(raw))`; upsert cache; return.
5. Network error on latest + cache hit within TTL → return cache + `logging.warning("using cached rate from %s (network unavailable)", fetched_at)`. No exception.
6. Network error on historical + cache miss → `FxUnavailableError`.
7. `date > today` → `RateNotFoundError` (never substitute today's rate).

Error mapping per FX-2 table (404 → 4, 422 → 5, network/5xx → 6). Retry once on `httpx.ConnectError` only.

## 8. CLI Integration

### `fin convert <amount> <from> <to> [--date YYYY-MM-DD]`

```
50000 COP = 15.36 USD (rate 0.000307, 2026-07-18, frankfurter)
```

Typer: `convert(amount: str, from_ccy: str, to_ccy: str, date: str = typer.Option("", "--date"))`. Validates amount via `validate_amount(amount, from_ccy)`, calls `fx.convert()`, prints formatted line on stdout. Stderr carries stale-fallback warning (FX-5 rule 6). Exit codes per FX-3.

### `fin report month --month YYYY-MM --currency CCY`

`--currency` validated via `validate_currency` first (D7). Empty → `Settings.display_currency` from config. Header `July 2026 (USD)` (FX-4 rule 5).

### `fin balance --currency CCY`

Same flag semantics. Output footer `NET WORTH: <Decimal> CCY` (FX-4 claim 3).

### `fin config show`

Replace `default_currency` line with `display_currency`. Source tag uses `FIN_DISPLAY_CURRENCY` env / `[file]` / `[default]`.

### `config.py` migration path (B2)

- Field renamed in `Settings`: `display_currency: str = "COP"`.
- Backward compat: if TOML has `default_currency` key, `load_settings` reads it, logs `DeprecationWarning`, writes `display_currency` on next `config_show`.
- Env var: `FIN_DISPLAY_CURRENCY` (old `FIN_DEFAULT_CURRENCY` still read with warning).

## 9. Reports under Multi-Currency

### `compute_monthly_report(conn, year_month, *, display_currency="COP")`

```sql
SELECT p.amount, p.currency, t.date, a.name, a.kind
FROM postings p
JOIN transactions t ON p.transaction_id = t.id
JOIN accounts a ON p.account_id = a.id
WHERE strftime('%Y-%m', t.date) = :ym
```

Python loop:
1. Group postings by `(t.date, p.currency)` tuple.
2. For each group, call `fx.get_rate(group.currency, display_currency, on=group.date)` (cached; one HTTP call per unique pair+date).
3. Convert each posting: `fx.convert(amount, p.currency, display_currency, on=t.date)`.
4. Aggregate by account into existing income/expense buckets (Wave 1 logic unchanged; just over converted amounts).
5. Return `MonthlyReport` with new `currency: str` field. Header renders `July 2026 (USD)`.

### `compute_balance(conn, *, display_currency="COP", as_of=None)`

```sql
SELECT p.amount, p.currency, t.date, a.id, a.name, a.kind
FROM postings p
JOIN transactions t ON p.transaction_id = t.id
JOIN accounts a ON p.account_id = a.id
```

Convert each posting at `t.date` rate (NOT `as_of`; F3 mark-to-market deferred). Sum converted amounts per account, then net worth. `BalanceReport.currency: str` field added.

**R5 mitigation**: `(date, currency)` grouping collapses N postings to ≤N distinct rate lookups. Tested with seeded mixed-currency DB (FX-4 claim 1).

## 10. AST No-Raw-Sum Guard (D8)

`tests/unit/test_no_raw_currency_sum.py` walks `reports.py` AST and asserts:

```python
for node in ast.walk(tree):
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        if _is_posting_amount(node.left) and _is_posting_amount(node.right):
            pytest.fail("raw Decimal addition of postings without convert()")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "sum":
        # sum() over postings is allowed only if list comes from already-converted source
        ...
```

Heuristic: flag any `+` where both operands are `Decimal` variables holding a posting's `.amount` field. Whitelist: `aggregated.get(key, Decimal("0")) + e["amount"]` in Wave 1's `_to_lines` is allowed because `e["amount"]` is already a converted `Decimal` (we'll convert before insertion in the modified function).

Also extends `tests/unit/test_no_float_amounts.py` to scan `fx.py`.

Pre-commit hook: `uv run pytest tests/unit/test_no_raw_currency_sum.py tests/unit/test_no_float_amounts.py`.

## 11. Test Strategy

| Contract | Unit | Integration | Property | Snapshot |
|---|---|---|---|---|
| **FX-1** Rate+cache | `Rate.to_row`/`from_row`; inverse arithmetic | real-DB roundtrip; `PRAGMA index_info` assertion | ∀Decimal: roundtrip byte-exact | — |
| **FX-2** Frankfurter | httpx MockTransport per status (200/404/422/future/5xx/network) | cache fill from client response | ∀payload: rate parsed via `Decimal(str)` not `float` | — |
| **FX-3** convert | pure arithmetic + spies | CliRunner `fin convert` happy + error | ∀Decimal × pair: result quantized | CLI `fin convert 50000 COP USD` |
| **FX-4** reports | `compute_*` with stubbed `fx.get_rate` | CliRunner on seeded mixed-currency DB | ∀mixed postings: convert-then-aggregate == per-posting convert | full Rich output per scenario |
| **FX-5** fallback | TTL boundary (23h vs 25h); inverse arithmetic | CliRunner cache+network-down | ∀historical: TTL ignored | CLI w/ and w/o warning line |

**41 testable claims** (FX-1:6 + FX-2:8 + FX-3:9 + FX-4:8 + FX-5:10 = 41). Property tests: FX-1 roundtrip, FX-3 quantization, FX-4 convert-identity, FX-5 historical-no-TTL, FX-2 no-float AST. Coverage target: 95% on `fx.py`, 90% on new `repository.py` functions, 90% on modified `reports.py`. Global floor 70% unchanged.

## 12. Review Budget + Chained PR Plan

| PR | Scope | Files | Est. lines | Risk |
|---|---|---|---|---|
| **A** Schema + Rate model + migration 0002 + allowlist | `models.py` (Rate), `validation.py` (PER_CURRENCY_DECIMALS), `0002_multi_currency_schema.py`, `config.py` (display_currency), `cli.py` (config_show update), `tests/unit/test_models.py`, `tests/integration/test_migrations.py` | 7 | ~340 | Low (additive) |
| **B** Frankfurter v2 client + cache | `fx.py` (FrankfurterClient, get_rate, convert skeletons, exceptions), `repository.py` (4 new fns), `tests/unit/test_fx_client.py`, `tests/integration/test_fx_cache.py` | 4 | ~380 | Med (HTTP) |
| **C** `fin convert` + internal convert + tests | `fx.py` (convert, get_rate final), `cli.py` (convert command + REPL UX), `tests/integration/test_convert_cli.py`, snapshot baseline | 3 | ~280 | Low |
| **D** `compute_*` reports + `--currency` flags | `reports.py` (modify compute_* + new fields), `cli.py` (--currency on report month + balance), `tests/integration/test_reports_multi_currency.py`, snapshots | 3 | ~360 | Med (FX-4) |
| **E** AST no-raw-sum guard + final tests + cleanup | `tests/unit/test_no_raw_currency_sum.py`, extend `test_no_float_amounts.py`, pre-commit hook wiring, README updates, end-to-end migration smoke test | 4 | ~260 | Low |

**Total**: ~1,620 lines across 5 PRs; each ≤400; each independently mergeable. Review budget 800 lines/PR honoured (each PR is under).

## Open Questions

- **Q1**: B2 — old `default_currency` TOML key behaviour: silent migrate vs. hard fail? **Pinned**: silent migrate + deprecation log; one-line override. Resolves during PR A.
- **Q2**: `Rate.from_row` mapping `base_currency` ↔ `from_ccy` — keep schema names or rename? **Pinned**: keep schema names (`base_currency`/`target_currency`), expose as `from_ccy`/`to_ccy` in Python only. Migration risk zero. Resolves during PR A.
- **Q3**: Should `transactions.currency` backfill skip rows where dominant currency is ambiguous (count tie)? **Pinned**: yes — leave `COP` default and emit `logging.warning` (B4 + R2). Resolves during PR A.

## Constraints honoured

- All money paths `Decimal`; no `float` in `fx.py`/`reports.py`/`repository.py` (AST guard + property).
- Money columns remain `TEXT` (no schema change to amount columns).
- Each account and posting keeps one native currency (Wave 1 invariant).
- Migration 0002 additive; downgrade reverses cleanly.
- Existing Wave 1 commands unchanged when no `--currency` flag given; default `display_currency="COP"`.
- Exit codes 0/1/2/3/130 preserved; new 4/5/6 only emitted by FX paths.