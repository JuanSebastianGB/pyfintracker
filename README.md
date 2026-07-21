# pyfintracker

[![CI](https://github.com/JuanSebastianGB/pyfintracker/actions/workflows/ci.yml/badge.svg)](https://github.com/JuanSebastianGB/pyfintracker/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Track personal finances from the terminal with strict double-entry accounting — multi-currency, local-first, no servers.

`pyfintracker` is a CLI for people who want real bookkeeping discipline without
giving their data to a third party. Every transaction balances. Money is
always `Decimal`, never `float`. Storage is a single SQLite file on disk.

## Installation

```bash
uv tool install pyfintracker
# or
pip install pyfintracker
```

Requires Python 3.12 or newer.

## Quick start

```bash
fin init
fin account new Assets:Cash --currency COP
fin account new Income:Salary --currency COP
fin register "January salary" 1000000 --account Assets:Cash
fin tui
```

Five commands from zero to a populated TUI dashboard. `fin register`
auto-creates the matching `Equity:Registered` account, so the only account
you must set up by hand is the one that receives the money.

## Features

- **Strict double-entry** — every transaction balances or it does not save.
- **Money is `Decimal`** — never `float`. Storage as `TEXT` keeps precision.
- **Multi-currency** — 12 currencies, one per account, with FX conversion.
- **Tags** — global or per-account, attach to any transaction.
- **Full-text search** — FTS5 over transaction descriptions.
- **Recurring transactions** — daily, weekly, monthly, or yearly rules that
  generate balanced postings on demand.
- **Budgets** — monthly or yearly, scoped to an account, a tag, or both.
- **Terminal UI** — Vim-style browser for accounts, transactions, search,
  reports, and budgets.
- **Local-first** — SQLite at `~/.local/share/fin/fin.db`, no network required.

## CLI reference

| Command | What it does |
|---|---|
| `fin init` | Initialize the database |
| `fin migrate [up\|down\|status]` | Manage schema migrations |
| `fin version` | Show version |
| `fin account new <name>` | Create an account (`--currency COP` default) |
| `fin account list` | List accounts |
| `fin add --from A --to B --amount N [--description "..."]` | Add a transaction (flag mode) |
| `fin add` | Add a transaction (interactive REPL) |
| `fin register DESCRIPTION AMOUNT --account A` | One-shot entry that auto-balances via `Equity:Registered` |
| `fin search QUERY [--limit N]` | Full-text search over transaction descriptions |
| `fin tag create NAME [--account A]` | Create a global or account-scoped tag |
| `fin tag list [--account A]` | List tags |
| `fin tag delete NAME [--account A]` | Delete a tag |
| `fin tag add NAME TXN_ID` | Attach a tag to a transaction |
| `fin tag remove NAME TXN_ID` | Detach a tag |
| `fin recurring create NAME FREQ AMOUNT ACCOUNT` | Create a recurring rule |
| `fin recurring list` | List recurring rules |
| `fin recurring due [--date YYYY-MM-DD]` | Show rules due on or before a date |
| `fin recurring generate [--date YYYY-MM-DD]` | Generate postings for due rules |
| `fin recurring delete RULE_ID` | Delete a rule |
| `fin budget create NAME AMOUNT [--period monthly\|yearly]` | Create a budget |
| `fin budget list` | List budgets with current spend |
| `fin budget report [--month YYYY-MM]` | Per-budget progress report |
| `fin budget delete BUDGET_ID` | Delete a budget |
| `fin report month --month YYYY-MM [--currency CCY]` | Monthly income / expense report |
| `fin balance [name] [--currency CCY]` | Balances and net worth |
| `fin convert --amount N --from A --to B [--on DATE]` | One-off currency conversion |
| `fin tui [--db PATH]` | Launch the Textual browser |

Every command accepts `--help`.

## Multi-currency

`pyfintracker` supports 12 currencies natively. Each account has exactly one
currency; transactions stay single-currency (Wave 1 invariant). Reports in
a different currency convert each posting at its transaction date using the
live FX rate.

```bash
fin convert --amount 100 --from USD --to COP
fin convert --amount 100 --from USD --to COP --on 2024-01-15
fin report month --month 2024-01 --currency USD
fin balance --currency EUR
```

Display currency defaults to `COP` and can be set in
`~/.config/fin/config.toml`:

```toml
display_currency = "USD"
```

> The legacy key `default_currency` is still accepted and silently remapped
> to `display_currency`. New configurations should use `display_currency`.

Live rates come from Frankfurter v2 and are cached locally in SQLite. The
latest rate cache TTL is 24 hours; historical rates are cached forever
(rate-at-date is immutable). If neither cache nor network is available, FX
paths exit with code 6.

## Tags

Tags classify transactions. A tag is global by default, or scoped to a
single account when needed (for example `Assets:Cash:business`).

```bash
fin tag create business
fin tag create personal --account Assets:Cash

fin register "Client invoice" 500000 --account Assets:Cash --tag business
fin tag list
fin tag delete business
```

Attach a tag to an existing transaction:

```bash
fin tag add business 42
fin tag remove business 42
```

Tag names are normalized to lowercase, trimmed, and may not contain commas
(reserved for multi-tag syntax).

## Search

Full-text search over transaction descriptions uses SQLite FTS5.

```bash
fin search coffee
fin search "coffee OR lunch" --limit 50
```

Rebuild the index after a bulk import:

```python
# from a Python session against the same DB
from pyfintracker.repository import rebuild_fts
rebuild_fts(conn)
```

## Recurring transactions

A rule describes a balanced posting template that fires on a schedule.
Supported frequencies: `daily`, `weekly`, `monthly`, `yearly`. Generation
handles month-end and leap-year boundaries without `python-dateutil`.

```bash
# Netflix subscription, monthly on the 15th, charged to Assets:Cash
fin recurring create "Netflix" monthly 42900 Assets:Cash \
    --description "Streaming subscription" --start-date 2024-01-15

# What is due today?
fin recurring due

# Generate postings for everything due on or before today
fin recurring generate
```

`generate` inserts balanced transactions and advances each rule's
`next_date`.

## Budgets

A budget caps spending over a period, optionally narrowed to one account,
one tag, or both. The report shows absolute spending (positive postings
only) so balanced transfers do not inflate the total.

```bash
fin budget create "Groceries" 600000 --period monthly --tag groceries
fin budget create "Travel" 3000000 --period yearly

fin budget list
fin budget report --month 2024-03
```

Progress is color-coded in the CLI: green below 80%, yellow at 80–99%, red
at 100% or above.

## Terminal UI

```bash
fin tui
```

Opens a master/detail dashboard with:

- Six-month net-worth trend.
- Current month's income / expense / net.
- Accounts grouped by kind.
- Ten most recent transactions, or live FTS5 results as you type.
- Budget progress per scope.
- Drilldown modal with full transaction details.

Vim-style keys: `j` / `k` move, `h` / `l` switch focus, `Enter` drills down,
`/` focuses the search box, `gg` goes to top, `G` goes to bottom, `q` quits.

## Account naming

Format: `Root:SubCategory` (max three levels). Case-insensitive on input,
normalized on storage.

| Root | Use for |
|---|---|
| `Assets` | Cash, bank accounts, receivables |
| `Liabilities` | Credit cards, loans, payables |
| `Equity` | Opening balances, owner equity, `Registered` (auto) |
| `Income` | Salary, interest, refunds |
| `Expenses` | Food, rent, subscriptions |

Only these five root types are accepted.

## Configuration

Default: `~/.config/fin/config.toml`. Override with `FIN_*` environment
variables or CLI flags.

```toml
display_currency = "USD"
db_path = "/custom/path/to/fin.db"
```

## Development

```bash
uv sync
uv run pytest
uv run pytest -m unit       # pure-logic tests only
uv run pytest -m component  # Textual Pilot component tests
uv run ruff check src/ tests/
uv run mypy src/
```

Test pyramid:

- `tests/unit/` — pure logic, no I/O.
- `tests/integration/` — full DB roundtrip and `CliRunner`.
- `tests/property/` — Hypothesis-driven invariants (sums to zero, currency
  precision).
- `tests/component/` — Textual Pilot tests against a real migrated database.
- `tests/snapshots/` — Syrupy snapshots for report output.

Pre-commit hooks enforce `no-float-in-money`, `no-raw-currency-sum`,
`money-columns-are-text`, Ruff, and strict Mypy. Install with
`uv run pre-commit install`.

## Contributing

Contributions are not currently accepted via this repository — see the
project roadmap for plans to open the contribution path.

## License

[MIT](https://opensource.org/licenses/MIT)
