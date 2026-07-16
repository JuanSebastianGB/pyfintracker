---
type: proposal
id: finance-tracker
status: draft
tags: [python, cli, finance, double-entry, sqlite, mvp]
parent_spec: null
---

# Finance Tracker — MVP Estricto

## Why

The user needs a personal finance CLI written primarily in Python to demonstrate language depth outside their existing TypeScript/Rails-heavy portfolio. The tool must be:

- **Solid**: not a toy, but a real accounting system with strict invariants
- **Latin-American focused**: Colombian peso (COP) as default currency
- **Local-first**: no cloud, no telemetry, single SQLite file
- **Daily-usable**: fast entry path so habit-forming

Spreadsheets fail at the double-entry invariant — they let you record `Mercado 50k COP` without specifying which account lost the money. This tool enforces the invariant at write time: every transaction has 2+ postings that sum to zero.

## What Changes

This proposal covers **Wave 1 (MVP Estricto)** of a 4-wave delivery plan. Later waves build on this foundation.

### Capabilities added

1. **Account management** — 5 root types (Assets, Liabilities, Equity, Income, Expenses) with strict naming and depth limits
2. **Transaction capture** — hybrid UX (flags for simple 2-posting txns, REPL for complex splits)
3. **Strict double-entry validation** — every saved txn must sum to 0; no drafts in DB; atomic writes
4. **Monthly report** — income/expense breakdown by category with sparklines
5. **Balance query** — current balance per account, total net worth
6. **Opening balances** — `fin account new --initial` creates account + equity offset txn
7. **Schema migrations** — Alembic from day 1
8. **Configuration** — XDG config file + env vars + flags with explicit precedence
9. **Test pyramid** — unit + integration + property-based (hypothesis) + snapshot (syrupy)
10. **CLI binary** — `fin`, installable via `uv tool install` or `pipx`

### Out of Scope (deferred to later waves)

- Multi-currency support (Wave 2 — Frankfurter FX rates)
- Recurring transactions, budgets, tags (Wave 3)
- Textual TUI browser (Wave 3)
- CSV import from banks, plain-text ledger export (Wave 4)
- PyPI publish (only after v1.0 stability)
- Multi-user, sync, mobile/web interfaces

## Architecture

Lazy-clean — NOT formal DDD. Four core files plus DB + config:

```
src/pyfintracker/
├── __init__.py
├── models.py        # @dataclass Account, Transaction, Posting, Rate
├── repository.py    # SQLAlchemy 2.0 Core queries
├── reports.py       # Monthly/balance report logic
├── cli.py           # Typer commands
├── db.py            # Engine + session factory
├── config.py        # Config loading (XDG + env + flags)
└── validation.py    # Account name regex, sum=0 invariant, currency precision

migrations/          # Alembic migrations
tests/
├── unit/
├── integration/
├── property/
└── snapshots/
```

Domain rules live in `validation.py` (regex, invariants, Decimal precision). Persistence in `repository.py`. Presentation in `cli.py`. Each file is independently testable.

## Naming conventions

- **CLI binary:** `fin` (3 chars, fast to type)
- **Python package:** `pyfintracker`
- **Account names:** `Type:Subname[:Subname]` with regex `^[A-Z][a-z]+:[A-Z][\w-]+(:[A-Z][\w-]+)?$`
- **DB location:** `~/.local/share/fin/fin.db` (XDG data dir)
- **Config file:** `~/.config/fin/config.toml` (XDG config dir)

## Chart of accounts

5 root types, no custom types allowed:

- `Assets:*` — checking, savings, cash, investments
- `Liabilities:*` — credit cards, loans
- `Equity:*` — opening balances, retained earnings
- `Income:*` — salary, gifts received
- `Expenses:*` — food, rent, transport, subscriptions, etc.

Max 3 levels deep. Each account has exactly one currency assigned at creation.

Starter chart in `fin init`:

```
Assets:Checking, Assets:Savings, Assets:Cash
Liabilities:CreditCard
Income:Salary
Expenses:Food:Groceries, Expenses:Food:Restaurants
Expenses:Rent, Expenses:Transport, Expenses:Subscriptions
Equity:OpeningBalances
```

## Data model

Money is always `Decimal` (never `float`). Stored in SQLite as TEXT to preserve precision. Per-currency precision:

- COP, JPY: 0 decimals
- USD, EUR, GBP: 2 decimals
- Custom currencies: configurable

Rounding mode: `ROUND_HALF_UP` (banking standard).

IDs: sequential integer per table. Dates: ISO `YYYY-MM-DD`, no timezone (date only).

## Tech stack

| Layer | Choice | Reason |
|---|---|---|
| CLI framework | Typer | Type-hint-driven, fast entry path |
| Validation | Pydantic v2 | Runtime validation, Rust-fast |
| SQL toolkit | SQLAlchemy 2.0 Core (NOT ORM) | Explicit SQL, cross-DB portability |
| Database | SQLite | Single file, no server |
| Migrations | Alembic | Standard, autogenerate from models |
| Output | Rich | Tables, sparklines, colors |
| HTTP client | httpx | Modern, async-capable (Wave 2) |
| Tests | pytest + hypothesis + syrupy | Pyramid coverage |
| Packaging | uv + hatchling | Modern, fast |
| Lint/types | ruff + mypy strict | Comprehensive coverage |

## UX examples

Simple case (90% of daily txns):
```bash
$ fin add 2026-07-15 "Mercado" 50000 COP \
    --from assets:checking \
    --to expenses:food:groceries
Saved as txn #0042.
```

Complex case (3+ postings, splits):
```bash
$ fin add
Date [today]: 2026-07-15
Description: Cena con amigos
Total: 250000 COP

Postings (empty to finish):
  [1] account: expenses:food:restaurants   amount: 80000
  [2] account: assets:checking             amount: -100000
  [3] account: liabilities:creditcard       amount: -150000
  [4]

Balance: 0 ✓
Save? [Y/n]: y
Saved as txn #0043.
```

Monthly report:
```bash
$ fin report month
JULIO 2026
─────────────────────────────────────
INGRESOS         +3.500.000 COP
  salary:dev              3.500.000

GASTOS            -1.247.500 COP
  food:groceries          -498.000  ▆▆▆▆▆
  food:restaurants        -312.500  ▆▆▆
  transport               -210.000  ▆▆
  subscriptions           -127.000  ▆
  rent                    -100.000  ▆

NETO             +2.252.500 COP
```

## Impact

### New files

- `src/pyfintracker/` — package skeleton (8 files)
- `migrations/versions/0001_initial_schema.py` — first Alembic migration
- `tests/{unit,integration,property,snapshots}/` — test pyramid
- `openspec/config.yaml` — SDD configuration
- `openspec/changes/finance-tracker/{proposal,spec,design,tasks}.md` — SDD artifacts
- `AGENTS.md` — project conventions for AI agents
- `README.md` — install + usage
- `pyproject.toml` — already configured with entry point, scripts, lint/type config

### Dependencies (already added)

- Runtime: typer, pydantic, sqlalchemy, alembic, rich, httpx
- Dev: pytest, pytest-cov, hypothesis, syrupy, ruff, mypy

### Risks

| Risk | Mitigation |
|---|---|
| Decimal precision bugs in money arithmetic | Property-based tests with hypothesis on every arithmetic path |
| Alembic autogenerate produces bad migrations | Manual review of every generated migration before commit |
| Strict validation too annoying for daily use | Keep REPL mode forgiving in prompts; only validation is at save time |
| Account naming inconsistency (case typos) | Regex enforced at creation; starter chart demonstrates convention |
| SQLite single-writer bottleneck | Not a concern for solo use; documented in design |
| Decimal vs float confusion | `mypy --strict` + `Decimal` type hints everywhere; pre-commit hook blocks `float` for amounts |

## Phased delivery (full plan)

| Wave | Scope | Est. duration |
|---|---|---|
| **1. MVP Estricto** | This proposal — accounts, txn capture, monthly report, balance, opening balances, Alembic, starter chart, test pyramid | 1-2 weeks |
| **2. Multi-moneda** | Frankfurter rates, conversion, `--currency` flag in reports | 1 week |
| **3. Productividad** | Budgets, recurring txns, tags, search, Textual TUI browser | 2 weeks |
| **4. Import/export** | CSV bank import, plain-text ledger export, net worth tracking | 2 weeks |

After Wave 1, the project is shippable as a v0.1 personal-use release. PyPI publish comes after v1.0 stability.

## Acceptance criteria for Wave 1

- [ ] `uv sync && uv run fin init` creates DB with starter chart
- [ ] `fin account new <name>` and `fin account list` work
- [ ] `fin account new assets:foo --initial 50000 COP` creates account + opening equity txn
- [ ] `fin add` with `--from/--to` flags saves a 2-posting txn that validates sum=0
- [ ] `fin add` without flags enters REPL mode and saves multi-posting txns
- [ ] `fin report month` produces income/expense breakdown in COP with sparklines
- [ ] `fin balance` shows current balance per account + total net worth
- [ ] `fin config show` shows effective config with source (default/file/env/flag)
- [ ] All 4 test layers pass (unit, integration, property, snapshot)
- [ ] Coverage ≥90% on `models.py` + `repository.py`, ≥70% global
- [ ] `ruff check` and `mypy --strict` pass clean
- [ ] `alembic upgrade head` and `alembic downgrade base` work cleanly
- [ ] README documents install + basic usage with examples

## Open questions deferred to Wave 1 design phase

None — all architectural decisions resolved during grilling session before this proposal.