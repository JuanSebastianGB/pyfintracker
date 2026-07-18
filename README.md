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
- Multi-currency: COP, USD, EUR, GBP, JPY (more via config)
- Interactive REPL for transaction entry
- Monthly income/expense reports
- Balance sheet with net worth
- SQLite local storage, no server needed

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
| `fin report month --month YYYY-MM` | Monthly report |
| `fin balance [name]` | Account balances + net worth |

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
uv run ruff check src/
uv run mypy src/
```

## License

MIT
