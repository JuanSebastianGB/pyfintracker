# AGENTS.md — pyfintracker

## Project context

Personal finance CLI. Strict double-entry bookkeeping, SQLite, multi-currency (COP default), local-first. Wave 1 (MVP) is the active change.

## Stack

- Python 3.12+, uv, hatchling
- Typer (CLI), Pydantic v2 (validation), SQLAlchemy 2.0 Core (no ORM), SQLite, Alembic (migrations)
- Rich (output), httpx (HTTP — Wave 2)
- pytest + hypothesis + syrupy (test pyramid)
- ruff + mypy --strict (lint/types)

## Architecture

Lazy-clean. 4 core files:

- `src/pyfintracker/models.py` — dataclasses for Account, Transaction, Posting, Rate
- `src/pyfintracker/repository.py` — SQLAlchemy Core queries
- `src/pyfintracker/reports.py` — report logic (monthly, balance)
- `src/pyfintracker/cli.py` — Typer commands (entry point: `fin`)
- Plus `db.py`, `config.py`, `validation.py`

Domain in models. Persistence in repository. Presentation in CLI. No DDD layers.

## Money invariants (non-negotiable)

- **Always `Decimal`, never `float`** for amounts. Period.
- Storage in SQLite as **TEXT** (preserves Decimal precision).
- Per-currency precision: COP/JPY = 0 decimals; USD/EUR/GBP = 2 decimals.
- Rounding mode: `ROUND_HALF_UP`.
- Every transaction must balance: `sum(postings) == 0` or it does NOT save.
- Atomic writes: txn is all-or-nothing. No partial DB states.

## Account naming

Regex enforced at creation: `^[A-Z][a-z]+:[A-Z][\w-]+(:[A-Z][\w-]+)?$`

- 5 root types only: `Assets`, `Liabilities`, `Equity`, `Income`, `Expenses`
- Max 3 levels deep
- Each account: exactly one currency

## Conventions

- ID: sequential integer per table
- Date: ISO `YYYY-MM-DD`, no timezone (date only)
- DB default location: `~/.local/share/fin/fin.db` (XDG data dir)
- Config default location: `~/.config/fin/config.toml` (XDG config dir)
- Config precedence: defaults < file < env vars (`FIN_*`) < CLI flags

## Testing

Strict TDD mode enabled. Pyramid:

- `tests/unit/` — pure logic, no I/O
- `tests/integration/` — full DB roundtrip, CliRunner
- `tests/property/` — hypothesis-driven invariant tests (sum=0, currency precision)
- `tests/snapshots/` — syrupy snapshots for report output

Coverage: 90%+ on money-touching code, 70%+ global. pytest-cov enforces.

## Workflow

```bash
uv sync                  # install deps
uv run fin --help        # run CLI
uv run pytest            # all tests
uv run pytest -m unit    # just unit
uv run ruff check        # lint
uv run mypy src          # type check
uv run alembic upgrade head   # apply migrations
uv run alembic revision --autogenerate -m "..."  # new migration
```

## SDD artifacts

- `openspec/config.yaml` — phase rules, testing capabilities
- `openspec/changes/finance-tracker/proposal.md` — Wave 1 PRD (active change)
- `openspec/changes/finance-tracker/spec.md` — detailed spec (to be written in spec phase)
- `openspec/changes/finance-tracker/design.md` — design decisions (to be written in design phase)
- `openspec/changes/finance-tracker/tasks.md` — implementation tasks (to be written in tasks phase)

## Don'ts

- Don't use `float` for money. Ever. mtype hints must be `Decimal`.
- Don't allow custom root account types (only Assets/Liabilities/Equity/Income/Expenses).
- Don't save partial/draft transactions to DB.
- Don't use SQLAlchemy ORM (only Core — explicit SQL).
- Don't add FastAPI or any web framework — this is a CLI.
- Don't publish to PyPI before v1.0 stability.