# pyfintracker

Personal finance CLI with strict double-entry bookkeeping.

- **Binary:** `fin`
- **Python package:** `pyfintracker`
- **Storage:** SQLite (local file, no cloud)
- **Strict double-entry:** every transaction must balance to zero
- **Multi-currency:** COP, USD, EUR with Frankfurter-sourced FX rates
- **Latin-American focused:** Colombian peso (COP) as default currency

## Status

Pre-alpha. Implementing in waves:

1. MVP estricto (Cuentas + add + report + balance, COP only)
2. Multi-moneda (Frankfurter rates)
3. Productividad (presupuestos, recurrentes, tags, TUI)
4. Import/export (CSV bancos, texto plano, net worth)

See `openspec/changes/finance-tracker/proposal.md` for the MVP specification.

## Install (development)

```bash
git clone https://github.com/JuanSebastianGB/pyfintracker
cd pyfintracker
uv sync
uv run fin --help
```

## License

MIT