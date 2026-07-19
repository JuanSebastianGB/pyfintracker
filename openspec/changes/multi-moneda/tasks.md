---
type: tasks
id: multi-moneda-tasks
status: draft
tags: [python, cli, finance, fx, multi-currency, frankfurter, tasks, wave-2]
parent_proposal: multi-moneda
parent_spec: multi-moneda-spec
parent_design: multi-moneda-design
parent_tasks: null
---

# Tasks — multi-moneda (Wave 2A)

Source of truth: engram obs `anvil/multi-moneda/tasks`. This file is the filesystem mirror.

## Work-unit etiquette

Per preflight: `artifact_store.mode=both` (engram + openspec), `execution_mode=interactive`, `tdd_mode=strict`, `delivery_strategy=force-chained`, `review_budget=800`. Every implementation task follows **red → green → refactor**. Each task declares `preflight` (default `[]`), `test_cycle` (one of `standard|tdd`, defaults to `tdd`), `quality_gates` (default `[]`). Available per `openspec/config.yaml` `testing_capabilities`: `test_cycle=tdd` available, `quality_gates=[property-based]` available, no preflight (additive to existing Wave 1 greenfield). FX arithmetic is the money pipeline → all FX tasks get `property-based` gate where hypothesis strategies apply.

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~1,620 (5 PRs × ~324 avg) |
| 400-line budget risk | **Low** per PR — each PR scoped ≤400; total well under 800-line cap |
| Chained PRs recommended | **Yes** (5-PR chain, design §12) |
| Suggested split | PR A → PR B → PR C → PR D → PR E |
| Delivery strategy | force-chained PRs (preflight cached) |
| Chain strategy | stacked-to-main (simple, fast) |

```text
Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low
```

---

## PR A — Schema + Rate model + migration + allowlist · `feat/A-fx-schema` · target ≤340 lines

**Goal**: Land the data layer first — widen account currency allowlist (5 → 12), add `transactions.currency` (B4), add `rates.fetched_at` TTL column + lookup index (FX-1), create `Rate` dataclass + repo fns, rename `default_currency` → `display_currency` (B2). No HTTP, no CLI surfaces beyond `config_show` update. **Scope**: `validation.py` (extend `PER_CURRENCY_DECIMALS`), `models.py` (`Rate`), `exceptions.py` (3 new), `repository.py` (4 new fns), `config.py` (rename + deprecation), `cli.py` (`config_show`), `migrations/versions/0002_multi_currency_schema.py`, tests. **Deps**: none (Wave 1 merged). **Tests**: `tests/unit/test_models.py`, `tests/unit/test_validation.py`, `tests/unit/test_exceptions.py`, `tests/unit/test_config.py`, `tests/integration/test_migrations.py`, `tests/integration/test_rates_repo.py`.

**Work-unit commit sequence**: `[T-A.1 red] [T-A.1 green] [T-A.2 red] [T-A.2 green] [T-A.3 red] [T-A.3 green] [T-A.4 red] [T-A.4 green] [T-A.5 red] [T-A.5 green] [T-A.6 red] [T-A.6 green] [T-A.7 red] [T-A.7 green] [refactor commit]`.

```yaml
- id: T-A.1
  title: Extend PER_CURRENCY_DECIMALS to 12 currencies (B3: COP, USD, EUR, GBP, JPY, CAD, AUD, CHF, MXN, BRL, INR, CNY)
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: assert PER_CURRENCY_DECIMALS['CAD'] missing → KeyError; green: add 7 entries; refactor: tuple ordering matches spec §B3}
  files_touched: [src/pyfintracker/validation.py]
  tests_added: [tests/unit/test_validation.py::test_per_currency_decimals_extended_to_12]
  depends_on: []
  acceptance: "All 12 currencies present with correct minor units (CAD/AUD/CHF/MXN/BRL/INR/CNY=2; COP/JPY=0)."
  risks: "Existing callsite to PER_CURRENCY_DECIMALS[c] must not regress for the original 5."

- id: T-A.2
  title: Add Rate frozen dataclass (id, date, from_ccy, to_ccy, rate, fetched_at, source) + to_row/from_row
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: Rate.rate accepts float → fail; green: dataclass(frozen=True, slots=True) with Decimal type; refactor: from_row Mapping[str, Any]}
  files_touched: [src/pyfintracker/models.py]
  tests_added: [tests/unit/test_models.py::test_rate_construction, ::test_rate_to_from_row_roundtrip]
  depends_on: [T-A.1]
  acceptance: "Rate.to_row→from_row preserves all 7 fields byte-exact; rate is Decimal (never float)."
  risks: "Schema uses base_currency/target_currency; Python uses from_ccy/to_ccy — map explicitly in to_row."

- id: T-A.3
  title: Add 3 FX exceptions: RateNotFoundError (code=4), InvalidCurrencyError (code=5, FX-context), FxUnavailableError (code=6)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: assert FxUnavailableError().code==6 → fail; green: subclass FinanceError with code attr; refactor: __all__ updated}
  files_touched: [src/pyfintracker/exceptions.py]
  tests_added: [tests/unit/test_exceptions.py::test_fx_exception_codes]
  depends_on: [T-A.1]
  acceptance: "All 3 classes import; each has `code` matching FX-2 error-mapping table."
  risks: "Existing InvalidCurrency (exit 1) stays distinct from new InvalidCurrencyError (exit 5)."

- id: T-A.4
  title: repository.{get_cached_rate, upsert_rate, list_cached_rates, get_rate_at_date} — SQL with idempotency on (date, base, target)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: second upsert_rate creates 2nd row → fail; green: INSERT...ON CONFLICT...DO UPDATE; refactor: shared _row_to_rate helper}
  files_touched: [src/pyfintracker/repository.py]
  tests_added: [tests/integration/test_rates_repo.py::test_upsert_idempotent, ::test_get_cached_rate_hit, ::test_inverse_lookup_via_direct_only, ::test_list_cached_rates]
  depends_on: [T-A.2, T-A.3]
  acceptance: "Upsert twice = 1 row; get_cached_rate returns stored Rate; inverse lookup raises (caller does inversion, repo is direct-only)."
  risks: "SQLite UPSERT requires SQLite ≥ 3.24; bump `sqlite3.sqlite_version` assertion in conftest."

- id: T-A.5
  title: Hand-write 0002_multi_currency_schema.py — transactions.currency + rates.fetched_at + idx_rates_lookup + accounts CHECK widening (12-currency)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: upgrade→downgrade→upgrade cycle fails on missing idx; green: paste DDL from design §4; refactor: extract _widen_accounts_check helper}
  files_touched: [migrations/versions/0002_multi_currency_schema.py]
  tests_added: [tests/integration/test_migrations.py::test_migration_0002_roundtrip, ::test_backfill_dominant_currency, ::test_accounts_check_widened]
  depends_on: [T-A.4]
  acceptance: "alembic upgrade→downgrade→upgrade idempotent; transactions.currency backfilled from dominant posting; idx_rates_lookup exists via PRAGMA index_info."
  risks: "Accounts CHECK widening uses SQLite recreate-table dance; existing Wave 1 starter chart rows must survive."

- id: T-A.6
  title: Rename Settings.default_currency → display_currency; FIN_DISPLAY_CURRENCY env; deprecation log on old TOML key (B2)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: Settings().display_currency missing → fail; green: rename field, add load_settings migration shim; refactor: helper _emit_currency_deprecation}
  files_touched: [src/pyfintracker/config.py]
  tests_added: [tests/unit/test_config.py::test_display_currency_field, ::test_old_key_emits_deprecation_warning]
  depends_on: [T-A.1]
  acceptance: "Settings.display_currency default='COP'; TOML key `display_currency` reads; old key `default_currency` still loads + logs DeprecationWarning."
  risks: "Wave 1 callers of Settings().default_currency break — update callers in same PR (cli.config_show)."

- id: T-A.7
  title: Update cli.config_show to render display_currency field with source tag
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: snapshot missing display_currency line; green: replace default_currency line in panel; refactor: source_of() tag}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/integration/test_cli_config.py::test_config_show_lists_display_currency]
  depends_on: [T-A.6]
  acceptance: "`fin config show` includes line `display_currency: COP [default]` (or [file]/[env])."
```

---

## PR B — Frankfurter v2 client + cache + get_rate fallback · `feat/B-fx-client` · target ≤380 lines

**Goal**: Wire the HTTP + cache layer. Build `FrankfurterClient` (httpx MockTransport-driven), the module-level `fx.get_rate` orchestrator (cache → inverse → fetch → fallback), and TTL/staleness rules per FX-5. No CLI surface beyond internal use. **Scope**: `src/pyfintracker/fx.py` (full module), extension of `tests/unit/test_fx_client.py`, `tests/integration/test_fx_cache.py`. **Deps**: PR A. **Tests**: unit (mock httpx), integration (real-DB cache + mocked transport).

**Work-unit commit sequence**: `[T-B.1 red] [T-B.1 green] [T-B.2 red] [T-B.2 green] [T-B.3 red] [T-B.3 green] [T-B.4 red] [T-B.4 green] [T-B.5 red] [T-B.5 green] [T-B.6 red] [T-B.6 green] [T-B.7 red] [T-B.7 green] [T-B.8 red] [T-B.8 green] [T-B.9 red] [T-B.9 green] [T-B.10 red] [T-B.10 green] [T-B.11 red] [T-B.11 green] [refactor commit]`.

```yaml
- id: T-B.1
  title: fx.FrankfurterClient skeleton (BASE_URL pinned, DEFAULT_TIMEOUT, __init__ with transport injection)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: import FrankfurterClient fails; green: declare class with pinned BASE_URL; refactor: extract BASE_URL constant test}
  files_touched: [src/pyfintracker/fx.py]
  tests_added: [tests/unit/test_fx_client.py::test_base_url_pinned_to_v2]
  depends_on: [T-A.3]
  acceptance: "FrankfurterClient().BASE_URL == 'https://api.frankfurter.dev/v2'; transport injectable."

- id: T-B.2
  title: FrankfurterClient.fetch_latest — calls GET /v2/rate/{from}/{to}, parses Decimal(str(rate)), maps 404/422/network to FX-2 table
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: mock returns 200 → returns None; green: parse JSON, return Rate; refactor: helper _raise_for_status}
  files_touched: [src/pyfintracker/fx.py]
  tests_added: [tests/unit/test_fx_client.py::test_fetch_latest_parses_decimal, ::test_fetch_latest_404_raises_RateNotFoundError, ::test_fetch_latest_422_invalid_currency_raises_InvalidCurrencyError, ::test_fetch_latest_connect_error_raises_FxUnavailableError]
  depends_on: [T-B.1]
  acceptance: "Rate.rate is Decimal (not float); 404→RateNotFoundError(code=4); 422 invalid currency→InvalidCurrencyError(code=5); ConnectError→FxUnavailableError(code=6) after ≤1 retry."

- id: T-B.3
  title: FrankfurterClient.fetch_historical — passes date query param; treats 200 [] as RateNotFoundError
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: empty 200 raises FxUnavailableError; green: map [] to RateNotFoundError; refactor: helper _parse_response}
  files_touched: [src/pyfintracker/fx.py]
  tests_added: [tests/unit/test_fx_client.py::test_fetch_historical_empty_array_raises_RateNotFoundError, ::test_fetch_historical_uses_effective_date]
  depends_on: [T-B.2]
  acceptance: "Future date 2099-01-01 with 200[] → RateNotFoundError (NOT FxUnavailableError); rate.date is API's effective date."

- id: T-B.4
  title: FrankfurterClient.list_currencies — GET /v2/currencies, returns dict[str, str]
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: returns None; green: dict comprehension over JSON; refactor: none}
  files_touched: [src/pyfintracker/fx.py]
  tests_added: [tests/unit/test_fx_client.py::test_list_currencies_returns_dict]
  depends_on: [T-B.2]
  acceptance: "Mock returns {USD: 'United States Dollar', COP: 'Colombian Peso', ...}; client returns same dict."

- id: T-B.5
  title: fx.list_supported_currencies() — frozenset intersection of PER_CURRENCY_DECIMALS keys
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: import fails; green: return frozenset(PER_CURRENCY_DECIMALS); refactor: __all__ exposes symbol}
  files_touched: [src/pyfintracker/fx.py]
  tests_added: [tests/unit/test_fx_client.py::test_list_supported_currencies_is_frozenset_of_12]
  depends_on: [T-A.1]
  acceptance: "frozenset with exactly 12 ISO codes; matches PER_CURRENCY_DECIMALS keys."

- id: T-B.6
  title: fx.get_rate cache-hit fast path + same-currency identity (no I/O)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: same-currency calls transport → fail; green: from==to returns Decimal('1') Rate; refactor: cache check via get_cached_rate}
  files_touched: [src/pyfintracker/fx.py]
  tests_added: [tests/integration/test_fx_cache.py::test_get_rate_same_currency_no_io, ::test_get_rate_cache_hit_uses_stored_row]
  depends_on: [T-A.4, T-B.1]
  acceptance: "from==to returns Rate(rate=Decimal('1')) with 0 transport calls + 0 conn.execute calls; cache hit returns stored Rate, 0 transport calls."

- id: T-B.7
  title: fx.get_rate inverse lookup — 1/rate quantized to PER_CURRENCY_DECIMALS[from_ccy]
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: inverse not attempted; green: query cache for (to_ccy, from_ccy, on); refactor: helper _invert_rate}
  files_touched: [src/pyfintracker/fx.py]
  tests_added: [tests/integration/test_fx_cache.py::test_get_rate_inverse_lookup]
  depends_on: [T-B.6]
  acceptance: "GIVEN row (date=D, COP→USD=0.000307) WHEN get_rate('USD','COP',on=D) THEN rate ≈ Decimal('3257') (quantized to COP precision 0)."

- id: T-B.8
  title: fx.get_rate cache miss → fetch via FrankfurterClient → upsert cache (TTL check via fetched_at)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: cache miss + transport down → propagates FxUnavailableError; green: call fetch_latest, upsert; refactor: helper _fetch_and_cache}
  files_touched: [src/pyfintracker/fx.py]
  tests_added: [tests/integration/test_fx_cache.py::test_get_rate_miss_calls_fetch_latest_and_caches, ::test_get_rate_23h_old_cache_reused, ::test_get_rate_25h_old_cache_refreshed]
  depends_on: [T-B.6]
  acceptance: "Cache miss triggers fetch_latest exactly once; upsert writes new row; 23h-old cache reused (0 transport); 25h-old cache triggers refresh."

- id: T-B.9
  title: fx.get_rate stale-fallback warning emission (stderr line format per FX-5 rule 6)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: network down + cache hit → raises FxUnavailableError; green: return cache, logging.warning(...); refactor: helper _warn_stale}
  files_touched: [src/pyfintracker/fx.py]
  tests_added: [tests/integration/test_fx_cache.py::test_stale_cache_fallback_warns_on_stderr, ::test_stale_cache_fallback_format_regex]
  depends_on: [T-B.8]
  acceptance: "Cache hit + transport raises ConnectError → returns cache + emits exactly one stderr line matching `^warning: using cached rate from \\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2} \\(network unavailable\\)$`."

- id: T-B.10
  title: fx.get_rate historical cache-TTL-ignored + future-date rejection + 5xx no-overwrite
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: 2-year-old historical triggers fetch; green: TTL skipped for on=date(...); refactor: branch on on is None}
  files_touched: [src/pyfintracker/fx.py]
  tests_added: [tests/integration/test_fx_cache.py::test_historical_cache_used_regardless_of_age, ::test_future_date_rejected_before_network, ::test_5xx_does_not_overwrite_cache]
  depends_on: [T-B.8]
  acceptance: "Historical row 5 years old → used; on>date.today() → RateNotFoundError (NOT FxUnavailableError); 503 response does NOT upsert (cache row unchanged)."

- id: T-B.11
  title: Integration — fx.get_rate end-to-end on real in-memory SQLite + MockTransport (cache fill + reuse)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: second call refetches; green: cache row inserted on first; refactor: parametrize latest vs historical}
  files_touched: [tests/integration/test_fx_cache.py]
  tests_added: [tests/integration/test_fx_cache.py::test_get_rate_cache_fill_roundtrip]
  depends_on: [T-B.10]
  acceptance: "First call: 1 transport hit, row in rates table. Second call: 0 transport hits, identical Rate returned."
```

---

## PR C — `fin convert` + internal `convert` + tests · `feat/C-fx-convert` · target ≤280 lines

**Goal**: Surface FX to the CLI. Pure `convert(amount, from, to, on)` with quantization + identity fast-path; `fin convert <amount> <from> <to> [--date]` Typer command with formatted stdout + stderr warning surfacing. Snapshot baseline for output format. **Scope**: `src/pyfintracker/fx.py` (`convert`), `src/pyfintracker/cli.py` (`convert` command), `tests/integration/test_convert_cli.py`, `tests/snapshots/test_convert_snap.py`. **Deps**: PR B. **Tests**: unit + integration + syrupy snapshot.

**Work-unit commit sequence**: `[T-C.1 red] [T-C.1 green] [T-C.2 red] [T-C.2 green] [T-C.3 red] [T-C.3 green] [T-C.4 red] [T-C.4 green] [T-C.5 red] [T-C.5 green] [T-C.6 red] [T-C.6 green] [T-C.7 red] [T-C.7 green] [refactor commit]`.

```yaml
- id: T-C.1
  title: fx.convert pure Decimal arithmetic — multiply × rate, quantize to PER_CURRENCY_DECIMALS[to_ccy], ROUND_HALF_UP
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: COP 100.456 quantizes to 100 (not 101); green: amount * rate, .quantize; refactor: extract _apply_rate helper}
  files_touched: [src/pyfintracker/fx.py]
  tests_added: [tests/unit/test_fx_client.py::test_convert_quantizes_per_currency, ::test_convert_negative_amount_allowed]
  depends_on: [T-B.6]
  acceptance: "convert(Decimal('1234.567'),'USD','COP',on=D) with rate=3255.56 → Decimal('4021187') (0 decimals); negative amount returns negative quantized result."

- id: T-C.2
  title: fx.convert same-currency fast-path (quantize only, no I/O via transport+conn spies)
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: same-ccy calls transport; green: return quantize_for_currency; refactor: guard at top of convert}
  files_touched: [src/pyfintracker/fx.py]
  tests_added: [tests/unit/test_fx_client.py::test_convert_same_currency_no_io]
  depends_on: [T-C.1]
  acceptance: "convert(Decimal('100'),'USD','USD') returns Decimal('100.00'); transport.call_count==0 AND conn.execute.call_count==0."

- id: T-C.3
  title: fx.convert historical uses cached rate when present (transport spy 0)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: cache hit still calls fetch; green: get_rate returns cached; refactor: none}
  files_touched: [src/pyfintracker/fx.py]
  tests_added: [tests/integration/test_convert_cli.py::test_convert_historical_cache_no_network]
  depends_on: [T-C.1]
  acceptance: "GIVEN row (USD→COP 2024-01-15=3924.50) WHEN convert(100,USD,COP,on=date(2024,1,15)) THEN transport called 0 times, result=Decimal('392450')."

- id: T-C.4
  title: fx.convert validate_currency runs at boundary; unknown raises InvalidCurrency (exit 1) before any FX call
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: 'XYZ' reaches get_rate; green: validate_currency guard; refactor: helper _validate_pair}
  files_touched: [src/pyfintracker/fx.py]
  tests_added: [tests/unit/test_fx_client.py::test_convert_unknown_currency_raises_before_io]
  depends_on: [T-C.1]
  acceptance: "convert(Decimal('100'),'XYZ','USD') raises InvalidCurrency (exit 1) without touching transport or conn."

- id: T-C.5
  title: cli.convert command — Typer args (amount, from_ccy, to_ccy, --date); validate_amount + validate_date
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: CliRunner invoke(['convert']) empty; green: wire args; refactor: helper _print_convert_line}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/integration/test_convert_cli.py::test_convert_cli_happy_path, ::test_convert_cli_invalid_amount_exits_1]
  depends_on: [T-C.1]
  acceptance: "`fin convert 50000 COP USD` exits 0; `fin convert abc COP USD` exits 1 with stderr `Invalid amount: abc`."

- id: T-C.6
  title: cli.convert output format snapshot — pinned to `50000 COP = 15.36 USD (rate 0.000307, 2026-07-18, frankfurter)`
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: snapshot missing; green: format helper + snapshot; refactor: _format_convert_line}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/snapshots/test_convert_snap.py::test_convert_output_format]
  depends_on: [T-C.5]
  acceptance: "Syrupy snapshot pinned; deterministic on re-run; matches FX-3 claim 6 format exactly."

- id: T-C.7
  title: Integration — fin convert with cached historical rate + network down (FX-5 claim 7)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: cache hit + net down exits 6; green: cache used, exit 0; refactor: parametrize latest vs historical}
  files_touched: [tests/integration/test_convert_cli.py]
  tests_added: [tests/integration/test_convert_cli.py::test_convert_cached_latest_falls_back, ::test_convert_historical_cache_always_used]
  depends_on: [T-C.5]
  acceptance: "Cached historical (5y old) + network down → exit 0, conversion printed, no warning (historical is intentionally persistent)."
```

---

## PR D — `compute_*` reports with `--currency` + CLI flags · `feat/D-fx-reports` · target ≤360 lines

**Goal**: Mixed-currency reports. `compute_monthly_report` and `compute_balance` accept `display_currency`; group postings by `(date, currency)` and convert before aggregation; emit currency tag in header/footer; add `--currency` flag to `fin report month` and `fin balance`. **Scope**: `src/pyfintracker/reports.py` (modify compute_*, add `currency` field to MonthlyReport + BalanceReport, render currency tag), `src/pyfintracker/cli.py` (`--currency` flag on report month + balance), `tests/integration/test_reports_multi_currency.py`. **Deps**: PR C. **Tests**: unit + integration + snapshot.

**Work-unit commit sequence**: `[T-D.1 red] [T-D.1 green] [T-D.2 red] [T-D.2 green] [T-D.3 red] [T-D.3 green] [T-D.4 red] [T-D.4 green] [T-D.5 red] [T-D.5 green] [T-D.6 red] [T-D.6 green] [T-D.7 red] [T-D.7 green] [T-D.8 red] [T-D.8 green] [T-D.9 red] [T-D.9 green] [T-D.10 red] [T-D.10 green] [refactor commit]`.

```yaml
- id: T-D.1
  title: Add `currency: str` field to MonthlyReport + BalanceReport (FX-4 rule 5)
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: model_validate fails without field; green: declare currency field with default 'COP'; refactor: validator upper-case}
  files_touched: [src/pyfintracker/reports.py]
  tests_added: [tests/unit/test_reports.py::test_monthly_report_currency_field, ::test_balance_report_currency_field]
  depends_on: [T-A.1]
  acceptance: "MonthlyReport.currency and BalanceReport.currency both default to 'COP'; settable via kwarg."

- id: T-D.2
  title: compute_monthly_report(conn, year_month, *, display_currency='COP') — same-currency identity fast path
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: signature missing kwarg; green: add display_currency, group by (date, currency); refactor: helper _group_for_convert}
  files_touched: [src/pyfintracker/reports.py]
  tests_added: [tests/unit/test_reports.py::test_compute_monthly_same_currency_identity]
  depends_on: [T-D.1]
  acceptance: "COP-only data + display_currency='COP' → all converted amounts byte-equal native (verified against snapshot)."

- id: T-D.3
  title: compute_monthly_report mixed-currency convert-then-aggregate (FX-4 claim 1, claim 2)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: mixed COP+USD → raw sum; green: convert each group at t.date rate before aggregate; refactor: extract _convert_posting}
  files_touched: [src/pyfintracker/reports.py]
  tests_added: [tests/unit/test_reports.py::test_compute_monthly_mixed_currency_converts_via_txn_date, ::test_compute_monthly_algebraic_identity_mixed]
  depends_on: [T-D.2]
  acceptance: "Mixed postings (50000 COP on 2026-07-05 + -15 USD on 2026-07-10) + display_currency='USD' → each posting uses its own date's rate; algebraic identity holds ±0.01 USD."

- id: T-D.4
  title: compute_balance(conn, *, display_currency='COP', as_of=None) — txn-date conversion (NOT as_of), grouped rate lookups (R5)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: signature missing kwargs; green: add display_currency, group by (date, currency); refactor: helper _prefetch_rates}
  files_touched: [src/pyfintracker/reports.py]
  tests_added: [tests/unit/test_reports.py::test_compute_balance_signature_display_currency, ::test_compute_balance_uses_txn_date_not_as_of]
  depends_on: [T-D.1]
  acceptance: "as_of=date(2099,1,1) → postings still convert at t.date rate (NOT 2099); (date, currency) grouping collapses N postings to ≤N distinct rate lookups."

- id: T-D.5
  title: compute_balance mixed-currency net_worth is single Decimal in display_currency (FX-4 claim 3)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: [property-based]
  tdd_cycle: {red: mixed 3+ ccy returns raw sum; green: convert before sum; refactor: helper _sum_converted}
  files_touched: [src/pyfintracker/reports.py]
  tests_added: [tests/property/test_balance_mixed_currency.py, tests/integration/test_reports_multi_currency.py::test_compute_balance_three_currencies_single_decimal]
  depends_on: [T-D.4]
  acceptance: "3 accounts in COP/USD/EUR + display_currency='EUR' → BalanceReport.net_worth is single Decimal in EUR precision (2 decimals)."

- id: T-D.6
  title: cli.report_month — --currency flag with validate_currency FIRST (D7), defaults to Settings.display_currency
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: --currency ignored; green: parse + validate before any DB query; refactor: helper _resolve_display_currency}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/integration/test_reports_multi_currency.py::test_report_month_currency_flag, ::test_report_month_invalid_currency_no_db_query]
  depends_on: [T-D.3]
  acceptance: "`fin report month --month 2026-07 --currency USD` exits 0; header reads `July 2026 (USD)`; --currency XYZ exits 1 with stderr `Invalid currency: XYZ` and rates table NEVER queried (spy)."

- id: T-D.7
  title: cli.balance — --currency flag with same validate-first semantics
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: --currency missing on balance; green: add flag, validate first; refactor: extract _resolve_display_currency shared with report month}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/integration/test_reports_multi_currency.py::test_balance_currency_flag_euro]
  depends_on: [T-D.5]
  acceptance: "`fin balance --currency EUR` exits 0; footer reads `NET WORTH: <single Decimal> EUR`."

- id: T-D.8
  title: render_monthly_report + render_balance include currency tag in header/footer
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: header missing currency; green: render Panel title includes f\"({currency})\"; refactor: helper _format_header}
  files_touched: [src/pyfintracker/reports.py]
  tests_added: [tests/snapshots/test_reports_snap.py::test_render_monthly_currency_tag_usd, ::test_render_balance_currency_tag_eur]
  depends_on: [T-D.6, T-D.7]
  acceptance: "Syrupy snapshots pinned for monthly USD header and balance EUR footer; deterministic."

- id: T-D.9
  title: Integration — fin report month on seeded mixed-currency DB (FX-4 claim 6)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: cli on mixed DB fails; green: seed 2 COP + 2 USD postings in 2026-07; refactor: helper _seed_mixed_month}
  files_touched: [tests/integration/test_reports_multi_currency.py]
  tests_added: [tests/integration/test_reports_multi_currency.py::test_report_month_mixed_currency_cli]
  depends_on: [T-D.8]
  acceptance: "Seeded 50000 COP @ 2026-07-05 + -15 USD @ 2026-07-10 + cached rates → `fin report month --month 2026-07 --currency USD` exits 0, header `July 2026 (USD)`, net section shows USD values."

- id: T-D.10
  title: Integration — fin balance on 3-currency DB (FX-4 claim 7)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: balance 3-ccy sums raw; green: seed 3 accounts + cached rates; refactor: helper _seed_three_currency_chart}
  files_touched: [tests/integration/test_reports_multi_currency.py]
  tests_added: [tests/integration/test_reports_multi_currency.py::test_balance_three_currency_cli]
  depends_on: [T-D.8]
  acceptance: "Seeded COP + USD + EUR accounts + cached rates → `fin balance --currency EUR` exits 0, prints per-account converted lines + `NET WORTH: <single Decimal> EUR`."
```

---

## PR E — AST guard + property tests + pre-commit + cleanup · `feat/E-fx-hardening` · target ≤260 lines

**Goal**: Lock in the no-float + no-raw-currency-sum invariants, ship property-based coverage for FX-1/3/4/5, wire pre-commit hooks, update README, double-check migration idempotency. **Scope**: `tests/unit/test_no_raw_currency_sum.py` (D8), `tests/unit/test_no_float_amounts.py` (extend to fx.py), property tests, `.pre-commit-config.yaml`, `README.md`, final migration smoke. **Deps**: PR D. **Tests**: AST scan + property (hypothesis) + smoke.

**Work-unit commit sequence**: `[T-E.1 red] [T-E.1 green] [T-E.2 red] [T-E.2 green] [T-E.3 red] [T-E.3 green] [T-E.4 red] [T-E.4 green] [T-E.5 red] [T-E.5 green] [T-E.6 red] [T-E.6 green] [T-E.7 red] [T-E.7 green] [T-E.8 red] [T-E.8 green] [T-E.9 red] [T-E.9 green] [refactor commit]`.

```yaml
- id: T-E.1
  title: tests/unit/test_no_raw_currency_sum.py — AST scan of reports.py for cross-currency Decimal addition (D8)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: scan reports.py, no violations yet; green: walk AST BinOp(Add) heuristic; refactor: helper _is_posting_amount}
  files_touched: [tests/unit/test_no_raw_currency_sum.py]
  tests_added: [tests/unit/test_no_raw_currency_sum.py::test_no_raw_currency_sum_in_reports]
  depends_on: [T-D.3, T-D.5]
  acceptance: "AST scan finds zero `Decimal.__add__` of postings from different account currencies without convert; whitelist for `aggregated.get(...) + e[\"amount\"]` where e[\"amount\"] is already converted."

- id: T-E.2
  title: Extend tests/unit/test_no_float_amounts.py to scan fx.py (no float annotations/types in FX arithmetic)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: scan list missing fx.py; green: add to MODULES list; refactor: parametrize module list}
  files_touched: [tests/unit/test_no_float_amounts.py]
  tests_added: [tests/unit/test_no_float_amounts.py::test_no_float_in_fx]
  depends_on: [T-C.1]
  acceptance: "Scan reports zero `float` annotations/types in fx.py alongside existing models/validation/repository."

- id: T-E.3
  title: Property test — Rate.to_row → from_row → to_row byte-exact (FX-1 claim 1)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: [property-based]
  tdd_cycle: {red: counterexample at fetched_at datetime; green: st.decimals + st.dates; refactor: normalize UTC}
  files_touched: [tests/property/test_rate_roundtrip.py]
  tests_added: [tests/property/test_rate_roundtrip.py]
  depends_on: [T-A.2]
  acceptance: "∀ Rate(...) with hypothesis strategy: from_row(to_row(r)) == r for all 7 fields."

- id: T-E.4
  title: Property test — convert quantizes to target precision per pair (FX-3 claim 1)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: [property-based]
  tdd_cycle: {red: counterexample at COP precision; green: st.decimals × ccy st.sampled_from; refactor: helper _expected_decimals}
  files_touched: [tests/property/test_convert_quantization.py]
  tests_added: [tests/property/test_convert_quantization.py]
  depends_on: [T-C.1]
  acceptance: "∀ Decimal × 12 allowlisted pair: result has exactly PER_CURRENCY_DECIMALS[to_ccy] decimal places."

- id: T-E.5
  title: Property test — convert-then-aggregate algebraic identity (FX-4 claim 2)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: [property-based]
  tdd_cycle: {red: counterexample at scale; green: st.lists(postings) with known rates; refactor: helper _mixed_posting_strategy}
  files_touched: [tests/property/test_convert_aggregate_identity.py]
  tests_added: [tests/property/test_convert_aggregate_identity.py]
  depends_on: [T-D.3]
  acceptance: "∀ mixed posting set: convert-then-sum == sum-of-converted ±0.01 target precision."

- id: T-E.6
  title: Property test — historical rate TTL ignored (FX-5 claim 4)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: [property-based]
  tdd_cycle: {red: old historical re-fetches; green: cache row 1y-50y old used; refactor: st.datetimes for fetched_at}
  files_touched: [tests/property/test_historical_ttl.py]
  tests_added: [tests/property/test_historical_ttl.py]
  depends_on: [T-B.10]
  acceptance: "∀ historical cache row with age in [1y, 50y]: get_rate returns cache, transport called 0 times."

- id: T-E.7
  title: Pre-commit hook wiring — .pre-commit-config.yaml runs no-float + no-raw-currency-sum + ruff + mypy
  estimate: S
  preflight: []; test_cycle: standard; quality_gates: []
  tdd_cycle: {red: pre-commit not configured; green: write .pre-commit-config.yaml; refactor: stage both new tests}
  files_touched: [.pre-commit-config.yaml]
  tests_added: []
  depends_on: [T-E.1, T-E.2]
  acceptance: "`pre-commit run --all-files` exits 0; pytest runs no-float + no-raw-currency-sum as gates."

- id: T-E.8
  title: README updates — fin convert, --currency flag, exit codes 4/5/6, display_currency, B2 migration note
  estimate: S
  preflight: []; test_cycle: standard; quality_gates: []
  tdd_cycle: {red: README missing FX examples; green: add sections; refactor: extract _FX_EXAMPLES constant}
  files_touched: [README.md]
  tests_added: []
  depends_on: [T-D.10]
  acceptance: "README has sections: 'Multi-currency', 'FX rates', 'Converting', exit-code table includes 4/5/6, B2 deprecation note for old `default_currency` key."

- id: T-E.9
  title: End-to-end migration smoke — 0001 → 0002 → 0001 → 0002 idempotent on existing Wave 1 DB
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: 0002 downgrade loses transactions.currency; green: assert schema after each leg; refactor: parametrize over alembic revisions}
  files_touched: [tests/integration/test_migrations.py]
  tests_added: [tests/integration/test_migrations.py::test_0002_idempotent_roundtrip_with_wave1_data]
  depends_on: [T-A.5]
  acceptance: "Seed Wave 1 single-currency DB (11 accounts + 5 postings) → alembic upgrade 0002 (backfill) → downgrade 0001 → upgrade 0002 → no data loss, accounts.currency widened to 12."
```

---

## Constraints honoured

- **Money pipeline**: All FX arithmetic uses `Decimal`; no `float` ever enters `fx.py`/`reports.py`/`repository.py` (AST scan + 5 property tests; pre-commit enforced via T-E.2 + T-E.7).
- **Money columns**: Remain `TEXT` (DecimalAsText); migration 0002 only adds columns/indexes/CHECK widening, never alters money columns.
- **Wave 1 invariant preserved**: Each txn stays single-currency; each posting equals its account's currency; `sum(postings) == 0` per currency.
- **Migration 0002 additive**: `alembic downgrade -1` reverses cleanly (recreates accounts table, drops fetched_at via recreate-table dance); no destructive changes to Wave 1 schema.
- **Backward compatibility**: Wave 1 commands unchanged when no `--currency` flag given; default `display_currency="COP"` keeps existing CLI behavior identical.
- **CLI exit codes**: 0/1/2/3/130 semantics preserved; new 4/5/6 only emitted by FX paths.
- **Test pyramid**: unit (FX-2 mock transport, validation) + integration (real-DB + mocked HTTP) + property (hypothesis: FX-1 roundtrip, FX-3 quantization, FX-4 algebraic identity, FX-5 historical TTL, FX-2 no-float) + snapshot (syrupy: convert format, report headers).
- **Review budget**: 5 PRs × ≤400 lines each = ~1,620 total; each PR under 800-line review cap; reviewer cognitive load protected.
- **Strict TDD**: red → green → refactor per task; pre-commit hooks (T-E.7) gate the no-float + no-raw-currency-sum invariants so future changes can't regress.
- **B2 (display_currency rename)**: silent migration with DeprecationWarning log; one-line override path; FIN_DISPLAY_CURRENCY env var.
- **B5 (rate direction)**: Direct lookup + 1/rate inversion quantized to source precision; never triangulate through USD/EUR.
- **FX-5 fallback policy**: Latest 24h TTL with stderr warning; historical cached forever; historical miss + network down fails clearly (exit 6), never substitutes today's rate.