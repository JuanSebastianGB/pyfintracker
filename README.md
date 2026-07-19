# pyfintracker

Personal finance CLI with strict double-entry bookkeeping. Multi-currency (COP default), local-first SQLite storage.

## Installation

```bash
uv tool install pyfintracker
# or
pip install pyfintracker
```

## Quick start

```bash
# Initialize database
fin init

# Create accounts
fin account new Assets:Cash --currency COP
fin account new Expenses:Food --currency COP
fin account new Income:Salary --currency COP

# Add transaction via flags
fin add --from Income:Salary --to Assets:Cash --amount 1000000 --description "January salary"

# Or via interactive REPL (omit flags)
fin add

# View reports
fin report month --month 2024-01
fin balance
```

## Features

- Double-entry accounting: every transaction balances
- Multi-currency: COP, USD, EUR, GBP, JPY, CAD, AUD, CHF, MXN, BRL, INR, CNY
- Interactive REPL for transaction entry
- Monthly income/expense reports
- Balance sheet with net worth
- SQLite local storage, no server needed

## Multi-currency

pyfintracker supports 12 currencies natively. Each account has exactly one currency;
transactions are still single-currency (Wave 1 invariant preserved). When you
request a report in a different currency than the posting, each posting is
converted at its transaction date using the live FX rate.

```bash
# Convert a one-off amount
fin convert --amount 100 --from USD --to COP

# Convert historical amount
fin convert --amount 100 --from USD --to COP --on 2024-01-15

# Reports in display currency
fin report month --month 2024-01 --currency USD
fin balance --currency EUR
```

Display currency defaults to `COP` and can be set in `~/.config/fin/config.toml`:

```toml
display_currency = "USD"
```

> **B2 migration note**: the legacy key `default_currency` is still accepted and
> silently remapped to `display_currency`. New configurations should use
> `display_currency`.

## FX rates

Live rates are fetched from Frankfurter v2 and cached locally in SQLite. The
cache TTL is 24 hours for the latest rate; **historical rates are cached
forever** (rate-at-date is immutable).

If the network is down and the cache holds a stale (but non-expired) rate, the
cache is returned with a stderr warning. If neither cache nor network
available, the FX paths exit with code 6.

## Converting

`fin convert` performs a one-off currency conversion:

```bash
fin convert --amount 100 --from USD --to COP          # latest rate
fin convert --amount 100 --from USD --to COP --on 2024-06-15   # historical
fin convert --amount 99.99 --from EUR --to USD --json  # JSON output
```

## CLI exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Validation / invariant error |
| 2 | Runtime error |
| 3 | Configuration error |
| 4 | FX rate not found |
| 5 | Invalid FX currency |
| 6 | FX service unavailable |
| 130 | Aborted (Ctrl-C) |

## Documentation

| Command | Description |
|---------|-------------|
| `fin init` | Initialize database |
| `fin migrate [up\|down\|status]` | Migration management |
| `fin version` | Show version |
| `fin account new <name>` | Create account |
| `fin account list` | List accounts |
| `fin add --from A --to B --amount X --desc "..."` | Add transaction |
| `fin add` (no flags) | Interactive REPL entry |
| `fin report month --month YYYY-MM [--currency CCY]` | Monthly report |
| `fin balance [name] [--currency CCY]` | Account balances + net worth |
| `fin convert --amount X --from A --to B [--on YYYY-MM-DD]` | Convert one-off amount |

## Account naming

Format: `Root:SubCategory` (e.g., `Expenses:Food:Delivery`)

Root types: `Assets`, `Liabilities`, `Equity`, `Income`, `Expenses`

Max 3 levels deep. Case-insensitive.

## Configuration

Default: `~/.config/fin/config.toml`
Override via `FIN_*` env vars or CLI flags.

## Development

```bash
uv sync
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
```

Pre-commit hooks enforce no-float-in-money, no-raw-currency-sum, money-columns-are-text,
ruff, and mypy strict. Install with `uv run pre-commit install`.

## License

MIT