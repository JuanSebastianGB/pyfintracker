---
type: tasks
id: finance-tracker-tasks
status: archived
tags: [python, cli, finance, double-entry, sqlite, mvp, tasks]
parent_proposal: finance-tracker
parent_spec: finance-tracker-spec
parent_design: finance-tracker-design
parent_tasks: null
---

# Tasks — finance-tracker (Wave 1 MVP Estricto)

Source of truth: engram obs `anvil/finance-tracker/tasks`. This file is the filesystem mirror.

## Work-unit etiquette
Per preflight: `artifact_store.mode=engram`, `execution_mode=interactive`, `tdd_mode=strict`, `delivery_strategy=chained PRs`, `review_budget=standard`. Every implementation task follows **red → green → refactor**. Each task declares `preflight` (default `[]`), `test_cycle` (one of `standard|tdd`, defaults to `tdd`), `quality_gates` (default `[]`). Available per testing-capabilities (#1539): `test_cycle=tdd` only, `quality_gates=[property-based]` only. No preflight (greenfield).

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~2300 (7 PRs × ~330 avg) |
| 400-line budget risk | **Medium** per PR — each PR scoped ≤400; no PR crosses |
| Chained PRs recommended | **Yes** (7-PR chain, design §11) |
| Suggested split | PR1 → PR2 → PR3 → PR4 → PR5 → PR6 → PR7 |
| Delivery strategy | chained PRs (preflight cached) |
| Chain strategy | stacked-to-main (simple, fast) |

```text
Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium
```

---

## PR 1 — Skeleton · `feat/01-skeleton` · target ≤350 lines

**Status**: Batch 3/4 complete. T-1.1 through T-1.11 done; T-1.14, T-1.15, T-1.16 done. Remaining: T-1.12 (cli.init), T-1.13 (cli.migrate), T-1.17 (test_cli_init), T-1.18 (test_cli_migrate), T-1.19 (lint CI gate).

**Goal**: Boot the package: empty modules, SQLite engine + WAL, Alembic + 11-account chart, `Settings`, `init`/`version`/`migrate`. **Scope**: `src/pyfintracker/{__init__,py.typed,models,validation,repository,reports,cli,db,config,exceptions}.py`, `migrations/env.py`, `alembic.ini`, `migrations/versions/0001_initial_schema.py`, `tests/conftest.py`. **Deps**: none. **Tests**: `tests/conftest.py`, `tests/integration/{test_db,test_migrations,test_cli_init,test_cli_version}.py`, `tests/unit/{test_no_float_amounts,test_config}.py`.

**Work-unit commit sequence**: `[T-1.1 red] [T-1.1 green] [T-1.2 red] [T-1.2 green] [T-1.3..1.10 red|green] [T-1.11..1.13 red|green] [T-1.14..1.18 red|green] [T-1.19 red|green] [refactor commit]`.

```yaml
- id: T-1.1
  title: Create empty module stubs (models/validation/repository/reports/cli/db/config/exceptions) + py.typed
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: importlib resolves each module & __all__ set; green: write empty stubs; refactor: none}
  files_touched: [src/pyfintracker/__init__.py, src/pyfintracker/py.typed, src/pyfintracker/*.py]
  tests_added: [tests/unit/test_imports.py::test_modules_resolve]
  depends_on: []
  acceptance: "Every public module imports cleanly; __all__ defined."
  risks: "Missing __all__ trips type checkers."

- id: T-1.2
  title: Implement exceptions.py with FinanceError tree (design §4, B2 exit codes)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: assert isinstance(InvalidAccountName(), ValidationError) & exit=1; green: declare tree; refactor: add __all__}
  files_touched: [src/pyfintracker/exceptions.py]
  tests_added: [tests/unit/test_exceptions.py]
  depends_on: [T-1.1]
  acceptance: "All 13 subclasses exist; each maps to declared exit code via `code` attr."
  risks: "MRO collisions if tree split across files; keep in one module."

- id: T-1.3
  title: db.make_engine(url) — applies 3 PRAGMAs
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: integration test asserts journal_mode=WAL on sqlite file URL; green: event listener; refactor: extract _register_pragmas}
  files_touched: [src/pyfintracker/db.py]
  tests_added: [tests/integration/test_db.py::test_make_engine_applies_pragmas]
  depends_on: [T-1.1]
  acceptance: "Engine connected to file URL reports journal_mode=WAL."
  risks: "WAL fails on read-only DB; ignore in test."

- id: T-1.4
  title: db.make_test_engine() — :memory: + StaticPool + pragmas (D2)
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: shared conn across two sessions sees same data; green: StaticPool + event listener; refactor: none}
  files_touched: [src/pyfintracker/db.py]
  tests_added: [tests/integration/test_db.py::test_test_engine_shares_state]
  depends_on: [T-1.3]
  acceptance: "Two connections from make_test_engine see each other's writes."

- id: T-1.5
  title: Hand-write 0001_initial_schema.py (4 tables, TEXT money, CHECK no-zero)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: migrations smoke fails on file with wrong DDL; green: paste DDL from design §3; refactor: inline starter chart data_migration}
  files_touched: [migrations/versions/0001_initial_schema.py, alembic.ini, migrations/env.py, migrations/script.py.mako]
  tests_added: [tests/integration/test_migrations.py::test_migrations_smoke]
  depends_on: [T-1.1]
  acceptance: "alembic upgrade head → downgrade base → upgrade head succeeds; 4 tables exist with TEXT money; CHECK constraint present."
  risks: "Alembic autogenerate later may try to alter TEXT→NUMERIC; pre-commit guard in PR 7."

- id: T-1.6
  title: Inline 11-account starter chart in 0001 data_migration (D1, B4)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: upgrade head, count accounts==11; green: insert 11 accounts via INSERT statements with IF NOT EXISTS; refactor: extract list constant}
  files_touched: [migrations/versions/0001_initial_schema.py]
  tests_added: [tests/integration/test_migrations.py::test_starter_chart_has_11]
  depends_on: [T-1.5]
  acceptance: "Post-migration SELECT count FROM accounts == 11; Equity:OpeningBalances present."
  risks: "Single-quote chars in descriptions; keep empty descriptions only."

- id: T-1.7
  title: db.apply_pragmas(conn) — idempotent PRAGMA call
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: call twice, journal_mode unchanged; green: SELECT pragma_journal_mode guard; refactor: none}
  files_touched: [src/pyfintracker/db.py]
  tests_added: [tests/integration/test_db.py::test_apply_pragmas_idempotent]
  depends_on: [T-1.3]
  acceptance: "Calling apply_pragmas twice yields identical state."

- id: T-1.8
  title: config.Settings (pydantic-settings) — fields + TOML loader
  status: done
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: load_settings() returns Settings with default db_path; green: declare BaseSettings with SettingsConfigDict; refactor: extract _xdg_config_path helper}
  files_touched: [src/pyfintracker/config.py]
  tests_added: [tests/unit/test_config.py::test_settings_defaults]
  depends_on: [T-1.1]
  acceptance: "Settings(db_path=Path('~/.local/share/fin/fin.db')) instance loads with defaults."

- id: T-1.9
  title: config.load_settings(cli_overrides=None) — precedence chain
  status: done
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: env var overrides default; green: settings_customise_sources with 4 tiers; refactor: cache for source_of}
  files_touched: [src/pyfintracker/config.py]
  tests_added: [tests/unit/test_config.py::test_precedence_chain]
  depends_on: [T-1.8]
  acceptance: "defaults < TOML < FIN_* env < cli_overrides; explicit unit test per layer."

- id: T-1.10
  title: config.source_of(field) → Literal["default","file","env","flag"]
  status: done
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: source_of("no_color") returns "flag" after CLI override; green: pop source map after merge; refactor: helper _track_source}
  files_touched: [src/pyfintracker/config.py]
  tests_added: [tests/unit/test_config.py::test_source_of_returns_origin]
  depends_on: [T-1.9]
  acceptance: "Each field's source is reported as one of 4 literals."

- id: T-1.11
  title: cli.version command — prints "fin X.Y.Z" from pyproject
  status: done
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: CliRunner.invoke(app, ["version"]) exit 0, stdout has version; green: read pyproject.toml; refactor: cache via importlib.metadata fallback}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/integration/test_cli_version.py]
  depends_on: [T-1.1]
  acceptance: "`fin version` exits 0, prints version string."

- id: T-1.12
  title: cli.init [--force] — refuses if DB exists, runs alembic upgrade (B3, D3)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: init refuses on existing DB; green: make_engine + alembic.command.upgrade + seed (already in 0001); refactor: split into _check_db_exists + _run_migrations}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/integration/test_cli_init.py::test_init_refuses_if_db_exists, ::test_init_force_recreates]
  depends_on: [T-1.3, T-1.5]
  acceptance: "Second `fin init` exits 1 with AlreadyInitializedError; `--force` recreates."
  risks: "TEMP env to redirect XDG_DATA_HOME during tests."

- id: T-1.13
  title: cli.migrate up|down|status — thin wrappers on alembic.command
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: migrate status exit 0 prints current rev; green: alias to alembic.command.{current,upgrade,downgrade}; refactor: shared _run_alembic helper}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/integration/test_cli_migrate.py]
  depends_on: [T-1.12]
  acceptance: "`fin migrate up` runs alembic upgrade head; exit 0."

- id: T-1.14
  title: tests/conftest.py — engine/conn/cli_runner fixtures (D2)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: conftest import fails; green: declare engine/conn/cli_runner/prompt_fn fixtures; refactor: scope=function for engine}
  files_touched: [tests/conftest.py]
  tests_added: [tests/unit/test_conftest.py::test_fixtures_present]
  depends_on: [T-1.4]
  acceptance: "All four fixtures available across test layers."

- id: T-1.15
  title: test_no_float_amounts_in_models — AST scan (CI gate PR 1)
  status: done
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: introduce float annotation; green: AST walk fails on Annotation containing Name(id=float); refactor: helper _scan_module}
  files_touched: [tests/unit/test_no_float_amounts.py]
  tests_added: [tests/unit/test_no_float_amounts.py::test_no_float_in_models_validation_repository]
  depends_on: [T-1.1]
  acceptance: "Scan returns zero `float` annotations in money-touching code."
  risks: "False positive on `from typing import Final` etc.; restrict to subscript annotations."

- id: T-1.16
  title: test_migrations_smoke — upgrade/downgrade/upgrade idempotent
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: triple-run fails; green: alembic upgrade/downgrade in tmpdir; refactor: parametrize over dialect if reusable}
  files_touched: [tests/integration/test_migrations.py]
  tests_added: [tests/integration/test_migrations.py::test_migrations_smoke]
  depends_on: [T-1.5, T-1.6]
  acceptance: "upgrade head → downgrade base → upgrade head succeeds without error."

- id: T-1.17
  title: test_cli_init — refuse if DB exists; --force recreates
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: second init fails; green: tmp db via XDG_DATA_HOME env; refactor: parametrize with --force}
  files_touched: [tests/integration/test_cli_init.py]
  tests_added: [tests/integration/test_cli_init.py::test_init_refuses_if_db_exists, ::test_init_force_recreates]
  depends_on: [T-1.12]
  acceptance: "Second run exits 1; --force creates fresh DB."
  risks: "Test isolation; ensure XDG_DATA_HOME redirected."

- id: T-1.18
  title: test_cli_version — exit 0, version string
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: assertion fails; green: CliRunner; refactor: none}
  files_touched: [tests/integration/test_cli_version.py]
  tests_added: [tests/integration/test_cli_version.py::test_version_prints]
  depends_on: [T-1.11]
  acceptance: "exits 0, stdout contains 'fin '."

- id: T-1.19
  title: test_config — precedence matrix (default/file/env/flag)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: parametrize missing; green: 4 cases per field; refactor: helper _with_env}
  files_touched: [tests/unit/test_config.py]
  tests_added: [tests/unit/test_config.py::test_precedence_chain]
  depends_on: [T-1.10]
  acceptance: "All 4 precedence combinations tested for one field."
```

---

## PR 2 — Account rules (contract a) · `feat/02-accounts` · target ≤380 lines

**Goal**: Account entity, name/currency/date validators, account repository (upsert/list/has_postings), `cli account new/list`. **Scope**: `models.Account`, `validation.{validate_account_name,validate_currency,validate_date}`, `repository.{upsert_account,get_account_by_name,get_account_by_id,list_accounts,account_has_postings}`, `cli account new/list`. **Deps**: PR 1. **Tests**: `tests/unit/test_models.py`, `tests/unit/test_validation.py`, `tests/property/test_account_name_regex.py`, `tests/integration/test_accounts_repo.py`, `tests/integration/test_cli_accounts.py`.

**Work-unit commit sequence**: `T-2.1..2.2 red|green (model)` → `T-2.3..2.5 red|green (validators)` → `T-2.6..2.10 red|green (repo)` → `T-2.11..2.12 red|green (CLI)` → `T-2.13 red|green (property)` → `T-2.14..2.15 red|green (integration)` → `[refactor commit]`.

```yaml
- id: T-2.1
  title: models.Account frozen dataclass (design §2)
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: dataclass instantiation fails; green: declare 6 fields + frozen=True slots=True; refactor: none}
  files_touched: [src/pyfintracker/models.py]
  tests_added: [tests/unit/test_models.py::test_account_construction]
  depends_on: [T-1.1]
  acceptance: "Account(name='Assets:Cash', currency='COP') instantiates; mutation raises FrozenInstanceError."

- id: T-2.2
  title: Account.to_row() / from_row()
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: roundtrip unequal; green: dict mapper; refactor: typed Mapping input}
  files_touched: [src/pyfintracker/models.py]
  tests_added: [tests/unit/test_models.py::test_account_to_from_row_roundtrip]
  depends_on: [T-2.1]
  acceptance: "from_row(to_row(a)) == a for all fields."

- id: T-2.3
  title: validation.validate_account_name (regex, canonicalize)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: rejects `assets:cash`; green: regex `^[A-Z][a-z]+(:[A-Z][\w-]+){0,2}$`; refactor: split max-depth check}
  files_touched: [src/pyfintracker/validation.py]
  tests_added: [tests/unit/test_validation.py::test_validate_account_name]
  depends_on: [T-2.1]
  acceptance: "lowercase rejected; `Assets:Cash` accepted; `Assets:A:B:C:D` rejected (>3 levels)."

- id: T-2.4
  title: validation.validate_currency (ISO 4217, uppercase)
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: 'us' raises; green: regex `[A-Z]{3}`; refactor: use pycountry if present}
  files_touched: [src/pyfintracker/validation.py]
  tests_added: [tests/unit/test_validation.py::test_validate_currency]
  depends_on: [T-1.1]
  acceptance: "'usd' raises; 'USD' returns 'USD'."

- id: T-2.5
  title: validation.validate_date (strict ISO)
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: '2024-13-01' raises; green: date.fromisoformat + length check; refactor: helper _parse_iso}
  files_touched: [src/pyfintracker/validation.py]
  tests_added: [tests/unit/test_validation.py::test_validate_date]
  depends_on: [T-1.1]
  acceptance: "'2024-01-15' accepted; malformed rejected."

- id: T-2.6
  title: repository.upsert_account (idempotent, parent check, COLLATE NOCASE)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: duplicate 'ASSETS:CASH' fails; green: SELECT-CASE-INSERT/UPDATE, COLLATE NOCASE; refactor: extract _resolve_parent_id}
  files_touched: [src/pyfintracker/repository.py]
  tests_added: [tests/integration/test_accounts_repo.py::test_upsert_account_idempotent]
  depends_on: [T-2.3, T-2.4, T-1.14]
  acceptance: "Duplicate case-insensitive name returns same id; parent pre-check raises if parent missing."

- id: T-2.7
  title: repository.get_account_by_name (case-insensitive)
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: lookup 'ASSETS:CASH' returns None; green: WHERE name=? COLLATE NOCASE; refactor: none}
  files_touched: [src/pyfintracker/repository.py]
  tests_added: [tests/integration/test_accounts_repo.py::test_get_account_by_name]
  depends_on: [T-2.6]
  acceptance: "Mixed-case lookup matches stored canonical."

- id: T-2.8
  title: repository.get_account_by_id
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: returns None for missing; green: SELECT id=?; refactor: none}
  files_touched: [src/pyfintracker/repository.py]
  tests_added: [tests/integration/test_accounts_repo.py::test_get_account_by_id]
  depends_on: [T-2.6]
  acceptance: "Returns Account or None."

- id: T-2.9
  title: repository.list_accounts(root=None, include_archived=False)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: only returns top-level; green: SELECT with LIKE prefix; refactor: helper _parent_of(name)}
  files_touched: [src/pyfintracker/repository.py]
  tests_added: [tests/integration/test_accounts_repo.py::test_list_accounts_root_filter]
  depends_on: [T-2.7]
  acceptance: "root='Assets' returns Assets:* only; None returns all."

- id: T-2.10
  title: repository.account_has_postings(id) → bool
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: count(*) returns None on empty; green: SELECT EXISTS; refactor: none}
  files_touched: [src/pyfintracker/repository.py]
  tests_added: [tests/integration/test_accounts_repo.py::test_account_has_postings]
  depends_on: [T-1.5]
  acceptance: "Returns True/False without raising."

- id: T-2.11
  title: cli.account_new (no --initial yet)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: new 'Assets:Cash' COP exit 1 (invalid root); green: validate + upsert_account + echo; refactor: helper _resolve_parent_by_name}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/integration/test_cli_accounts.py::test_account_new_creates_row]
  depends_on: [T-2.6, T-2.11 dep shown]
  acceptance: "`fin account new Assets:Cash --currency COP` creates row; exists prints idempotent ok."

- id: T-2.12
  title: cli.account_list (Rich table)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: empty output; green: list_accounts + Table grouped; refactor: group iterator}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/integration/test_cli_accounts.py::test_account_list_renders_table]
  depends_on: [T-2.9]
  acceptance: "Lists 11 chart accounts grouped by root type."

- id: T-2.13
  title: property test — test_account_name_regex (hypothesis)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: [property-based]
  tdd_cycle: {red: fuzzed string catches false accepts; green: st.from_regex + ffilter; refactor: shared strategy}
  files_touched: [tests/property/test_account_name_regex.py]
  tests_added: [tests/property/test_account_name_regex.py]
  depends_on: [T-2.3]
  acceptance: "∀ random string: re.fullmatch ↔ validate_account_name agrees."

- id: T-2.14
  title: integration — duplicate idempotent, parent must exist
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: unknown parent raises; green: pre-check in upsert_account; refactor: parametrize tests}
  files_touched: [tests/integration/test_accounts_repo.py]
  tests_added: [tests/integration/test_accounts_repo.py::test_duplicate_idempotent, ::test_parent_must_exist]
  depends_on: [T-2.6]
  acceptance: "Both scenarios cover error + idempotency paths."

- id: T-2.15
  title: integration — account_list renders
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: stdout empty; green: snapshot match; refactor: strip ANSI for assertion}
  files_touched: [tests/integration/test_cli_accounts.py]
  tests_added: [tests/integration/test_cli_accounts.py::test_account_list_renders_table]
  depends_on: [T-2.12]
  acceptance: "Output contains 'Assets:Checking' line."
```

---

## PR 3 — Decimal pipeline (contract f) · `feat/03-decimal-pipeline` · target ≤280 lines

**Goal**: DecimalAsText TypeDecorator, per-currency precision, validate_amount + Money, property tests for quantization/roundtrip. **Scope**: `db.DecimalAsText`, `validation.{PER_CURRENCY_DECIMALS,quantize_for_currency,validate_amount,Money}`, tests. **Deps**: PR 1. **Tests**: `tests/unit/test_validation.py`, `tests/property/{test_decimal_quantization,test_decimal_text_roundtrip}.py`, `tests/unit/test_money_columns_text.py`.

**Work-unit commit sequence**: `T-3.1 red|green (TypeDecorator)` → `T-3.2 red|green (const)` → `T-3.3..3.4 red|green (validate_amount)` → `T-3.5 red|green (Money type)` → `T-3.6 red|green (wire schema)` → `T-3.7..3.10 red|green (property + tests)` → `[refactor]`.

```yaml
- id: T-3.1
  title: db.DecimalAsText TypeDecorator (TEXT storage, Decimal roundtrip)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: bind Decimal('99.456'), read back returns float; green: TypeDecorator impl=Text, str(value)/Decimal(value); refactor: cache_ok=True}
  files_touched: [src/pyfintracker/db.py]
  tests_added: [tests/integration/test_db.py::test_decimal_as_text_roundtrip]
  depends_on: [T-1.3]
  acceptance: "Decimal('99.456') binds as '99.456', reads back as Decimal('99.456')."

- id: T-3.2
  title: validation.PER_CURRENCY_DECIMALS constant (MappingProxyType)
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: assert COP==0; green: declare MappingProxyType({...}); refactor: add USD/EUR/GBP=2}
  files_touched: [src/pyfintracker/validation.py]
  tests_added: [tests/unit/test_validation.py::test_per_currency_decimals]
  depends_on: [T-1.1]
  acceptance: "PER_CURRENCY_DECIMALS['COP'] == 0; mutation raises TypeError."

- id: T-3.3
  title: quantize_for_currency(amount, currency) → Decimal (ROUND_HALF_UP)
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: COP 99.6 roundups to 100; green: amount.quantize(decimals, ROUND_HALF_UP); refactor: cache decimal places per call}
  files_touched: [src/pyfintracker/validation.py]
  tests_added: [tests/unit/test_validation.py::test_quantize_for_currency]
  depends_on: [T-3.2]
  acceptance: "COP: 99.6→100; USD: 99.456→99.46 (with HALF_UP)."
  risks: "Python default is HALF_EVEN; pin ROUND_HALF_UP explicitly."

- id: T-3.4
  title: validate_amount(value, currency) → Decimal (rejects float/NaN/Inf, quantizes)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: float 1.5 raises; green: int/str/Decimal → Decimal, float→TypeError, NaN→InvalidAmount; refactor: helper _coerce}
  files_touched: [src/pyfintracker/validation.py]
  tests_added: [tests/unit/test_validation.py::test_validate_amount]
  depends_on: [T-3.3]
  acceptance: "float rejected; Decimal('99.456') COP → Decimal('100'); NaN/Inf rejected."

- id: T-3.5
  title: Money Pydantic type (Annotated Decimal)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: BaseModel with Money rejection; green: Annotated[Decimal, BeforeValidator(_coerce_money), PlainSerializer(_serialize_money)]; refactor: helper _coerce_money}
  files_touched: [src/pyfintracker/validation.py]
  tests_added: [tests/unit/test_validation.py::test_money_pydantic]
  depends_on: [T-3.4]
  acceptance: "Money('99.456', 'COP') → Decimal('100'); float rejected at Pydantic boundary."

- id: T-3.6
  title: Wire DecimalAsText into postings.amount (re-check)
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: read existing migration; green: confirm TEXT (already done in 0001); refactor: make migration explicit}
  files_touched: [migrations/versions/0001_initial_schema.py]
  tests_added: [tests/unit/test_money_columns_text.py::test_migration_uses_text_for_money]
  depends_on: [T-3.1, T-1.5]
  acceptance: "grep confirms `amount TEXT` and `rate TEXT`; no NUMERIC/REAL."

- id: T-3.7
  title: property test — test_decimal_quantization_per_currency
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: [property-based]
  tdd_cycle: {red: counterexample at COP 99.6→99; green: strategies.decimals(min_value=-1e9, max_value=1e9, places=5); refactor: shared currencies}
  files_touched: [tests/property/test_decimal_quantization.py]
  tests_added: [tests/property/test_decimal_quantization.py]
  depends_on: [T-3.3]
  acceptance: "∀ Decimal × {COP,JPY,USD,EUR,GBP}: roundtrip == quantize."

- id: T-3.8
  title: property test — test_decimal_text_roundtrip
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: [property-based]
  tdd_cycle: {red: Decimal('1.10') str→str='1.1'; green: strategies.decimals(); refactor: canonical form normalization}
  files_touched: [tests/property/test_decimal_text_roundtrip.py]
  tests_added: [tests/property/test_decimal_text_roundtrip.py]
  depends_on: [T-3.1]
  acceptance: "Decimal → str → Decimal == Decimal normalized."

- id: T-3.9
  title: unit tests — validate_amount rejects float/NaN/Inf
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: missing branches; green: parametrize (float, Decimal('NaN'), Decimal('Infinity'), 'foo'); refactor: lists}
  files_touched: [tests/unit/test_validation.py]
  tests_added: [tests/unit/test_validation.py::test_validate_amount_rejects_invalid]
  depends_on: [T-3.4]
  acceptance: "Each bad input raises correct exception class."

- id: T-3.10
  title: unit tests — quantize_for_currency per currency
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: parametrize; green: parametrize (currency, input, expected); refactor: tabular fixture}
  files_touched: [tests/unit/test_validation.py]
  tests_added: [tests/unit/test_validation.py::test_quantize_per_currency]
  depends_on: [T-3.3]
  acceptance: "Covers COP, JPY, USD, EUR, GBP with edge cases (0.5, 99.456)."
```

---

## PR 4 — Transactions + double-entry (contracts b+c) · `feat/04-transactions` · target ≤400 lines

**Goal**: Posting/Transaction entities, validate_posting/validate_transaction, atomic create, `--initial` opening balance, `--from --to` flag mode, property test for sum-zero invariant. **Scope**: `models.{Posting,Transaction,Rate}`, `validation.{validate_posting,validate_transaction}`, `repository.create_transaction_with_postings`, `cli add` flag mode + `account new --initial`. **Deps**: PR 2, PR 3. **Tests**: `tests/property/{test_double_entry_invariant,test_opening_balance}.py`, `tests/integration/{test_transactions_repo,test_cli_add,test_cli_opening_balance}.py`.

**Work-unit commit sequence**: `T-4.1..4.3 red|green (entities)` → `T-4.4..4.5 red|green (validators)` → `T-4.6 red|green (repo)` → `T-4.7 red|green (--initial)` → `T-4.8 red|green (flag mode)` → `T-4.9..4.10 (property)` → `T-4.11..4.15 (integration)` → `[refactor]`.

```yaml
- id: T-4.1
  title: Posting frozen dataclass
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: missing field; green: declare; refactor: none}
  files_touched: [src/pyfintracker/models.py]
  tests_added: [tests/unit/test_models.py::test_posting_construction]
  depends_on: [T-2.1]
  acceptance: "Posting(account_id=1, amount=Decimal('100'), currency='COP') immutable."

- id: T-4.2
  title: Transaction frozen dataclass
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: missing fields; green: declare id,date,description,currency + frozen slots; refactor: validate description maxlen in factory}
  files_touched: [src/pyfintracker/models.py]
  tests_added: [tests/unit/test_models.py::test_transaction_construction]
  depends_on: [T-1.1]
  acceptance: "Transaction(date=date(2024,1,15)) immutable; description 257 chars rejected by validator."

- id: T-4.3
  title: Posting/Transaction to_row/from_row
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: roundtrip unequal; green: dict conversion; refactor: shared dict-key helper}
  files_touched: [src/pyfintracker/models.py]
  tests_added: [tests/unit/test_models.py::test_posting_tx_roundtrip]
  depends_on: [T-4.1, T-4.2]
  acceptance: "roundtrip identity for all 4 entities."

- id: T-4.4
  title: validate_posting (currency coherence, D6)
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: COP↔USD accepted; green: posting.currency == account.currency else CurrencyMismatchError; refactor: none}
  files_touched: [src/pyfintracker/validation.py]
  tests_added: [tests/unit/test_validation.py::test_validate_posting_currency]
  depends_on: [T-4.1, T-2.3]
  acceptance: "Mismatch raises; match returns None."

- id: T-4.5
  title: validate_transaction — fail-fast order: count→zero→currency→sum=0
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: order wrong; green: ordered asserts; refactor: extract _check_count, _check_no_zero, _check_currency, _check_sum}
  files_touched: [src/pyfintracker/validation.py]
  tests_added: [tests/unit/test_validation.py::test_validate_transaction_order]
  depends_on: [T-4.2, T-4.4]
  acceptance: "Empty → TooFewPostings; zero-amount → ZeroAmountPosting; mix-currency → CurrencyMismatchError; sum≠0 → UnbalancedTransaction."

- id: T-4.6
  title: create_transaction_with_postings — atomic single transaction
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: partial insert on failure; green: `with conn.begin():` wrap INSERT tx + N postings; refactor: helper _insert_postings}
  files_touched: [src/pyfintracker/repository.py]
  tests_added: [tests/integration/test_transactions_repo.py::test_create_atomic]
  depends_on: [T-1.14, T-4.5, T-4.1]
  acceptance: "Failure mid-loop rolls back; success returns new txn id."

- id: T-4.7
  title: cli.account_new --initial — builds synthetic 2-posting opening txn (contract c)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: only creates account; green: if --initial: ensure Equity:OpeningBalances exists, build txn asset+=initial, equity-=initial; refactor: helper _build_opening_tx}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/integration/test_cli_opening_balance.py]
  depends_on: [T-4.6, T-2.11]
  acceptance: "Creates row + balanced synthetic txn; idempotent on second `--initial` (rejects)."

- id: T-4.8
  title: cli.add --from --to --amount (2-posting flag mode)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: missing branch; green: validate + build Posting x2 + save; refactor: helper _build_two_posting_txn}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/integration/test_cli_add.py::test_add_flags_creates_two_posting_txn]
  depends_on: [T-4.6, T-2.6]
  acceptance: "Exit 0, two postings sum to 0, same currency."

- id: T-4.9
  title: property — test_double_entry_invariant_holds
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: [property-based]
  tdd_cycle: {red: counterexample unbalanced; green: strategy.decompose(sum_total) into N postings; refactor: helper _balanced_split}
  files_touched: [tests/property/test_double_entry_invariant.py]
  tests_added: [tests/property/test_double_entry_invariant.py]
  depends_on: [T-4.5]
  acceptance: "∀ random balanced postings: validate_transaction() succeeds; ∀ unbalanced: raises."

- id: T-4.10
  title: property — test_opening_balance_creates_zero_sum_synthetic
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: [property-based]
  tdd_cycle: {red: random initial not zero-sum; green: strategy.decimals; refactor: shared currency}
  files_touched: [tests/property/test_opening_balance.py]
  tests_added: [tests/property/test_opening_balance.py]
  depends_on: [T-4.7]
  acceptance: "Synthetic opening txn always sums to 0."

- id: T-4.11
  title: integration — test_add_flags_creates_two_posting_txn
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: txn absent; green: SELECT count; refactor: assert sum}
  files_touched: [tests/integration/test_cli_add.py]
  tests_added: [tests/integration/test_cli_add.py]
  depends_on: [T-4.8]
  acceptance: "DB has 1 txn, 2 postings, sum=0."

- id: T-4.12
  title: integration — test_opening_balance_idempotency_rejects_reinit
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: reinit succeeds; green: AlreadyInitializedError on second --initial; refactor: parametrize}
  files_touched: [tests/integration/test_cli_opening_balance.py]
  tests_added: [tests/integration/test_cli_opening_balance.py::test_opening_balance_idempotent]
  depends_on: [T-4.7]
  acceptance: "Reinit exits 1; original balance preserved."

- id: T-4.13
  title: integration — test_unbalanced_txn_rejected
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: passes; green: validate_transaction pre-insert; refactor: parametrize scenarios}
  files_touched: [tests/integration/test_transactions_repo.py]
  tests_added: [tests/integration/test_transactions_repo.py::test_unbalanced_rejected]
  depends_on: [T-4.6]
  acceptance: "Creates invocation raising UnbalancedTransaction; DB unchanged."

- id: T-4.14
  title: integration — test_currency_mismatch_rejected
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: passes; green: pre-check; refactor: shared fixture}
  files_touched: [tests/integration/test_transactions_repo.py]
  tests_added: [tests/integration/test_transactions_repo.py::test_currency_mismatch]
  depends_on: [T-4.6]
  acceptance: "Mixed-currency postings rejected with CurrencyMismatchError."

- id: T-4.15
  title: integration — test_too_few_postings_rejected
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: passes; green: ensure ≥2; refactor: parametrize (1, 0) postings}
  files_touched: [tests/integration/test_transactions_repo.py]
  tests_added: [tests/integration/test_transactions_repo.py::test_too_few_postings]
  depends_on: [T-4.6]
  acceptance: "<2 postings raises TooFewPostings; rollback OK."
```

---

## PR 5 — REPL (contract e) · `feat/05-repl` · target ≤250 lines

**Goal**: Interactive transaction entry via prompts, TTY detection, abort/CTRL-C. **Scope**: `cli.repl_add_postings(console, prompt_fn)`, REPL amount parser, account resolution. **Deps**: PR 4. **Tests**: `tests/unit/test_repl.py`, `tests/integration/{test_cli_add_repl,test_cli_repl_abort,test_cli_repl_unbalanced}.py`.

**Work-unit commit sequence**: `T-5.1..5.5 red|green (REPL core)` → `T-5.6..5.8 red|green (wiring + parser)` → `T-5.9..5.12 (tests)` → `[refactor]`.

```yaml
- id: T-5.1
  title: repl_add_postings(console, prompt_fn) main loop
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: prompts never called; green: collect date→desc→total→postings loop; refactor: split _prompt_posting}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/unit/test_repl.py::test_repl_collects_inputs]
  depends_on: [T-4.5]
  acceptance: "Returns Transaction + postings when prompts yield balanced set."

- id: T-5.2
  title: REPL prompts — date → description → total → posting loop
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: prompt order wrong; green: sequence call prompt_fn; refactor: helper _prompt_date}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/unit/test_repl.py::test_repl_prompt_order]
  depends_on: [T-5.1]
  acceptance: "Prompts invoked in declared order with declared labels."

- id: T-5.3
  title: :abort command — cancel without save
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: persists; green: raise SystemExit(130) from :abort; refactor: catch in repl}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/unit/test_repl.py::test_abort_raises_system_exit]
  depends_on: [T-5.1]
  acceptance: "`:abort` triggers SystemExit(130), no txn saved."

- id: T-5.4
  title: CTRL-C handler — discard with confirmation
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: KeyboardInterrupt propagates; green: prompt 'discard? y/n'; refactor: helper _handle_sigint}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/unit/test_repl.py::test_ctrl_c_confirms_discard]
  depends_on: [T-5.3]
  acceptance: "CTRL-C → confirmation prompt; aborts on y."

- id: T-5.5
  title: TTY detection — ReplRequiresTTYError if not a TTY (exit 2)
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: opens REPL on pipe; green: check sys.stdin.isatty(); refactor: helper _require_tty}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/integration/test_cli_add_repl.py::test_repl_requires_tty]
  depends_on: [T-5.1]
  acceptance: "REPL on non-TTY stdin exits 2 with stderr message."

- id: T-5.6
  title: cli.add — dispatch REPL branch (no flags)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: plain `fin add` no-op; green: detect absent --from/--to → REPL; refactor: helper _mode_add}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/integration/test_cli_add.py]
  depends_on: [T-5.1]
  acceptance: "`fin add` enters REPL (TTY required for integration test)."

- id: T-5.7
  title: REPL amount parser — accepts `50000`/`-50000`/`50,000`; rejects 0/non-numeric
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: parser raises on valid; green: strip commas, Decimal, zero check; refactor: regex _AMOUNT_RE}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/unit/test_repl.py::test_amount_parser]
  depends_on: [T-4.5]
  acceptance: "Valid inputs return Decimal; `0` rejected; `abc` rejected."

- id: T-5.8
  title: account autocomplete — free-text fallback (Tab is nice-to-have, optional)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: exact-match only; green: case-insensitive, suggest list; refactor: helper _suggest_accounts}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/unit/test_repl.py::test_account_fuzzy_match]
  depends_on: [T-5.2]
  acceptance: "Unknown name → list of 3 closest matches, accept number to pick."

- id: T-5.9
  title: unit test — repl_add_postings uses prompt_fn fixture
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: prompt_fn undefined; green: closure-based override; refactor: helper _reply_with}
  files_touched: [tests/unit/test_repl.py]
  tests_added: [tests/unit/test_repl.py]
  depends_on: [T-5.1]
  acceptance: "Test injects scripted replies; repl returns expected txn."

- id: T-5.10
  title: integration — test_add_repl_creates_three_posting_txn
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: txn absent; green: mock stdin; refactor: parametrize (2, 3, 5 postings)}
  files_touched: [tests/integration/test_cli_add_repl.py]
  tests_added: [tests/integration/test_cli_add_repl.py]
  depends_on: [T-5.6]
  acceptance: "3-posting txn persisted, balanced."

- id: T-5.11
  title: integration — test_repl_abort_discards
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: persists; green: type :abort; refactor: helper _feed_stdin}
  files_touched: [tests/integration/test_cli_add_repl.py]
  tests_added: [tests/integration/test_cli_add_repl.py::test_repl_abort]
  depends_on: [T-5.3]
  acceptance: "Exit 130; DB count unchanged."

- id: T-5.12
  title: integration — test_repl_unbalanced_prompts_fix
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: persists unbalanced; green: re-prompt for adjustment; refactor: helper _show_diff}
  files_touched: [tests/integration/test_cli_add_repl.py]
  tests_added: [tests/integration/test_cli_add_repl.py::test_repl_unbalanced_fix]
  depends_on: [T-5.7]
  acceptance: "Sum mismatch → guided fix prompt loop; final state balanced."
```

---

## PR 6 — Reports (contract d) · `feat/06-reports` · target ≤380 lines

**Goal**: MonthlyReport + BalanceReport Pydantic models, compute + render with Rich, `cli report month`, `cli balance`. **Scope**: `reports.{MonthlyReport,BalanceReport,MonthlyLine,BalanceLine,compute_monthly_report,compute_balance,render_*}` + `cli.report_month`, `cli.balance`. **Deps**: PR 2 (accounts) + PR 4 (tx data — via repo). **Tests**: `tests/unit/test_reports.py`, `tests/snapshots/test_reports_snap.py`, `tests/integration/{test_cli_report_month,test_cli_balance}.py`.

**Work-unit commit sequence**: `T-6.1..6.3 red|green (compute)` → `T-6.4..6.5 red|green (render)` → `T-6.6..6.7 red|green (CLI)` → `T-6.8..6.11 (tests + snapshot)` → `[refactor]`.

```yaml
- id: T-6.1
  title: reports.{MonthlyReport,MonthlyLine,BalanceReport,BalanceLine} Pydantic models
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: import fails; green: declare BaseModel; refactor: shared helpers}
  files_touched: [src/pyfintracker/reports.py]
  tests_added: [tests/unit/test_reports.py::test_models_instantiate]
  depends_on: [T-1.1]
  acceptance: "All 4 models serializable to dict."

- id: T-6.2
  title: compute_monthly_report (formula design §8)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: returns None; green: filter txns by month, group, rollup; refactor: extract _per_day_aggregate}
  files_touched: [src/pyfintracker/reports.py]
  tests_added: [tests/unit/test_reports.py::test_compute_monthly]
  depends_on: [T-6.1, T-4.2]
  acceptance: "income_sum + (-expense_sum) == net algebraically."

- id: T-6.3
  title: compute_balance (per-account + net worth, sign convention)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: returns 0; green: SUM per account type, assets-liab+equity net; refactor: helper _sign_for_root}
  files_touched: [src/pyfintracker/reports.py]
  tests_added: [tests/unit/test_reports.py::test_compute_balance_signs]
  depends_on: [T-6.1, T-4.1]
  acceptance: "Assets=+, Liabilities=+, Equity=+, Income/Expenses excluded; net = sum(asset+liab+equity)."

- id: T-6.4
  title: render_monthly_report (Rich table + Sparkline per line)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: console empty; green: Panel + Tables; refactor: helper _format_pct}
  files_touched: [src/pyfintracker/reports.py]
  tests_added: [tests/snapshots/test_reports_snap.py::test_render_monthly]
  depends_on: [T-6.2]
  acceptance: "Output contains 'Income' / 'Expenses' / 'Net' sections."

- id: T-6.5
  title: render_balance (grouped table + bold net worth footer)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: footer missing; green: grouped Table + Panel; refactor: helper _group_by_root}
  files_touched: [src/pyfintracker/reports.py]
  tests_added: [tests/snapshots/test_reports_snap.py::test_render_balance]
  depends_on: [T-6.3]
  acceptance: "Footer line contains 'Net worth:' bold."

- id: T-6.6
  title: cli.report_month (default current month)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: ignores --month; green: parse YYYY-MM, default current; refactor: helper _current_yyyymm}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/integration/test_cli_report_month.py]
  depends_on: [T-6.4]
  acceptance: "`fin report month --month 2024-01` exits 0, prints panel."

- id: T-6.7
  title: cli.balance [account_name] (per-account + net worth)
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: missing branch; green: scope by account_name or all; refactor: helper _filter_accounts}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/integration/test_cli_balance.py::test_balance_returns_per_account_and_net_worth]
  depends_on: [T-6.5]
  acceptance: "Per-account balance lines + bold net worth footer."

- id: T-6.8
  title: unit tests for compute_* — pure function assertions
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: parametrize sparse; green: edge cases (empty, single, rollup); refactor: shared fixtures}
  files_touched: [tests/unit/test_reports.py]
  tests_added: [tests/unit/test_reports.py::test_compute_*]
  depends_on: [T-6.2, T-6.3]
  acceptance: "Covers empty/single/rollup/no-rollup cases."

- id: T-6.9
  title: snapshot — test_report_month_renders_snapshot
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: snapshot missing; green: snapshot match via syrupy; refactor: name by scenario}
  files_touched: [tests/snapshots/test_reports_snap.py]
  tests_added: [tests/snapshots/test_reports_snap.py::test_report_month_renders_snapshot]
  depends_on: [T-6.4]
  acceptance: "Snapshot pinned to file; deterministic on re-run."

- id: T-6.10
  title: snapshot — test_balance_renders_snapshot
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: snapshot missing; green: snapshot match; refactor: none}
  files_touched: [tests/snapshots/test_reports_snap.py]
  tests_added: [tests/snapshots/test_reports_snap.py::test_balance_renders_snapshot]
  depends_on: [T-6.5]
  acceptance: "Snapshot stable."

- id: T-6.11
  title: integration — test_balance_returns_per_account_and_net_worth
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: stdout empty; green: seeded fixture + CliRunner; refactor: helper _seed_postings}
  files_touched: [tests/integration/test_cli_balance.py]
  tests_added: [tests/integration/test_cli_balance.py::test_balance_returns_per_account_and_net_worth]
  depends_on: [T-6.7]
  acceptance: "Output contains per-account lines and net worth."
```

---

## PR 7 — Hardening · `feat/07-hardening` · target ≤300 lines

**Goal**: Cross-cutting acceptance (proposal §13), error UX polish, exit-code assertions, coverage gates, README. **Scope**: error UX, CI smoke, README install + examples, pre-commit config, coverage gate. **Deps**: all prior PRs. **Tests**: integration tests for every proposal acceptance, exit-code assertions, README code blocks.

**Work-unit commit sequence**: `T-7.1..7.4 red|green (acceptance + UX)` → `T-7.5 (docs)` → `T-7.6..7.8 red|green (gates + pre-commit)` → `[changelog commit]`.

```yaml
- id: T-7.1
  title: Cross-cutting acceptance — proposal §13 scenarios as integration tests
  estimate: M
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: scenarios uncovered; green: parametrize acceptance list; refactor: helper _acceptance_scenarios}
  files_touched: [tests/integration/test_acceptance.py]
  tests_added: [tests/integration/test_acceptance.py]
  depends_on: [PR 1..6 merged]
  acceptance: "Every proposal §13 bullet covered by an integration test."
  risks: "Acceptance bullets in proposal text ambiguous; map to spec contracts."

- id: T-7.2
  title: Error UX — Rich panels (red=Validation, yellow=Config, plain=runtime)
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: plain stderr; green: Console(stderr=True) + Panel; refactor: helper _render_error}
  files_touched: [src/pyfintracker/cli.py]
  tests_added: [tests/integration/test_error_ux.py]
  depends_on: [PR 1..6 merged]
  acceptance: "Each error class renders in correct panel style."

- id: T-7.3
  title: Exit-code assertions — 0/1/2/3/130 per scenario
  estimate: S
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: missing assertions; green: parametrize (scenario, expected_exit); refactor: fixture _cli_runner}
  files_touched: [tests/integration/test_exit_codes.py]
  tests_added: [tests/integration/test_exit_codes.py]
  depends_on: [PR 1..6 merged]
  acceptance: "Matrix covers all 5 exit codes per design §4 mapping."

- id: T-7.4
  title: CI migration smoke double-check (covered in T-1.16 but verify non-regression)
  estimate: XS
  preflight: []; test_cycle: tdd; quality_gates: []
  tdd_cycle: {red: silent regression; green: re-run T-1.16 against current schema; refactor: add .github/workflows/ci.yml}
  files_touched: [.github/workflows/ci.yml, tests/integration/test_migrations.py]
  tests_added: [tests/integration/test_migrations.py::test_migrations_smoke_idempotent]
  depends_on: [PR 1..6 merged]
  acceptance: "Triple upgrade/downgrade cycle still passes."

- id: T-7.5
  title: README — install + basic usage examples (from proposal §UX)
  estimate: M
  preflight: []; test_cycle: standard; quality_gates: []
  tdd_cycle: {red: readme missing sections; green: write install + 6 example blocks; refactor: extract _examples}
  files_touched: [README.md]
  tests_added: []
  depends_on: [PR 1..6 merged]
  acceptance: "uv tool install + fin init + fin add --from/--to example covered."
  risks: "Code-block linting; embed bash that double-runs in CI smoke."

- id: T-7.6
  title: Coverage gate — pytest --cov-fail-under=70 global, 90%+ money
  estimate: S
  preflight: []; test_cycle: standard; quality_gates: []
  tdd_cycle: {red: gate missing in pyproject; green: add [tool.pytest.ini_options] addopts; refactor: per-module threshold}
  files_touched: [pyproject.toml]
  tests_added: []
  depends_on: [PR 1..6 merged]
  acceptance: "`uv run pytest` exits non-zero if global <70% or money modules <90%."

- id: T-7.7
  title: ruff + mypy --strict clean
  estimate: S
  preflight: []; test_cycle: standard; quality_gates: []
  tdd_cycle: {red: lint/type errors; green: enable strict, fix; refactor: add overrides per module}
  files_touched: [pyproject.toml, src/pyfintracker/**/*.py]
  tests_added: []
  depends_on: [PR 1..6 merged]
  acceptance: "`uv run ruff check` and `uv run mypy src` exit 0."

- id: T-7.8
  title: pre-commit hook — wire test_no_float_amounts + test_money_columns_text
  estimate: S
  preflight: []; test_cycle: standard; quality_gates: []
  tdd_cycle: {red: hook missing; green: .pre-commit-config.yaml + local hook; refactor: extract common hook runner}
  files_touched: [.pre-commit-config.yaml]
  tests_added: [tests/unit/test_no_float_amounts.py, tests/unit/test_money_columns_text.py]
  depends_on: [T-1.15, T-3.6]
  acceptance: "`pre-commit run --all-files` triggers both gates; floating-point annotation blocked from commit."
```

---

## Cross-cutting concerns (PR 7)

- **README install + basic usage** — see T-7.5. Examples: `uv tool install`, `fin init`, `fin account new`, `fin add --from --to`, `fin balance`, `fin report month`.
- **Error UX**: red panel for `ValidationError`/`InvariantError` (T-7.2); yellow panel for `ConfigError`/`NotInitializedError`; plain stderr for runtime `ReplRequiresTTYError`. Exit codes per B2 mapping (T-7.3).
- **Exit code assertions** — 0 ok · 1 Validation/Invariant/AccountNotFound · 2 runtime REPL · 3 NotInitialized/Config · 130 abort. Asserted per integration test in T-7.3.
- **CI migration smoke** — `alembic upgrade head && downgrade base && upgrade head` lives in T-1.16, re-verified in T-7.4.
- **Strict TDD coverage** — `--cov-fail-under=70` global, 90%+ money modules (T-7.6).
- **Pre-commit gates** — `test_no_float_amounts` + `test_money_columns_text` (T-7.8).

## Required property tests — pinned

| Test | Property | Task ID |
|---|---|---|
| `test_double_entry_invariant_holds` | random postings summing to zero: validate_transaction() succeeds | **T-4.9** |
| `test_decimal_quantization_per_currency` | ∀ Decimal × currency: roundtrip+quantize | **T-3.7** |
| `test_account_name_regex` | ∀ string: re.fullmatch ↔ validate_account_name | **T-2.13** |
| `test_decimal_text_roundtrip` | Decimal → str → Decimal == Decimal normalized | **T-3.8** |
| `test_no_float_amounts_in_models` | AST scan: zero `float` annotations in money code | **T-1.15** |

## Required integration tests — pinned

| Test | Scenario | Task ID |
|---|---|---|
| `test_migrations_smoke` | upgrade/downgrade/upgrade head idempotent | **T-1.16** |
| `test_cli_init_refuses_if_db_exists` | second `fin init` exits 1 | **T-1.17** |
| `test_cli_init_force_recreates` | `--force` rebuilds DB | **T-1.17** |
| `test_add_flags_mode_creates_two_posting_txn` | `--from --to` writes 2 postings | **T-4.11** |
| `test_add_repl_creates_three_posting_txn` | REPL writes 3 postings, balanced | **T-5.10** |
| `test_report_month_renders_snapshot` | snapshot matches syrupy stored | **T-6.9** |
| `test_balance_returns_per_account_and_net_worth` | per-account + net worth footer | **T-6.11** |

Plus bonus integration tests per PR (**T-2.14/2.15**, **T-4.12/4.13/4.14/4.15**, **T-5.11/5.12**, **T-7.1/7.2/7.3/7.4**).

## Cross-PR dependencies

```text
PR 1 ── PR 2 ─┐                       ┌─ PR 5
             ├─ PR 4 ─────────────────┘
PR 1 ── PR 3 ┘
PR 2 ──────── PR 6 (uses accounts + postings)
PR 1..6 ───── PR 7 (hardening)
```

## Commit discipline per PR

```text
For each PR, work-unit commits interleaved:
  1. red(test)   → failing test
  2. green(impl) → minimum code to pass
  3. repeat per task in topological order
  4. refactor    → cleanup with tests green
  5. docs        → README/changelog (PR 5+ only)
  6. pre-commit  → guards active (PR 7 only)
```

---

## Constraints honoured

- TDD mode `strict`: every task has explicit red/green/refactor + declared `test_cycle`/`quality_gates`.
- Greenfield: no `preflight` required.
- 7-PR plan honoured; each ≤400 lines per design §11.
- All 5 required property tests pinned with task IDs.
- All 7 required integration tests pinned with task IDs.
- Money invariants: Decimal-only enforced via T-1.15 (AST scan) + T-3.1 (DecimalAsText) + T-3.4 (validate_amount rejects float).
- Atomic writes: T-4.6 enforces `with conn.begin():`; DB-level CHECK no-zero posting from 0001 migration (T-1.5).
