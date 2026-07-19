---
type: proposal
id: multi-moneda
status: draft
tags: [python, cli, finance, fx, multi-currency, frankfurter, wave-2]
parent_spec: null
parent_design: null
parent_tasks: null
---

# Proposal: Multi-moneda (Wave 2A)

## Why now

Wave 1 is single-currency COP. The owner holds COP savings plus USD/EUR/GBP accounts; `fin report month` and `fin balance` sum raw `Decimal` amounts across currencies as if all COP — net worth is meaningless. Wave 2A delivers honest display conversion. Each account and posting keeps one currency (Wave 1 invariant); cross-currency transactions defer to Wave 2B because they break `sum(postings) == 0`.

## What Changes

1. **`fin convert <amount> <from> <to> [--date YYYY-MM-DD]`** — pair conversion with effective rate and date.
2. **`fin report month --currency X`** and **`fin balance --currency X`** — convert via transaction date.
3. **Default display currency** — `display_currency = "COP"` in `~/.config/fin/config.toml`; `FIN_DISPLAY_CURRENCY` env override.
4. **Frankfurter v2 client** (`src/pyfintracker/fx.py`) — `httpx`, no API key, 5s timeout, `Decimal` parsing, normalized errors.
5. **Persistent rates cache** — reuse `rates` table; latest TTL 24h, historical cached forever.
6. **`Rate` frozen-dataclass model** — the entity Wave 1 design §3 promised but never shipped.
7. **`transactions.currency` persistence** — migration `0002_add_transaction_currency.py`; backfill from dominant posting currency.
8. **Stale rate fallback** — Frankfurter down + cache hit → use last fetched with stderr warning; historical rows never stale.

## Out of Scope (Wave 2B / later)

Multi-currency postings in one txn · auto `Equity:FXConversion` posting · cross-currency invariant + per-posting rate context · mark-to-market revaluation · dynamic precision for all 201 v2 currencies · provider pinning · bulk historical sync · `--offline` flag.

## User-facing UX

```
$ fin convert 50000 COP USD
50000 COP = 15.36 USD (rate 0.000307, 2026-07-18, frankfurter)

$ fin convert 100 USD COP --date 2024-01-15
100 USD = 392450.00 COP (rate 3924.50, 2024-01-15, frankfurter)

$ fin report month --month 2026-07 --currency USD
July 2026 (USD)            Income    Expense    Net
  Assets:USDC:Revolut         0.00   120.00  -120.00
  Assets:COP:Nequi          45.30     8.10    37.20
TOTAL                                  -82.80 USD

$ fin balance --currency EUR
Net worth: 1,420.55 EUR (5 accounts, 3 currencies, 2026-07-18)
```

## Tech Choices

| Decision | Pick | Why |
|---|---|---|
| FX provider | Frankfurter **v2** (`api.frankfurter.dev/v2`) | v1 returns 404 for COP. |
| HTTP | `httpx>=0.28.1` | Already in `pyproject.toml`. |
| Cache | SQLite `rates` table | Survives restarts; auditable. |
| TTL | 24h latest, ∞ historical | Latest drifts; historical is frozen. |
| Valuation | transaction date | Deterministic historical reports. |
| Module | new `fx.py` + `Rate` in `models.py` | Domain in models, I/O at edge. |

## Schema Changes

`migrations/versions/0002_add_transaction_currency.py`:

```sql
ALTER TABLE transactions ADD COLUMN currency TEXT NOT NULL DEFAULT 'COP';
UPDATE transactions SET currency = (
  SELECT p.currency FROM postings p WHERE p.transaction_id = transactions.id
  GROUP BY p.currency ORDER BY COUNT(*) DESC LIMIT 1
);
CREATE INDEX ix_rates_lookup ON rates(base_currency, target_currency, date);
```

## New Module

`src/pyfintracker/fx.py`:

```python
def get_rate(from_ccy: str, to_ccy: str, on: date) -> Decimal: ...
def convert(amount: Decimal, from_ccy: str, to_ccy: str, on: date) -> Decimal: ...
def list_supported_currencies() -> frozenset[str]: ...
```

## Acceptance Criteria

- [ ] `fin convert 50000 COP USD` returns Decimal result with effective rate date.
- [ ] `--date 2024-01-15` uses historical rate, never today's.
- [ ] Cache hit for repeated pair+date returns identical Decimal without network (httpx mock).
- [ ] 404 → `RateNotFound` (exit 4); 422 → `InvalidCurrency` (exit 5).
- [ ] Stale latest cache + Frankfurter down → exit 6 with stderr warning, uses last good.
- [ ] `fin report month --currency USD` converts via txn date; mixed-currency accounts never summed raw (property test).
- [ ] `fin balance --currency EUR` outputs single net-worth Decimal in EUR across 3+ currencies.
- [ ] Migration 0002 upgrades existing DB without data loss; backfill sets `transactions.currency` correctly.
- [ ] `Rate` roundtrips via `to_row` / `from_row`; `Rate` is the only authoritative rate entity.
- [ ] All money paths 100% Decimal; no `float` in FX arithmetic (pre-commit + property test).

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Frankfurter down / rate-limited | Med | 24h latest cache, ∞ historical, clear exit codes. |
| Weekend/holiday date semantics differ v1 vs v2 | Med | Persist and use API's `date`; never the requested date. |
| Mixed-currency net worth sums raw Decimals | Med | Property test: no `+` between different currencies in `reports.py`. |
| Backfill picks wrong currency for future mixed txns | Low | Wave 2A only backfills Wave 1 single-currency data. |
| v2 drops a currency, breaking cache lookups | Low | `list_supported_currencies()` is single source; unknown → error. |

## Rollback Plan

Migration 0002 is additive — `alembic downgrade -1` is clean. `fx.py` is a new module — `git revert` removes it without touching Wave 1. `display_currency` defaults to COP if absent. `fin convert` is a new subcommand; existing commands untouched. `rates` cache entries are inert; clearing forces re-fetch.

## Phased Delivery

- **Wave 2A (this PR chain):** items 1–8. Single currency per account and posting; honest display conversion.
- **Wave 2B (chained follow-up):** cross-currency postings, functional-currency declaration, persisted per-posting rate context, auto `Equity:FXConversion`, mark-to-market. Separate proposal after Wave 2A ships with real mixed-currency usage to design against.
