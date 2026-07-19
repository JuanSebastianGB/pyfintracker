---
type: spec
id: multi-moneda-spec
status: draft
tags: [python, cli, finance, fx, multi-currency, frankfurter, spec, wave-2]
parent_proposal: multi-moneda
parent_design: null
parent_tasks: null
---

# Spec — multi-moneda (Wave 2A)

Source of truth: engram obs `anvil/multi-moneda/spec`. This file mirrors for downstream consumption.

## Scope

Wave 2A = display-layer multi-currency. Each account and posting keeps ONE native currency (Wave 1 invariant preserved). Frankfurter v2 supplies FX rates via `httpx`; rates persist in the existing `rates` table; new `fin convert` CLI + `--currency` flag on `fin report month` and `fin balance` give honest conversion without breaking double-entry. Cross-currency postings defer to Wave 2B (see F1, F2).

## Blocker Resolutions (locked before design)

| # | Decision | Rationale |
|---|----------|-----------|
| **B1** | **Exit-code extension.** New codes 4=RateNotFound, 5=InvalidCurrency (FX-specific), 6=FxUnavailable/Network. Existing 0/1/2/3/130 unchanged. | FX failures must be distinguishable from validation/config errors for scripting (`fin convert` in shell pipelines). |
| **B2** | **Rename `default_currency` → `display_currency`** in `Settings`. TOML key changes; `FIN_DISPLAY_CURRENCY` env var replaces `FIN_DEFAULT_CURRENCY`. Migration of user config: write new key, log deprecation if old key seen. | `default_currency` is misleading (it never selected the txn currency). `display_currency` accurately describes its role: the unit reports show by default. |
| **B3** | **Curated allowlist** — `PER_CURRENCY_DECIMALS` extended to the 12 currencies Wave 2A supports (`COP, USD, EUR, GBP, JPY, CAD, AUD, CHF, MXN, BRL, INR, CNY`). All other ISO codes → `UnknownCurrency`. | v2 offers 201 currencies; we only need precision metadata for ones the owner holds. Adding dynamic precision needs a separate spec. |
| **B4** | **`transactions.currency` semantics** = dominant posting currency (most postings). Persist via migration 0002. **NOT** a balancing/functional currency. | Wave 2A never has mixed-currency postings (F1). The field is persisted only because `models.Transaction.currency` already exists in Python and design §3 promised it. Wave 2B will redefine. |
| **B5** | **Rate-direction policy.** Cache stores rows with `(from_ccy, to_ccy, date, rate)`. Lookup: try direct, then inverse (`1 / rate` quantized to `PER_CURRENCY_DECIMALS[from_ccy]`). Never triangulate. | Two-row cache miss implies the provider doesn't have either direction; refuse rather than compose silently. |

## Design Resolutions (locked)

| # | Decision |
|---|----------|
| **D1** | Frankfurter base URL pinned: `https://api.frankfurter.dev/v2`. No env override (deterministic, testable). |
| **D2** | `httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0)` per request; one retry on `httpx.ConnectError` only. |
| **D3** | New module `src/pyfintracker/fx.py`. Public API: `get_rate(from_ccy, to_ccy, on: date | None) -> Rate`, `convert(amount, from_ccy, to_ccy, *, on: date | None) -> Decimal`, `list_supported_currencies() -> frozenset[str]`. Internal: `FrankfurterClient` (httpx). |
| **D4** | New exceptions in `exceptions.py`: `RateNotFoundError(FinanceError, code=4)`, `InvalidCurrencyError(FinanceError, code=5)` (FX-context only — distinct from existing `InvalidCurrency` which stays exit 1), `FxUnavailableError(FinanceError, code=6)`. |
| **D5** | TTL via new `fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` column (migration 0002). Cache hit on latest iff `now - fetched_at <= 24h`. Historical: cached forever (no TTL check). |
| **D6** | `Rate` dataclass field names = `from_ccy`, `to_ccy` (match existing schema; avoid Python `from` keyword). |
| **D7** | CLI `--currency X` validation runs `validate_currency(X)` first (exit 1 on unknown); only after passing does it route to FX. |
| **D8** | Property test: `compute_monthly_report` and `compute_balance` MUST convert each posting before any aggregation. AST-level guard: `tests/unit/test_no_raw_currency_sum.py` scans `reports.py` for `Decimal(...) + Decimal(...)` patterns where the two operands come from postings of different accounts. |
| **D9** | `fin convert` output goes to stdout; FX-fallback warnings go to stderr. Network failure + cache miss → exit 6 with red panel. Network failure + fresh cache → exit 6 with yellow panel + warning line "warning: using cached rate from YYYY-MM-DD HH:MM:SS". |

## Contract FX-1: `Rate` model + persistent cache

### API surface

```python
# src/pyfintracker/models.py (new entity)
@dataclass(frozen=True, slots=True)
class Rate:
    id: int | None
    date: date                        # API effective date (NOT requested date)
    from_ccy: str                     # ISO 4217
    to_ccy: str
    rate: Decimal                     # DecimalAsText
    fetched_at: datetime | None       # populated on read; not persisted in 0001
    source: str = "frankfurter"       # provider tag

    def to_row(self) -> dict[str, object]: ...
    @staticmethod
    def from_row(row: Mapping[str, Any]) -> Rate: ...

# src/pyfintracker/repository.py (new functions)
def get_cached_rate(conn, from_ccy: str, to_ccy: str, on: date) -> Rate | None: ...
def upsert_rate(conn, rate: Rate) -> Rate: ...   # idempotent on (date, from_ccy, to_ccy)
def list_cached_rates(conn, *, since: date | None = None) -> Sequence[Rate]: ...
```

### Validation rules
1. `from_ccy != to_ccy` (no zero-rate self-lookup). Equality → fast-path returns `Decimal("1")`.
2. `from_ccy`, `to_ccy` ∈ `list_supported_currencies()` → else `UnknownCurrency` (exit 1).
3. `rate > 0` (negative or zero rate is provider bug → `RateNotFoundError`, exit 4).
4. `date` is a `datetime.date`; reject `datetime` objects or strings at boundary.
5. `fetched_at` is read-only outside the repository; never accepted from CLI.

### Edge cases
- Cache hit on direct pair (`USD → COP`) → use it.
- Cache hit only on inverse (`COP → USD`, need `USD → COP`) → invert: `1 / rate` quantized to `PER_CURRENCY_DECIMALS[from_ccy]`.
- Cache miss both directions → caller (`fx.get_rate`) fetches.
- Cache hit but `date` is in future (clock skew) → treat as miss; provider's effective date governs.
- Same-currency `convert` → returns `quantize_for_currency(amount, ccy)`, never touches the network or DB.

### Testable claims
1. `Rate.from_row` + `to_row` roundtrip preserves all 7 fields byte-exact.
2. `get_cached_rate` returns `None` for `from_ccy == to_ccy` (caller fast-paths).
3. `get_cached_rate("USD", "COP", date(2024,1,15))` returns a row where `rate.date == 2024-01-15` even if `date` requested differs from API effective date — the row's date is the API's.
4. `upsert_rate` is idempotent: writing the same `(date, from_ccy, to_ccy)` twice produces one row, second call returns existing.
5. `Rate.rate` is `Decimal`, never `float` (AST scan + property test on `to_row`).
6. Schema-level: `rates.fetched_at` index supports `WHERE from_ccy=? AND to_ccy=? AND date=?` lookup under 1ms on 10k-row cache (query plan assertion in integration test).

### DB impact

| Table | Column added | Migration | Index added |
|---|---|---|---|
| `rates` | `fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | `0002_fx_cache_ttl.py` | `idx_rates_lookup ON rates(from_ccy, to_ccy, date)` |

No destructive changes. Existing rows: `fetched_at` defaults to row creation time. Read-only impact: `Rate.from_row` must populate `fetched_at` from the column; old rows from Wave 1 (none expected — table is unused) work the same.

### Example

```python
rate = Rate(id=None, date=date(2026, 7, 18), from_ccy="USD", to_ccy="COP",
            rate=Decimal("3255.56"), fetched_at=None)
saved = upsert_rate(conn, rate)        # returns Rate with id=1, fetched_at populated on re-read
cached = get_cached_rate(conn, "USD", "COP", date(2026, 7, 18))   # returns saved
```

### Requirement: Rate model + persistent cache

The system MUST persist `Rate` rows in the `rates` table with `fetched_at` for TTL, MUST roundtrip via `to_row`/`from_row` byte-exact, and MUST never insert a zero/negative rate.

#### Scenario: upsert idempotent on (date, from_ccy, to_ccy)
- GIVEN empty `rates` table
- WHEN `upsert_rate(Rate(date=D, from_ccy="USD", to_ccy="COP", rate=R))` called twice with identical fields
- THEN table has exactly 1 row
- AND both calls return the same `Rate` (same `id`, `fetched_at`)

#### Scenario: cache lookup returns stored row
- GIVEN row `(date=2026-07-18, USD→COP, rate=3255.56)` exists
- WHEN `get_cached_rate("USD", "COP", date(2026, 7, 18))`
- THEN returns that exact `Rate`

#### Scenario: inverse lookup inverts rate
- GIVEN row `(date=2026-07-18, COP→USD, rate=0.000307)` exists
- WHEN `get_cached_rate("USD", "COP", date(2026, 7, 18))`
- THEN returns rate ≈ `Decimal("3257.32")` (= 1 / 0.000307, quantized to COP precision 0 → `3257`)

#### Scenario: unknown currency rejected at boundary
- GIVEN `validate_currency("ABC")` raises
- WHEN caller invokes `get_cached_rate("USD", "ABC", today)`
- THEN `UnknownCurrency` raised before any DB call (verified via `connection_not_touched` spy)

---

## Contract FX-2: Frankfurter v2 HTTP client

### API surface

```python
# src/pyfintracker/fx.py
class FrankfurterClient:
    BASE_URL: ClassVar[str] = "https://api.frankfurter.dev/v2"

    def __init__(self, *, timeout: httpx.Timeout = DEFAULT_TIMEOUT,
                 transport: httpx.BaseTransport | None = None) -> None: ...
    def fetch_latest(self, from_ccy: str, to_ccy: str) -> Rate: ...
    def fetch_historical(self, from_ccy: str, to_ccy: str, on: date) -> Rate: ...
    def list_currencies(self) -> dict[str, str]: ...   # {"USD": "United States Dollar", ...}
```

### Validation rules
1. `from_ccy`, `to_ccy` ∈ curated allowlist → else `InvalidCurrencyError` (exit 5).
2. `on` is `datetime.date` or `None`; `None` ⇒ `fetch_latest`; otherwise `fetch_historical`.
3. `on > date.today()` → `RateNotFoundError` (exit 4); never interpret as zero rate.
4. Response JSON `rate` parsed via `Decimal(str(raw))` — never `float(raw)`.
5. Response JSON `date` (effective date) used; never the requested date.

### Error mapping (HTTP status → exception)

| Status / condition | Exception | Exit |
|---|---|---|
| 200 with `rates` map missing the requested quote | `RateNotFoundError` | 4 |
| 200 with empty array (future date) | `RateNotFoundError` | 4 |
| 404 `{"message":"not found"}` | `RateNotFoundError` | 4 |
| 422 `{"message":"invalid currency: X"}` | `InvalidCurrencyError` | 5 |
| 422 `{"message":"invalid date"}` | `InvalidDate` (existing, exit 1) | 1 |
| `httpx.ConnectError`, `TimeoutException` | `FxUnavailableError` | 6 |
| 5xx | `FxUnavailableError` | 6 |
| Malformed JSON | `FxUnavailableError` (treat as upstream bug) | 6 |

### Edge cases
- Weekend `2024-01-06` — v2 may return a row dated that day; we use it as-is. If empty → `RateNotFoundError`.
- Holiday `2024-01-01` — same as weekend.
- Future date with no data — 200 `[]` → `RateNotFoundError` (NOT `FxUnavailableError`).
- Provider returns negative or zero rate — provider bug → `RateNotFoundError` and skip caching.
- Network down + cached latest hit (within 24h) — `get_rate` returns cache + emits warning via stderr (caller's job to surface); contract FX-5 governs.

### Testable claims
1. `FrankfurterClient("https://mock").fetch_latest("USD", "COP")` calls `GET /v2/rate/USD/COP` exactly once.
2. Response with `rate: 3255.56` parsed into `Decimal("3255.56")` (not `Decimal("3255.5600000000001")`).
3. 404 → raises `RateNotFoundError` (exit code attribute `== 4`).
4. 422 with `"invalid currency: ABC"` → raises `InvalidCurrencyError` (exit `== 5`).
5. Network error (httpx mock raising `ConnectError`) → raises `FxUnavailableError` (exit `== 6`) after at most 1 retry.
6. Future date `2099-01-01` → `RateNotFoundError`, NOT `FxUnavailableError`.
7. Malformed JSON `{"date": "2026-07-18", "base": "USD"}` (no `rate`) → `RateNotFoundError`.
8. `list_currencies()` returns dict with `len() == 12` (curated allowlist intersection).

### DB impact
None directly. `FrankfurterClient` is pure HTTP; persistence is the caller's job (`fx.get_rate` writes the cache).

### Example

```python
client = FrankfurterClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={
    "date": "2026-07-18", "base": "USD", "quote": "COP", "rate": 3255.56
})))
rate = client.fetch_latest("USD", "COP")
# rate.date == date(2026, 7, 18); rate.rate == Decimal("3255.56"); rate.from_ccy == "USD"
```

### Requirement: Frankfurter v2 client

The system MUST use `https://api.frankfurter.dev/v2` exclusively, MUST parse `rate` via `Decimal(str(raw))`, MUST use the API's effective date, and MUST map HTTP statuses to the exit codes above.

#### Scenario: latest pair fetch succeeds
- GIVEN mock returns `{"date": "2026-07-18", "base": "USD", "quote": "COP", "rate": 3255.56}`
- WHEN `client.fetch_latest("USD", "COP")`
- THEN returns `Rate(date=2026-07-18, from_ccy="USD", to_ccy="COP", rate=Decimal("3255.56"))`

#### Scenario: 404 maps to RateNotFoundError (exit 4)
- GIVEN mock returns 404 `{"message":"not found"}`
- WHEN `client.fetch_latest("USD", "XYZ")`
- THEN raises `RateNotFoundError`
- AND `e.code == 4`

#### Scenario: network error maps to FxUnavailableError (exit 6)
- GIVEN mock transport raises `httpx.ConnectError`
- WHEN `client.fetch_latest("USD", "COP")`
- THEN raises `FxUnavailableError`
- AND `e.code == 6`

#### Scenario: future date is RateNotFoundError, not FxUnavailableError
- GIVEN mock returns 200 `[]`
- WHEN `client.fetch_historical("USD", "COP", date(2099, 1, 1))`
- THEN raises `RateNotFoundError` (NOT `FxUnavailableError`)

---

## Contract FX-3: Conversion (`fin convert` + internal `convert`)

### API surface

```python
# src/pyfintracker/fx.py
def get_rate(from_ccy: str, to_ccy: str, on: date | None = None) -> Rate: ...
def convert(amount: Decimal, from_ccy: str, to_ccy: str, *,
            on: date | None = None) -> Decimal: ...
def list_supported_currencies() -> frozenset[str]: ...

# src/pyfintracker/cli.py (new top-level command)
@app.command()
def convert(amount: str, from_ccy: str, to_ccy: str,
            date: str = typer.Option("", "--date",
                help="Historical rate date YYYY-MM-DD (default: latest)")) -> None: ...
```

### Validation rules
1. `amount` is parsed by `validate_amount(amount, from_ccy)` → `Decimal`, rejects `float`/`NaN`/`Inf`.
2. `from_ccy`, `to_ccy` validated via `validate_currency` → uppercase 3-letter ISO; else `InvalidCurrency` (exit 1).
3. Both in curated allowlist (B3) → else `InvalidCurrencyError` (exit 5) only when network/cache lookup fails the allowlist gate.
4. `on=None` ⇒ use latest rate (24h TTL); `on=date(...)` ⇒ use historical rate (∞ TTL).
5. `on > date.today()` → `RateNotFoundError` (exit 4) — never zero, never negative.
6. Result quantized to `PER_CURRENCY_DECIMALS[to_ccy]` with `ROUND_HALF_UP`.
7. Same-currency `convert(amount, X, X)` → `quantize_for_currency(amount, X)` without I/O.

### Edge cases
- Empty rate cache + network down + non-historical date → `FxUnavailableError` (exit 6).
- Historical date + cache hit → use cache, never network.
- Historical date + cache miss + network down → `FxUnavailableError`.
- `on` is string `"2024-01-15"` → parse via `validate_date` first.
- CLI flag `--date` invalid (`"2024-13-01"`) → `InvalidDate` (exit 1), stderr message.
- `amount = 0` → allowed (returns `Decimal("0")` quantized); CLI does NOT error.
- Negative `amount` → allowed (returns negative quantized result).

### Testable claims
1. `convert(Decimal("100"), "USD", "COP", on=date(2024,1,15))` returns a `Decimal` with 0 decimal places (= COP precision), value `392450` when rate is `3924.50`.
2. `convert(Decimal("100"), "USD", "USD", on=today)` returns `Decimal("100.00")` (no I/O — verified by transport spy never called).
3. `convert(Decimal("1234.567"), "USD", "COP", on=today)` with rate `3255.56` returns `Decimal("4021187")` (= `1234.567 * 3255.56`, quantized to 0).
4. `get_rate("USD", "COP", on=date(2024,1,15))` with cached row returns cached; transport spy shows 0 calls.
5. `get_rate("USD", "COP", on=date(2024,1,15))` with cache miss calls `client.fetch_historical("USD", "COP", date(2024,1,15))` exactly once and writes the result.
6. CLI `fin convert 50000 COP USD` outputs `50000 COP = 15.36 USD (rate 0.000307, 2026-07-18, frankfurter)` (format pinned; syrupy snapshot).
7. CLI `fin convert 100 USD COP --date 2024-01-15` with cached historical → no network (transport spy), same output format.
8. Negative amount `convert(Decimal("-100"), "USD", "COP", on=D)` returns negative quantized result.
9. Future `on=date(2099,1,1)` + no cache → `RateNotFoundError` (exit 4), not `FxUnavailableError`.

### DB impact
- Reads: `rates` (cache lookup).
- Writes: `rates` (cache fill on miss, via `upsert_rate`).
- No `transactions` or `postings` writes (display-only).

### Example

```bash
$ fin convert 50000 COP USD
50000 COP = 15.36 USD (rate 0.000307, 2026-07-18, frankfurter)

$ fin convert 100 USD COP --date 2024-01-15
100 USD = 392450 COP (rate 3924.50, 2024-01-15, frankfurter)

$ fin convert 100 USD USD
100 USD = 100.00 USD (rate 1, 2026-07-18, identity)
```

```python
# Internal
convert(Decimal("100"), "USD", "COP", on=date(2024, 1, 15))
# → Decimal("392450")  (rate cached 3924.50, COP precision 0)
```

### Requirement: Conversion correctness

The system MUST convert via `Decimal` arithmetic only (no `float`), MUST quantize result to target-currency precision, MUST short-circuit same-currency without I/O, and MUST honor `--date` for historical rates.

#### Scenario: same-currency no I/O
- GIVEN any cache/network state
- WHEN `convert(Decimal("100"), "USD", "USD", on=today)`
- THEN result is `Decimal("100.00")`
- AND `transport.call_count == 0` AND `conn.execute.call_count == 0`

#### Scenario: historical uses cache when present
- GIVEN row `(date=2024-01-15, USD→COP, rate=3924.50)` exists
- WHEN `convert(Decimal("100"), "USD", "COP", on=date(2024,1,15))`
- THEN result is `Decimal("392450")`
- AND transport was never called

#### Scenario: CLI exit codes
- GIVEN `fin convert 50000 COP XYZ`
- WHEN executed
- THEN exit code is 1 (InvalidCurrency, validation stage)
- AND stderr contains `Invalid currency: XYZ`

- GIVEN Frankfurter returns 404 for `fin convert 50000 ABC USD`
- WHEN executed
- THEN exit code is 4 (RateNotFoundError)
- AND stderr contains `rate not found`

---

## Contract FX-4: Multi-currency report display (`--currency` flag)

### API surface

```python
# src/pyfintracker/reports.py (modified)
class MonthlyReport(BaseModel):
    year: int
    month: int
    currency: str                       # NEW: display currency
    income: list[MonthlyLine]
    expenses: list[MonthlyLine]
    net: Decimal
    rollup: bool

class BalanceReport(BaseModel):
    as_of: date | None
    currency: str                       # NEW: display currency
    lines: list[BalanceLine]
    net_worth: Decimal

def compute_monthly_report(conn, year_month: str, *,
                           display_currency: str = "COP") -> MonthlyReport: ...
def compute_balance(conn, *,
                    display_currency: str = "COP",
                    as_of: date | None = None) -> BalanceReport: ...

# src/pyfintracker/cli.py (modified)
@report_app.command("month")
def report_month(month: str = typer.Option("", "--month"),
                 currency: str = typer.Option("", "--currency", "-c",
                     help="Display currency (default from config)")) -> None: ...

@app.command()
def balance(currency: str = typer.Option("", "--currency", "-c",
                     help="Display currency (default from config)")) -> None: ...
```

### Validation rules
1. `--currency X` runs `validate_currency(X)` → `InvalidCurrency` (exit 1) on bad input.
2. If `--currency` empty → use `Settings.display_currency` (default `"COP"`, B2).
3. Every posting converted using rate effective on **transaction date** (`txn.date`) — not today's rate.
4. Converted postings aggregated per account after conversion; never summed across raw native currencies (D8 property test).
5. Output report header includes currency tag: `July 2026 (USD)`.
6. Sparkline, rollup, and ordering logic unchanged from Wave 1.

### Edge cases
- All postings same currency as `--currency` → conversion is identity (no FX cache fetch for those).
- Mixed-currency accounts (e.g. `Assets:COP:Nequi` + `Assets:USDC:Revolut`) → each posting converts to `display_currency` at its txn-date rate, then aggregates.
- Historical txn (e.g. 2024-01-15) + cache miss + network down → fall back per FX-5; if no stale cache, raise `FxUnavailableError` (exit 6).
- `BalanceReport.as_of` defaults to today; conversion uses txn-date rate (NOT as_of rate) — mark-to-market deferred (F3).
- Empty month/balance → existing Wave 1 behavior; `currency` still set on report.

### Testable claims
1. `compute_monthly_report(conn, "2026-07", display_currency="USD")` on a COP-only dataset converts every posting using `tx.date` rate; all converted amounts have USD precision (2 decimals).
2. `compute_monthly_report(conn, "2026-07", display_currency="USD")` on mixed-currency data produces a `MonthlyReport.net` whose absolute value is the same whether computed by single SQL join or by per-posting convert-then-aggregate (algebraic identity, ±0.01 USD rounding).
3. `compute_balance(conn, display_currency="EUR")` across 3+ account currencies returns `BalanceReport.net_worth` as a single `Decimal` in EUR.
4. `MonthlyReport.currency == "USD"` when called with `display_currency="USD"`; default is `"COP"`.
5. Property test (D8): scanning `reports.py` AST finds NO `Decimal.__add__` / `sum()` over postings where the posting currencies differ at the SQL level. (Test asserts: the SQL query joins `accounts` and reads `account.currency` per posting before aggregation.)
6. CLI `fin report month --month 2026-07 --currency USD` exits 0 on valid dataset; report header reads `July 2026 (USD)`.
7. CLI `fin balance --currency EUR` exits 0 and shows net worth footer in EUR, even when underlying accounts are mixed.
8. CLI with `--currency XYZ` (unknown) → exit 1, stderr `Invalid currency: XYZ`.

### DB impact
- Reads: `accounts`, `transactions`, `postings` (unchanged) + `rates` (new cache reads per posting row).
- Writes: none.
- New query pattern: `SELECT p.amount, p.currency, a.currency AS account_ccy, t.date FROM postings p JOIN accounts a ON ... JOIN transactions t ON ...` then convert in Python.

### Example

```bash
$ fin report month --month 2026-07 --currency USD
July 2026 (USD)            Income    Expense    Net
  Assets:USDC:Revolut         0.00   120.00  -120.00
  Assets:COP:Nequi          45.30     8.10    37.20
TOTAL                                  -82.80 USD

$ fin balance --currency EUR
Account                       Balance
  Assets:COP:Nequi         12,345,000 COP → 2,945.21 EUR
  Assets:USDC:Revolut           500.00 USD → 458.32 EUR
  ...
NET WORTH: 1,420.55 EUR  (5 accounts, 3 currencies, 2026-07-18)
```

### Requirement: Multi-currency report display

The system MUST convert each posting to `--currency` at the transaction-date rate before aggregation, MUST emit a single report-level `currency` field, and MUST never sum raw native `Decimal`s across different currencies.

#### Scenario: monthly report converts mixed currencies
- GIVEN 2 postings: `+50000 COP` on 2026-07-05, `-15 USD` on 2026-07-10
- AND cached rates `(USD→COP, 2026-07-05)` and `(USD→COP, 2026-07-10)` exist
- WHEN `fin report month --month 2026-07 --currency USD`
- THEN net section shows converted values in USD (each posting uses its own date's rate)
- AND header reads `July 2026 (USD)`

#### Scenario: balance net worth is single Decimal
- GIVEN 3 accounts in COP, USD, EUR with mixed balances
- WHEN `fin balance --currency EUR`
- THEN stdout prints `NET WORTH: <single Decimal> EUR`
- AND the `BalanceReport.net_worth` field is a `Decimal` (not a string with mixed currency)

#### Scenario: invalid currency rejected before any DB query
- GIVEN `--currency XYZ`
- WHEN CLI invokes report
- THEN exit code is 1
- AND `select * from rates` is NEVER called (verified via spy)

#### Scenario: same-currency display is identity
- GIVEN all postings are COP
- WHEN `fin report month --currency COP`
- THEN all amounts equal their native values byte-exact (verified against snapshot)

---

## Contract FX-5: Stale rate fallback

### API surface

```python
# src/pyfintracker/fx.py (extends FX-3)
def get_rate(from_ccy: str, to_ccy: str, on: date | None = None,
             *, allow_stale: bool = False) -> Rate: ...
# Internal flag; CLI commands translate warnings to stderr.
```

### Validation rules
1. **Latest rates** (`on=None`): cache hit iff `now - fetched_at <= 24h` → use cache; else call `fetch_latest`.
2. **Historical rates** (`on=date(...)`): cache hit regardless of age → use cache; never call `fetch_historical` if row present.
3. **Network failure on latest fetch + cache hit** (within 24h) → use cache, emit stderr warning, **no exception**.
4. **Network failure on latest fetch + cache miss** → `FxUnavailableError` (exit 6).
5. **Network failure on historical fetch + cache miss** → `FxUnavailableError` (exit 6). Historical NEVER falls back to stale: if a date is missing, fail clearly so reports cannot silently drift.
6. Warning format (stderr): `warning: using cached rate from 2026-07-18 14:23:01 (network unavailable)` — one line, prefixed `warning:`, contains fetched_at timestamp.
7. `allow_stale=False` is the default; no CLI flag exposes this in Wave 2A (F7).

### Edge cases
- Cache row exists but `rate = 0` or negative → treated as cache miss (FX-1 rule 3) AND provider bug logged.
- `fetched_at` is `NULL` (Wave 1 rows, expected: zero) → treated as oldest possible; for latest, always cache miss.
- Clock skew: `fetched_at` in the future → cache hit (do not penalize).
- Network returns 200 but with malformed JSON → `FxUnavailableError`, cache NOT updated.
- Provider returns 5xx → `FxUnavailableError`, cache NOT updated (no overwrite with garbage).
- `convert()` invoked from `fin convert` vs from report path: same `get_rate` semantics; warning emission is the caller's responsibility (CLI prints to stderr; reports print `[yellow]⚠[/yellow] cached rate` line).

### Testable claims
1. `get_rate("USD", "COP", on=None)` with cache row whose `fetched_at = now - 23h` → returns cache, transport called 0 times.
2. `get_rate("USD", "COP", on=None)` with cache row whose `fetched_at = now - 25h` → calls `fetch_latest`, returns fresh row (cache updated).
3. `get_rate("USD", "COP", on=None)` with cache hit + transport raising `ConnectError` → returns cache row, emits exactly one stderr line matching `^warning: using cached rate from \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \(network unavailable\)$`.
4. `get_rate("USD", "COP", on=None)` with cache miss + transport raising `ConnectError` → raises `FxUnavailableError` (exit 6).
5. `get_rate("USD", "COP", on=date(2024,1,15))` with cache row 5 years old → returns cache (historical never stale).
6. `get_rate("USD", "COP", on=date(2024,1,15))` with cache miss + transport raising `ConnectError` → raises `FxUnavailableError`; never uses today's rate as substitute.
7. CLI `fin convert 100 USD COP` with stale cache + network down → exits 0 (success), prints conversion line + warning on stderr.
8. CLI `fin convert 100 USD COP` with empty cache + network down → exits 6, prints `FxUnavailableError: ...` panel.
9. Report path: `fin report month` with stale cache + network down + same-currency postings → succeeds without warning (no FX call issued).
10. Report path: `fin report month` with stale cache + network down + mixed-currency postings → exits 6, yellow panel.

### DB impact
- Reads: `rates` (cache lookup; unchanged from FX-1).
- Writes: `rates` (cache fill on successful fetch, unchanged).

### Example

```bash
# Frankfurter down, cache has USD→COP from 2026-07-18 09:00
$ fin convert 100 USD COP
100 USD = 325,556 COP (rate 3255.56, 2026-07-18, frankfurter)
# stderr: warning: using cached rate from 2026-07-18 09:00:00 (network unavailable)

# Frankfurter down, no cache for requested date 2024-01-15
$ fin convert 100 USD COP --date 2024-01-15
# stderr: Error: FX service unavailable and no cached rate for 2024-01-15
# exit 6
```

### Requirement: Stale rate fallback policy

The system MUST use cached latest rates within 24h on network failure (with stderr warning), MUST use cached historical rates regardless of age, and MUST fail clearly when no cache covers the requested date.

#### Scenario: latest fallback uses 24h-old cache
- GIVEN cache row `(USD→COP, rate=3255.56, fetched_at=now - 23h)`
- AND transport raises `ConnectError`
- WHEN `fin convert 100 USD COP`
- THEN stdout shows conversion
- AND stderr contains `warning: using cached rate from <timestamp>`
- AND exit code is 0

#### Scenario: historical fallback always uses cache
- GIVEN cache row `(USD→COP, date=2024-01-15, rate=3924.50, fetched_at=2 years ago)`
- AND transport raises `ConnectError`
- WHEN `fin convert 100 USD COP --date 2024-01-15`
- THEN stdout shows conversion using the 2-year-old rate
- AND exit code is 0
- AND no warning (historical is intentionally persistent)

#### Scenario: historical miss + network down fails clearly
- GIVEN NO cache row for 2024-01-15
- AND transport raises `ConnectError`
- WHEN `fin convert 100 USD COP --date 2024-01-15`
- THEN exit code is 6
- AND stderr contains `FxUnavailableError`
- AND the conversion is NEVER substituted with today's rate

#### Scenario: provider 5xx never overwrites cache
- GIVEN cache row `(USD→COP, fetched_at=now - 1h)`
- AND transport returns 503
- WHEN `fin convert 100 USD COP`
- THEN cache row is unchanged in DB (verified by SELECT after)
- AND the user gets a fresh fetch attempt; on failure, falls back per the 24h rule

---

## Test Pyramid (per contract)

| Contract | Unit | Integration | Property (hypothesis) | Snapshot (syrupy) |
|---|---|---|---|---|
| **FX-1** (Rate + cache) | `Rate.to_row`/`from_row`; `upsert_rate` idempotency via in-memory SQLite; inverse lookup arithmetic | real-DB roundtrip via `make_test_engine()`; index existence assertion via `PRAGMA index_info` | ∀Decimal: `Rate.to_row → from_row` byte-exact; ∀allowlisted pair: cache hit returns same rate | — |
| **FX-2** (Frankfurter client) | mock httpx transport per scenario (success / 404 / 422 / future / malformed / 5xx / network) | real-DB `upsert_rate` from client response; cache fill flow | ∀response payload: `rate` field parsed via `Decimal(str(raw))` — never `float`; ∀status code: correct exception subclass | — |
| **FX-3** (convert) | `convert` pure arithmetic with injected `get_rate` stub; same-currency no-I/O assertion (transport/conn spies); rounding edge cases | CliRunner `fin convert` happy + error paths; cache hit vs miss via mocks | ∀Decimal × allowlisted pair: result quantized to target precision (e.g. COP→0, USD→2); ∀amount × ccy: identity when from==to | CLI output format: `fin convert 50000 COP USD` baseline |
| **FX-4** (report display) | `compute_monthly_report` + `compute_balance` with injected `fx.get_rate` stub returning known rates; per-posting convert-before-aggregate | CliRunner `fin report month --currency USD` and `fin balance --currency EUR` on seeded mixed-currency DB; cache fill on first conversion | ∀mixed posting set: `sum(raw) != raw_net_worth` is impossible — algebraic identity ±target precision; AST scan of `reports.py` for cross-currency `+` (D8) | full Rich output per scenario: monthly USD, balance EUR, monthly COP (identity) |
| **FX-5** (fallback) | `get_rate` with mocked clock + transport raising/returning per scenario; TTL boundary test (23h vs 25h) | CliRunner `fin convert` with cache + transport down | ∀cache row with `now - fetched_at < 24h`: transport called 0 times on latest; ∀historical: TTL ignored | CLI outputs with/without warning line |

**Coverage targets** (Wave 2A addition to Wave 1): 95%+ on `fx.py`; 90%+ on `repository.py` (new rate functions); 90%+ on `reports.py` (modified convert path). pytest-cov enforcement unchanged at 70% global.

**Property tests required** (Wave 2A):
1. `∀ Decimal × allowlisted pair: convert quantizes to target precision` — FX-3.
2. `∀ Decimal → Decimal roundtrip via Rate.to_row → from_row → Decimal == original` — FX-1.
3. `∀ mixed posting set: sum of converted amounts == report net` — FX-4.
4. `∀ historical rate request: TTL ignored, cache hit regardless of age` — FX-5.
5. `∀ Frankfurter response: rate field never enters float pipeline` — FX-2 (AST scan + property).

**No-float guard extended**: `tests/unit/test_no_float_amounts.py` must scan `fx.py` and `reports.py` in addition to Wave 1 modules. Pre-commit gate.

---

## Non-Goals (explicit F1–F9 exclusions)

- **F1.** Cross-currency postings within one transaction (deferred to Wave 2B). Each txn stays single-currency; `transactions.currency` is dominant posting currency (B4).
- **F2.** Auto-generated `Equity:FXConversion` synthetic posting for rounding residuals (Wave 2B). A non-zero residual currently rejects; Wave 2A keeps that.
- **F3.** Mark-to-market revaluation, unrealized FX gains/losses, period-end revaluation entries. Reports use txn-date rate; balance uses txn-date rate. No "as-of valuation" semantics.
- **F4.** All 201 Frankfurter v2 currencies. Curated 12 (B3). Adding a currency requires `PER_CURRENCY_DECIMALS` entry.
- **F5.** Provider pinning (ECB, Fed, etc.). Default blended; `Rate.source` records the tag for future use but no UI.
- **F6.** Bulk historical sync / time-series import. Cache fills lazily on miss.
- **F7.** Explicit `--offline` / `--allow-stale` flag. Stale fallback is implicit-on-failure only (FX-5). CLI surfaces warnings but offers no opt-in.
- **F8.** Rate triangulation through USD/EUR. If `X→Y` is not cached and `Y→X` is not cached, fail (FX-1 B5). Never compose.
- **F9.** FX fee/spread modeling. Raw provider rate only.

---

## Cross-cutting Acceptance (mapped to proposal §"Acceptance Criteria")

| Proposal criterion | Spec coverage |
|---|---|
| `fin convert 50000 COP USD` returns Decimal result with effective date | FX-3 claim 6, scenario "historical uses cache" |
| `--date 2024-01-15` uses historical rate, never today's | FX-3 claim 5, FX-5 scenario "historical fallback always uses cache" |
| Cache hit returns identical Decimal without network | FX-3 claim 4 (transport spy), FX-5 claim 1 |
| 404 → exit 4; 422 → exit 5 | FX-2 error-mapping table, FX-2 scenarios |
| Stale latest cache + Frankfurter down → exit 0 with stderr warning | FX-5 scenario "latest fallback uses 24h-old cache" |
| `fin report month --currency USD` converts via txn date | FX-4 claim 1, scenario "monthly report converts mixed currencies" |
| Mixed-currency accounts never summed raw (property test) | FX-4 claim 5 (D8 AST scan + property 3) |
| `fin balance --currency EUR` outputs single net-worth Decimal | FX-4 claim 3, scenario "balance net worth is single Decimal" |
| Migration 0002 upgrades existing DB without data loss | FX-1 DB impact table; covered by Wave 1 `tests/integration/test_migrations.py` extended for 0002 |
| `Rate` roundtrips via `to_row`/`from_row` | FX-1 claim 1, scenario "upsert idempotent" |
| All money paths 100% Decimal | FX-2 claim 2, FX-3 claim 1, no-float AST scan extended |

---

## Risks (spec-phase)

| # | Risk | Mitigation |
|---|---|---|
| **R1** | Curated allowlist (12 currencies) blocks user adding their own. | Document in `fin account new` help text; FX-1 B3; adding a currency is one-line + tests. |
| **R2** | `transactions.currency` backfill (B4) picks wrong currency if Wave 1 data ever had mixed postings (it shouldn't). | Migration only backfills when postings have a unique dominant currency; otherwise leaves `"COP"` and logs a warning. |
| **R3** | Rate inversion arithmetic loses precision (COP→USD at `0.000307` → 1/0.000307 = 3257.32...). | Quantize inverted rate to source-currency precision per FX-1 inverse rule; property test asserts inversion is `Decimal` exact. |
| **R4** | Frankfurter API change (v3?) breaks FX-2. | All API interaction isolated to `FrankfurterClient`; tests assert endpoint paths; pinning `BASE_URL` in D1 makes changes loud. |
| **R5** | `--currency` on `fin balance` runs N+1 rate lookups for N accounts. | `compute_balance` groups postings by (date, currency) tuple, looks up rate once per group. Tested with seeded DB. |
| **R6** | Stale-fallback policy masks real provider outages for users. | Stderr warning is loud; FX-5 claim 3 asserts format; future `--strict` flag (F7) is one line away. |
| **R7** | `Account.currency` schema has 5-currency `CHECK` from Wave 1 — Wave 2A accounts can declare USD/EUR/GBP/JPY but adding CAD/AUD/CHF/MXN/BRL/INR/CNY requires schema migration. | Migration 0003 (separate from 0002 if size > 400 lines) widens the CHECK; FX-1 B3 lists the 12 allowlist codes. |
| **R8** | The "Frankfurter returns 200 `[]` for future date" behavior is undocumented; spec might be wrong. | FX-2 claim 6 + scenario assert this; if provider changes, contract surfaces the regression in tests. |

---

## Constraints honoured

- Wave 1 double-entry invariant preserved: each txn is single-currency; each posting equals its account's currency; `sum(postings) == 0` per currency.
- `Decimal`-only money pipeline: all FX arithmetic is `Decimal`; no `float` ever enters `fx.py`, `reports.py`, or `repository.py`.
- Money columns remain `TEXT` (`DecimalAsText`); migration 0002 only adds columns to `rates` and `transactions`, never alters money columns.
- Atomicity unchanged: reports are read-only; `upsert_rate` is idempotent; no new transaction boundaries needed.
- CLI exit codes extended but not broken: 0/1/2/3/130 semantics preserved; new 4/5/6 only emitted by FX paths.
- Test pyramid: unit / integration / property / snapshot. Same conventions as Wave 1.
- Backward compatibility: Wave 1 commands and outputs unchanged when no `--currency` flag is given. Default `display_currency = "COP"` keeps existing CLI behavior identical.