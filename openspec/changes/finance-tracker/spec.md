---
type: spec
id: finance-tracker-spec
status: draft
tags: [python, cli, finance, double-entry, sqlite, mvp, spec]
parent_proposal: finance-tracker
parent_design: null
parent_tasks: null
---

# Spec — finance-tracker (Wave 1 MVP Estricto)

Source of truth: engram obs (linked). This file mirrors for downstream consumption.

## Scope

Wave 1 = single-currency COP, local-first CLI, 5-root chart, REPL+flags `fin add`, monthly report + balance, opening balances via `--initial`. Non-goals section below excludes F1–F9.

## Blocker Resolutions (locked)

- **B1. Pydantic-vs-dataclass boundary.** Domain entities (Account, Transaction, Posting, Rate) = frozen `@dataclass`. Validation envelopes / transfer shapes = Pydantic v2. Config = `pydantic-settings` (`settings_customise_sources` for XDG < env < flag precedence). CLI parsing = Typer + Pydantic for cross-field. Repository accepts frozen dataclasses; converts to/from `dict`/`tuple` for SQLAlchemy Core.
- **B2. CLI exit codes (numeric contract).** 0=ok · 1=validation · 2=runtime · 3=config · 130=abort.
- **B3. `fin init` semantics.** Creates SQLite at XDG data dir (`~/.local/share/fin/fin.db`), runs `alembic upgrade head`, seeds 10-account starter chart. Refuses by default if DB exists (`DB exists at <path>; use --force to recreate (DESTRUCTIVE)`); `--force` drops + recreates. NEVER creates opening-balance txns; user runs `fin account new --initial` per funded account.
- **B4. `Equity:OpeningBalances` materialization.** Ships empty in starter chart (zero postings). Only non-zero via `--initial`. Never modified by reports or any other command in Wave 1.

## Design Resolutions (locked)

| # | Decision |
|---|----------|
| D1 | `PRAGMA journal_mode=WAL` on engine init. |
| D2 | `function`-scoped pytest fixture: `:memory:` + `StaticPool` shared across the session. Helper `make_engine()` in `tests/conftest.py`. |
| D3 | Snapshot Console = `Console(file=StringIO(), no_color=True, force_terminal=False, width=120)`. Syrupy `autofix=False` in CI. |
| D4 | Description: optional, default `""`, whitespace stripped, max 256 chars. |
| D5 | Date: ISO `YYYY-MM-DD` strict, no timezone (calendar date), future allowed, reject `0000-00-00` and malformed. |
| D6 | Currency coherence: every posting.amount.currency == txn.currency == account.currency. Enforced at Pydantic validator. Invariant documented so Wave 2 needs no schema surgery. |
| D7 | `fin add` idempotency: every invocation produces a NEW auto-incremented txn. No dedup. Undo = Wave 2. |
| D8 | Account rename: NEVER in Wave 1. `fin account new <existing-canonical>` is idempotent (no-op). |
| D9 | REPL abort (`:abort` or CTRL-C): discard WIP. No draft state ever touches the DB. |

---

## Contract b. Double-entry invariant (safety floor)

### API surface
- Implicit on every `fin add` save path and every `fin account new --initial` synthetic-txn path.
- Validator entrypoint: `validate_transaction(txn) -> None` raises `InvariantError` family.

### Validation rules (fail-fast order, most-actionable first)
1. `count(postings) >= 2` → `Transactions require ≥2 postings` (exit 1).
2. Each posting `amount != 0` → `Posting amount must be non-zero` (exit 1).
3. Each posting `amount.currency == account.currency` → `Posting currency must match account currency` (exit 1).
4. `sum(per-currency amounts) == 0` exact (no epsilon) → `Unbalanced transaction: sum=<N> <CUR>` (exit 1).
5. Atomic commit: posting rows + txn row in single `with engine.begin():` block (rolls back on any failure).

### Edge cases
- Single posting → reject (rule 1).
- All postings sum to a non-zero residue → reject (rule 4).
- Mixed-currency postings → reject per-currency bucket mismatch (rule 4, Wave 2 spec).
- Posting with `amount = 0` → reject (rule 2).
- DB failure mid-insert → rollback; no partial state.
- Concurrent writers → SQLite WAL serializes; second writer blocks then retries.

### Testable claims
- ∀txn where `repository.save(txn)` returned: count≥2, no-zero, currency-coherent, sum==0.
- ∀txn rejected: 0 rows inserted (atomicity).
- Validator order is fail-fast (most-actionable error wins).

### DB impact
- Tables touched: `transactions` (1 row), `postings` (N rows).
- Transaction boundary: single SQLAlchemy `engine.begin()` block.
- Atomicity guarantee: all-or-nothing; rollback on any failure.

### Requirement: Sum-Zero Atomic Save
The system MUST reject any transaction whose postings violate rules 1–4, and MUST persist accepted transactions atomically.

#### Scenario: balanced 2-posting txn saves
- GIVEN accounts `Assets:Checking` and `Expenses:Food`
- WHEN user saves txn with postings `+50000 COP` / `-50000 COP`
- THEN 1 txn row + 2 posting rows committed atomically
- AND process exit code is 0

#### Scenario: unbalanced txn rejected (atomicity preserved)
- GIVEN draft with postings `+50000 COP` / `-49999 COP`
- WHEN user confirms save
- THEN 0 rows inserted
- AND stderr contains `unbalanced transaction: sum=1 COP`
- AND exit code is 1

#### Scenario: single posting rejected
- GIVEN draft with exactly 1 posting
- WHEN save attempted
- THEN rejected with `transactions require ≥2 postings`

#### Scenario: zero-amount posting rejected
- GIVEN a posting with `amount = 0`
- WHEN save attempted
- THEN rejected with `posting amount must be non-zero`

#### Scenario: currency mismatch rejected
- GIVEN USD posting on a COP account
- WHEN save attempted
- THEN rejected with `posting currency must match account currency`

---

## Contract f. Decimal-only money pipeline

### API surface
- `DecimalAsText` SQLAlchemy `TypeDecorator` (stores TEXT, returns `Decimal`).
- Pydantic `field_validator(mode='before')` on every amount field.
- `quantize_for_currency(amount, currency) -> Decimal` using `ROUND_HALF_UP`.

### Validation rules
1. Accepts `str`/`int`/`Decimal`; coerces to `Decimal` precisely.
2. Rejects `float` with `TypeError("float rejected for money fields; use str or Decimal")` (exit 1).
3. Rejects `Decimal('NaN')` and `Decimal('Infinity')` (exit 1).
4. Quantize to per-currency precision: COP/JPY=0 decimals, USD/EUR/GBP=2.
5. Roundtrip `Decimal → TEXT → Decimal` must be byte-exact.

### Edge cases
- `Decimal('123.456789')` stored in COP column → quantized to `Decimal('123')`.
- `Decimal('1234.567')` in USD → quantized to `Decimal('1234.57')`.
- Trailing zeros preserved through DB roundtrip.
- Negative amounts allowed (sign = direction of value flow).
- `Decimal('1E+10')` stored and read back exact.

### Testable claims
- Roundtrip preserves all 28+ significant digits.
- `float` inputs never reach a money field.
- Custom currency precision is configurable per-currency map.

### DB impact
- Columns typed `DecimalAsText`; underlying SQLite type `TEXT`.
- Migration script (hand-written, NOT autogenerated) declares money columns as TEXT.
- `Numeric` SQLAlchemy type is FORBIDDEN for money columns (loses precision in SQLite).

### Requirement: Decimal-Only Storage and Validation
The system MUST store amounts as `Decimal` in SQLite TEXT columns, MUST reject `float` inputs at the Pydantic boundary, and MUST quantize to per-currency precision using `ROUND_HALF_UP`.

#### Scenario: Decimal roundtrip preserves precision
- GIVEN amount `Decimal('123.456789')`
- WHEN persisted to SQLite and read back
- THEN result equals `Decimal('123.456789')` exactly

#### Scenario: float input rejected
- GIVEN CLI argument `--amount 1.5` (parsed as float)
- WHEN passed to validator
- THEN validator raises `TypeError("float rejected for money fields; use str or Decimal")`

#### Scenario: COP quantizes to 0 decimals
- GIVEN `Decimal('1234.7')` and currency COP
- WHEN quantized for storage
- THEN stored as `Decimal('1235')` (ROUND_HALF_UP)

#### Scenario: USD quantizes to 2 decimals
- GIVEN `Decimal('1234.567')` and currency USD
- WHEN quantized
- THEN stored as `Decimal('1234.57')`

#### Scenario: NaN/Infinity rejected
- GIVEN `Decimal('NaN')` or `Decimal('Infinity')`
- WHEN validated
- THEN rejected with explicit error, exit code 1

---

## Contract c. Opening balance materialization

### API surface
- `fin account new <name> --initial <amount> <currency> [--date YYYY-MM-DD]`
- Auto-creates `Equity:OpeningBalances` if missing in chart.
- Helper: `build_opening_txn(account, amount, date) -> Transaction`.

### Validation rules
1. Account name passes contract `a`.
2. Currency matches account currency (set at creation by this command).
3. Amount > 0 (zero rejected: `--initial 0` → `Opening balance must be positive`).
4. Date is valid ISO `YYYY-MM-DD` (D5).
5. Account MUST have 0 postings (post-condition: SELECT COUNT FROM postings WHERE account_id = ? → 0). Otherwise reject: `Account already initialized; Wave 1 doesn't permit re-initialization.`
6. Equity offset amount = `-account_amount`. Single synthetic txn.

### Edge cases
- Account exists with 0 postings → re-init allowed (Wave 1 ambiguity: rejected by rule 5 above; user runs a regular txn for additional openings).
- Account doesn't exist → auto-create then initialize.
- `Equity:OpeningBalances` missing → auto-create as zero-balance equity account.
- Date in the future → allowed (planned deposit).
- Date pre-dates starter chart creation → allowed.

### Testable claims
- Post-condition: `SUM(amount) over all postings` == 0 after any `--initial`.
- Equity offset account exists with non-zero balance iff ≥1 account initialized.
- Re-init attempt produces 0 rows.

### DB impact
- Tables touched: `accounts` (1 row, the new account), `accounts` (1 row, `Equity:OpeningBalances` if missing), `transactions` (1 row), `postings` (2 rows).
- Atomicity: all in one `engine.begin()` block.

### Requirement: Synthetic Opening Txn on `--initial`
The system MUST create the account (if absent) AND a synthetic 2-posting transaction: `<new>: +<amount>` / `Equity:OpeningBalances: -<amount>`. MUST reject re-initialization of an account with any postings.

#### Scenario: first-time initialization succeeds
- GIVEN `Assets:Checking` does not exist
- WHEN `fin account new Assets:Checking --initial 500000 COP`
- THEN account + 1 txn + 2 postings committed
- AND `Equity:OpeningBalances` exists

#### Scenario: re-initialization rejected
- GIVEN `Assets:Checking` has ≥1 posting
- WHEN user runs `--initial` again
- THEN system rejects with `account already initialized`
- AND exit code 1, 0 rows inserted

---

## Contract a. Account creation rules

### API surface
- `fin account new <name> [--currency COP] [--description ""]`
- `fin account list [--currency COP] [--root Assets]`
- Lookup is case-insensitive against canonical form.

### Validation rules
1. Regex `^[A-Z][a-z]+:[A-Z][\w-]+(:[A-Z][\w-]+)?$` enforced post-normalize.
2. Normalize at boundary: `assets:checking` → `Assets:Checking` (PascalCase segments).
3. Root MUST be one of: `Assets|Liabilities|Equity|Income|Expenses` (5 fixed).
4. Max depth 3 (root + 2 children).
5. Parent MUST exist before child (root itself has no parent).
6. Length cap 64 chars (constant `ACCOUNT_NAME_MAX_LEN`).
7. Currency defaults to COP; once set, immutable (no API to change in Wave 1).
8. Re-running `fin account new` with same canonical name + currency = idempotent no-op (returns existing).

### Edge cases
- Lowercase input → normalized, no error.
- Mixed case input `Assets:checking` → normalized to `Assets:Checking`.
- 4-level-deep → rejected (depth cap).
- Custom root `CustomRoot:Foo` → rejected.
- Child without parent → rejected.
- Empty string or whitespace-only → rejected (regex).
- `--currency USD` on existing `Assets:Checking` (COP) → rejected (currency immutable).

### Testable claims
- ∀ string s: `re.fullmatch(REGEX, normalize(s))` iff s is a valid account name.
- ∀ account created: stored name equals canonical form.
- ∀ child creation: parent row exists in `accounts` table.
- ∀ rename attempt: rejected (no API in Wave 1).

### DB impact
- Table: `accounts` (1 row per create, idempotent on duplicate).
- No postings created by `account new` alone (only `--initial` does).
- Atomicity: single insert.

### Requirement: Strict Account Naming and Hierarchy
The system MUST enforce regex + 5-root set + 3-level depth + parent-exists + 64-char cap, and MUST fix currency at creation.

#### Scenario: lowercase normalized to canonical
- GIVEN input `assets:checking`
- WHEN account created
- THEN stored as `Assets:Checking`

#### Scenario: invalid regex rejected
- GIVEN input `FOO:bar` (lowercase segment)
- WHEN creation attempted
- THEN rejected with regex violation message

#### Scenario: custom root type rejected
- GIVEN input `CustomRoot:Foo`
- WHEN creation attempted
- THEN rejected: `root must be one of Assets|Liabilities|Equity|Income|Expenses`

#### Scenario: depth cap enforced
- GIVEN `Assets:Checking:Sub` exists (depth 3)
- WHEN creating `Assets:Checking:Sub:More`
- THEN rejected with `max depth 3 exceeded`

#### Scenario: parent must exist
- GIVEN `Assets:Checking` does not exist
- WHEN creating `Assets:Checking:Subsidiary`
- THEN rejected with `parent account Assets:Checking not found`

#### Scenario: duplicate name idempotent
- GIVEN `Assets:Checking` exists (COP)
- WHEN `fin account new Assets:Checking --currency COP`
- THEN no error, no new row, exit 0

---

## Contract e. REPL flow for >2 postings

### API surface
- `fin add` (no `--from`/`--to` flags) → enters REPL.
- `fin add --from <acct> --to <acct> <date> <desc> <amount> <ccy>` → 2-posting flag mode.
- REPL prompt order: date → description → total (informational) → posting loop.
- Posting loop prompts: `[n] account (autocomplete): ` then `[n] amount: `.

### Validation rules
1. Date: ISO `YYYY-MM-DD`, default today (D5).
2. Description: optional, ≤256 chars, stripped (D4).
3. Total: computed from sum of absolute inflows, displayed only.
4. Account: normalized per contract `a`; live-rejects invalid input inline.
5. Amount: accepts `50000`, `-50000`, `50,000`, `50000.00`; rejects `0`, empty, non-numeric.
6. After each posting, display `Residual: +X / 0 ✓`.
7. Empty line on account prompt: ends loop ONLY if residual=0; else re-prompt.
8. Final prompt: `Save? [Y/n]: ` default Y; on commit prints `Saved as txn #NNNN`.
9. `:abort` typed at any prompt → discard WIP, exit 130.
10. CTRL-C → prompt `discard? [Y/n]` default Y; on Y exit 130, on N re-enter loop.

### Edge cases
- Residual non-zero + empty-line → re-prompt (not silent abort).
- Negative amount entered → accepted; signs determine direction of flow.
- Account name with case-mismatch → normalized, no error.
- `:abort` during amount prompt → discard entire txn.
- CTRL-C during final save prompt → handled same as `:abort`.
- REPL invoked when stdin is non-TTY → fail with `REPL requires interactive terminal` (exit 2).

### Testable claims
- REPL with N postings summing to 0 → saves with auto-id.
- REPL with N postings summing ≠ 0 → never saves.
- `:abort` at any prompt → 0 DB writes.
- CTRL-C defaults to discard (Y).

### DB impact
- Same as contract `b` (1 txn + N postings, atomic).
- No draft rows ever inserted (D9).

### Requirement: Interactive Posting Entry
When `fin add` is invoked without `--from/--to`, the system MUST enter REPL with the prompt sequence above. `:abort` and CTRL-C MUST discard WIP.

#### Scenario: balanced 3-posting REPL saves
- GIVEN user enters REPL
- WHEN 3 postings summing to 0 are entered
- AND user confirms `Y`
- THEN txn saved with auto-id
- AND stdout shows `Saved as txn #NNNN`

#### Scenario: empty-line re-prompts when residual ≠ 0
- GIVEN residual != 0
- WHEN user hits enter on account prompt
- THEN system re-prompts with `Add another posting or fix amount (:abort to discard)`

#### Scenario: `:abort` discards
- GIVEN user mid-REPL
- WHEN user types `:abort`
- THEN no DB write
- AND exit code 130

#### Scenario: CTRL-C defaults to discard
- GIVEN user mid-REPL
- WHEN CTRL-C pressed
- THEN prompt `discard? [Y/n]` (default Y)
- AND on Y, exit code 130

---

## Contract d. Monthly report

### API surface
- `fin report month [--month YYYY-MM] [--no-rollup]`
- Default month = current calendar month (today's local date).
- Helper: `build_monthly_report(conn, year, month, rollup: bool) -> Report`.

### Validation rules
1. `--month` parses as ISO `YYYY-MM`; reject malformed.
2. Currency filter: Wave 1 = COP only; reject `--currency USD` flag (Wave 2).
3. Empty month still listed with `0` + comment `no transactions`.
4. Sections: INGRESOS (Income), GASTOS (Expenses), NETO (net).
5. Order within section: by absolute magnitude descending.
6. Rollup (default ON): parent rows aggregated; leaves indented beneath.
7. `--no-rollup`: leaves only, no aggregation.
8. Per-day sparkline per expense line: width=10 block chars (rich `Sparkline`), padded with `─` for shorter months.
9. Display formatting per COP convention: `1.234.567` (thousands dot, no decimals).

### Edge cases
- Month with no txns → all sections `0` + `no transactions` comment.
- Month with only income → expenses section `0`, neto positive.
- Month with only expenses → income section `0`, neto negative.
- Account with 0 net flow → not listed.
- Sparkline on a 28-day month → leading `─` padding to align with 31-day months.
- Currency display: `+2.252.500 COP` (signed, no decimals for COP).

### Testable claims
- ∀ month: income sum + (-expense sum) == net sum (algebraic identity).
- ∀ expense line: sparkline width == 10.
- ∀ section: ordering by absolute value descending.
- Rollup sum == leaf sum (consistency invariant).

### DB impact
- Read-only: `transactions`, `postings`, `accounts` (joins).
- No writes; no transaction needed beyond implicit read snapshot.

### Requirement: Income/Expense Breakdown with Sparklines
`fin report month` MUST aggregate income/expense txns in the month (default current), roll up by default with leaves indented, order by absolute magnitude, render per-day sparkline width=10, show net.

#### Scenario: current month default
- GIVEN today is 2026-07-16
- WHEN `fin report month`
- THEN report covers 2026-07-01..2026-07-31

#### Scenario: empty month shows zeros + comment
- GIVEN no txns in 2026-08
- WHEN `fin report month --month 2026-08`
- THEN all sections show `0` + comment `no transactions`

#### Scenario: rollup aggregates children
- GIVEN `Expenses:Food:Groceries` and `Expenses:Food:Restaurants` have txns
- WHEN `--no-rollup` not set
- THEN `Expenses:Food` row aggregates both
- AND children shown indented

#### Scenario: sparkline width 10
- GIVEN 31 days in month
- WHEN sparkline rendered
- THEN exactly 10 block chars wide

---

## Non-Goals (explicit F1–F9 exclusions)

- **F1.** Multi-currency conversion, FX rates (Frankfurter), cross-currency postings.
- **F2.** Recurring transactions, budgets, tags, search.
- **F3.** Textual TUI browser.
- **F4.** CSV bank import, plain-text ledger export.
- **F5.** PyPI publish (post-v1.0).
- **F6.** Net-worth-over-time tracking (balance snapshots).
- **F7.** Backup strategy / destructive-op snapshots.
- **F8.** Account redirect aliases (renamed-account bridge).
- **F9.** Materialized balance views (compute-on-the-fly OK for Wave 1).

---

## Test Pyramid (per contract)

| Contract | Unit | Integration | Property (hypothesis) | Snapshot (syrupy) |
|----------|------|-------------|----------------------|-------------------|
| a (accounts) | regex match, normalize, length cap, root enum | upsert parent check, duplicate idempotency | name regex with random strings | — |
| b (double-entry) | validator order, error types | atomic commit roundtrip via CliRunner | ∀random posting sets: sum==0 ↔ accepted | — |
| c (opening bal) | `build_opening_txn` builder | `--initial` end-to-end (CliRunner) | post-condition: SUM(all postings) == 0 | — |
| d (report) | rollup aggregation, ordering, sparkline padding | CliRunner monthly report on seeded DB | — | full Rich output per scenario |
| e (REPL) | prompt-fn mock, abort path | CliRunner `--interactive` (or default) | — | balance/prompt strings |
| f (decimal) | `DecimalAsText` codec, `quantize_for_currency` | DB roundtrip via `make_engine()` | ∀Decimal: roundtrip exact; ∀currency: precision enforced; ∀float-input: rejected | no-float AST scan (`tests/unit/test_no_float_amounts.py`) |

Coverage targets: 90%+ on `models.py` + `repository.py` + `validation.py`; 70%+ global (enforced by `pytest --cov-fail-under=70`).

Property tests required for:
1. Double-entry sum=0 with random txn sizes (b).
2. Decimal quantization per currency (f).
3. Account name regex with random strings (a).
4. Roundtrip `Decimal → TEXT → Decimal` precision preservation (f).

---

## Cross-cutting Acceptance (mapped to proposal §"Acceptance criteria")

| Proposal criterion | Spec coverage |
|--------------------|---------------|
| `uv sync && uv run fin init` creates DB with starter chart | B3, contract `a` |
| `fin account new` / `fin account list` | contract `a` |
| `fin account new --initial` creates account + equity txn | contract `c` |
| `fin add --from/--to` saves 2-posting txn, sum=0 | contract `b` + `e` |
| `fin add` REPL mode saves multi-posting | contract `e` |
| `fin report month` produces breakdown + sparklines | contract `d` |
| `fin balance` shows per-account + net worth | deferred to balance sub-spec (single command, see report's rollup logic; uses same Sum-Zero invariants) |
| `fin config show` shows effective config + source | contract B1 (`pydantic-settings`) |
| All 4 test layers pass | test pyramid table |
| Coverage ≥90% / ≥70% | explicit targets above |
| `ruff check` + `mypy --strict` clean | D4, D5, F (Decimal hints) |
| `alembic upgrade/downgrade` clean | hand-written migration (R1 mitigation) |
| README documents install + usage | out of scope (post-apply phase) |

---

## Risks (spec-phase)

- **R1.** Alembic autogenerate may emit `NUMERIC` despite TEXT-as-Decimal intent → hand-write first migration; declare money columns as TEXT explicitly.
- **R2.** Pydantic v2 + `Decimal` + `strict=True` blocks int→Decimal coercion → targeted validators, not blanket strict mode on amount-bearing models.
- **R3.** Rich ANSI in snapshots is flaky → D3 fix (`no_color=True`, `force_terminal=False`, `width=120`).
- **R4.** SQLite `:memory:` is per-connection → D2 fix (`StaticPool`).
- **R5.** REPL test flakiness (mocking `typer.prompt`) → contract `e` testable via injected `prompt_fn`, not raw stdin.
- **R6.** mypy --strict + Decimal-as-field has weird narrowing → define narrowing manually in `models.py`.
- **R7.** `fin balance` was underspecified in proposal (no acceptance criterion beyond "shows per-account + net worth") → spec above scopes it via contract `d` rollup + contract `b` sum-zero invariants; design phase may add a dedicated sub-spec if complexity warrants.