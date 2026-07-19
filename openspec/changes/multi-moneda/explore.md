---
type: explore
id: multi-moneda-explore
status: draft
tags: [wave-2, multi-currency, frankfurter, fx, sqlite, cli]
parent_proposal: null
parent_spec: null
parent_design: null
parent_tasks: null
---

# Exploration: Multi-moneda (Wave 2)

**Date:** 2026-07-18  
**Scope:** Frankfurter integration, conversion, report display currency, multi-currency accounts, local rate cache, `fin convert`, and cross-currency postings.

## Current state

Wave 1 is a lazy-clean Python CLI: domain dataclasses in `src/pyfintracker/models.py`, validation in `validation.py`, SQLAlchemy Core persistence in `repository.py`, direct SQL report computation in `reports.py`, Typer presentation in `cli.py`, and XDG/TOML/env configuration in `config.py`. `httpx>=0.28.1` is already declared in `pyproject.toml`; no HTTP integration exists yet.

### Money and currency behavior

- `Account.currency` is already persisted per account. The schema and `validate_currency` currently allow only `COP`, `USD`, `EUR`, `GBP`, and `JPY`.
- `Posting` already has its own `currency` field. `validate_posting` checks posting currency against account currency, but `create_transaction_with_postings` does not currently load accounts or call `validate_posting`; the repository therefore does not enforce that invariant at the write boundary.
- `validate_transaction` requires at least two postings, rejects zero postings, rejects more than one posting currency, and requires the raw `Decimal` sum to equal zero.
- Precision is hard-coded: COP/JPY use 0 decimals; USD/EUR/GBP use 2 decimals; rounding is `ROUND_HALF_UP`. There is no ISO minor-unit table or dynamic precision source.
- `Money` wraps the same five-currency allowlist and precision rules.

### Current schema and model inconsistencies

- `accounts.currency` has a SQLite `CHECK` for the five Wave 1 currencies.
- `postings.currency` is persisted as `TEXT`, but has no currency `CHECK` constraint.
- `transactions` currently contains only `id`, `date`, `description`, and `created_at`; it has no `currency` column.
- `Transaction.currency` exists in the Python dataclass and `to_row`, but `repository.create_transaction_with_postings` inserts only `date` and `description`. The field is therefore not persisted and is not a reliable transaction-level currency today.
- Migration `0001_initial_schema.py` already creates a `rates` table with `(base_currency, target_currency, rate, date, source)` and a uniqueness constraint on `(base_currency, target_currency, date)`. There is no `Rate` dataclass in the current `models.py`, despite the archived Wave 1 design describing one, and no rate repository/client uses the table.

### Reports, configuration, and CLI

- `compute_monthly_report(conn, year_month)` joins postings, transactions, and accounts, then aggregates native posting amounts. It does not expose or convert a target currency; `MonthlyReport` does not carry a currency field.
- `compute_balance(conn)` sums posting amounts per account directly. If accounts with different currencies are introduced, those raw `Decimal` values cannot be summed into a meaningful net worth.
- `report month` accepts only `--month`; `report balance` accepts only an optional account-name argument. Neither accepts `--currency`.
- `Settings.default_currency` already exists and defaults to `COP`, with defaults < TOML < `FIN_*` env < CLI override precedence. The report commands do not currently consume it.
- There is no `fin convert` command.
- REPL transactions prompt for one currency and apply it to every posting. Flag mode does the same. Cross-currency input has no representation.

## Frankfurter API summary

### Version and host decision

The requested `/latest` and `/YYYY-MM-DD` shape is the **legacy v1 API**. Current documentation uses `https://api.frankfurter.dev/v1/...`; the historical `https://api.frankfurter.app/...` hostname redirects to that host. The current v2 API is `https://api.frankfurter.dev/v2/...` and is the relevant choice for COP.

| Need | v1 | v2 |
|---|---|---|
| Latest rates | `GET /v1/latest?base=USD&symbols=EUR,GBP` | `GET /v2/rates?base=USD&quotes=EUR,GBP` |
| Historical rates | `GET /v1/YYYY-MM-DD?base=USD&symbols=EUR` | `GET /v2/rates?date=YYYY-MM-DD&base=USD&quotes=EUR` |
| Pair lookup | Fetch latest/historical rates and select `rates[quote]` | `GET /v2/rate/USD/EUR` (latest) |
| Currency list | `GET /v1/currencies` | `GET /v2/currencies` |
| Conversion endpoint | None; multiply in the client | None; multiply in the client |
| Coverage | 31 current symbols in the live v1 endpoint | Documentation says 201 currencies from 84 sources |
| COP | **Not supported** | **Supported**; live `USD/COP` query succeeded |

The v1 docs explicitly say the API returns the latest working day and historical data, and show the `/latest`, `/YYYY-MM-DD`, time-series, currencies, and client-side conversion patterns. The v2 docs use a row-oriented response and explicitly state that there is no conversion endpoint.

### v1 supported currencies (~30)

The live `GET https://api.frankfurter.dev/v1/currencies` response currently contains these 31 symbols:

`AUD`, `BRL`, `CAD`, `CHF`, `CNY`, `CZK`, `DKK`, `EUR`, `GBP`, `HKD`, `HUF`, `IDR`, `ILS`, `INR`, `ISK`, `JPY`, `KRW`, `MXN`, `MYR`, `NOK`, `NZD`, `PHP`, `PLN`, `RON`, `SEK`, `SGD`, `THB`, `TRY`, `USD`, `ZAR`.

COP is absent from this list. The v1 request `GET /v1/latest?base=USD&symbols=COP` returned `404 {"message":"not found"}` during live verification.

### v2 COP verification

The live v2 endpoint returned a COP rate:

- `GET https://api.frankfurter.dev/v2/rate/USD/COP`
- Observed response: `{"date":"2026-07-18","base":"USD","quote":"COP","rate":3255.56}`

The v2 currencies endpoint also returned `COP` with name `Colombian Peso`, confirming that v2 is required if COP must be a first-class Frankfurter currency.

### Authentication, cost, and limits

- No API key is required.
- The v2 FAQ says the service is free, including commercial use subject to provider terms.
- The FAQ says there are **no monthly or daily quotas**, but requests **are rate-limited to prevent abuse**. Therefore “no rate limits” is not accurate; caching is still required for a CLI that may be queried repeatedly.
- Rates are sourced from official providers; v2 defaults to blended provider data and supports provider filtering. For a personal finance display, the default blended source is probably adequate, but the source must be recorded if reproducibility matters.

### Response formats

v1 latest/historical response:

```json
{
  "amount": 1.0,
  "base": "USD",
  "date": "2026-07-17",
  "rates": {
    "EUR": 0.87451,
    "GBP": 0.74419
  }
}
```

v2 pair response:

```json
{
  "date": "2026-07-18",
  "base": "USD",
  "quote": "COP",
  "rate": 3255.56
}
```

v2 multi-rate response is an array of rows, one row per date/base/quote pair:

```json
[
  {"date": "2024-01-02", "base": "USD", "quote": "COP", "rate": 3879.5},
  {"date": "2024-01-02", "base": "USD", "quote": "EUR", "rate": 0.9073}
]
```

The API supplies JSON numbers. The client must parse them from their string representation into `Decimal`; no `float` may enter bookkeeping arithmetic.

### Error and calendar behavior

Verified behavior differs between v1 and v2, so the adapter must normalize it:

| Case | v1 observed behavior | v2 observed behavior |
|---|---|---|
| Unknown currency | `404 {"message":"not found"}` | `422 {"status":422,"message":"invalid currency: ABC"}` for pair lookup |
| Malformed date | `422 {"message":"invalid date"}` | `422` |
| Future date with no data | `404 {"message":"not found"}` | `200 []` for a rates query |
| Weekend 2024-01-06 | Returns effective date `2024-01-05` | Returned a row dated `2024-01-06` in the live test |
| Holiday 2024-01-01 | Returns effective date `2023-12-29` | Returned a row dated `2024-01-01` in the live test |
| `api.frankfurter.app` | Redirects (`301`) to `api.frankfurter.dev/v1` | N/A |

The v1 documentation promises the latest working day and historical rates; the v2 provider-blended dataset can expose rows on dates where v1 would roll back. The implementation must use and persist the API’s returned/effective date rather than assuming it equals the requested date. A future date must be rejected as “no rate available”, not interpreted as a zero rate.

**Documentation sources:**

- [Frankfurter v1 API documentation](https://frankfurter.dev/v1/)
- [Frankfurter v2 API documentation](https://frankfurter.dev/docs/)
- [v1 currencies endpoint](https://api.frankfurter.dev/v1/currencies)
- [v2 currencies endpoint](https://api.frankfurter.dev/v2/currencies)
- [Frankfurter providers](https://frankfurter.dev/providers/)

Live endpoint checks were performed on 2026-07-18 against the URLs above.

## Gap analysis

| Area | Current behavior | Required change / implication |
|---|---|---|
| FX client | No client; `httpx` is unused | Add a small v2 adapter with timeout, status mapping, `Decimal` parsing, and returned-date handling. Do not add an SDK dependency. |
| Conversion | No `convert` function | Add a pure `convert(amount, from_currency, to_currency, rate)` or `convert(..., date)` boundary that obtains a rate outside the pure arithmetic. Quantize only in the target currency using `ROUND_HALF_UP`. Same-currency conversion must avoid HTTP. |
| Rate cache | `rates` table exists but is unused; no `Rate` model/repository | Reuse the table as a persistent local cache. Add model/repository functions and likely an index/`fetched_at` metadata migration. In-memory-only caching is ineffective across CLI processes and cannot provide an audit trail. |
| Currency allowlist | Five hard-coded currencies in Python and a five-currency SQLite account `CHECK` | Choose an explicit Wave 2 allowlist and explicit minor units. Do not blindly accept all 201 v2 symbols: the API list includes non-standard/legacy/metal-like symbols and does not provide the accounting precision contract needed by `Money`. |
| Accounts | Each account already has one currency | Keep this rule. Remove the five-currency schema restriction in a migration only for the chosen allowlist. Different account currencies are structurally supported once validation and reports stop assuming one currency. |
| Posting/account coherence | `validate_posting` exists, but repository write does not load accounts or call it | Enforce `posting.currency == account.currency` before insert for every posting. This is a trust-boundary invariant and must not depend on CLI callers. |
| Transaction currency | Python `Transaction.currency` exists but is absent from the DB and ignored by the insert | Do not use this field as the semantic currency for a multi-currency transaction. A transaction cannot have one native currency when postings differ. Either remove/rename it, or replace its meaning with an explicitly defined functional/valuation currency in a later cross-currency design. |
| Transaction validation | All posting currencies must match and raw sum must be zero | Native single-currency transactions can retain the current invariant. Cross-currency transactions need a declared balancing/functional currency, an effective rate per posting, target-currency quantization, and exact converted-sum validation. Reject residuals; do not silently tolerate a cent/peso mismatch. |
| Cross-currency posting | REPL and flag mode prompt for one currency and stamp it on every posting | The highest-risk area. Every posting should still be in its account’s native currency. A cross-currency transaction needs persisted rate/conversion context so later reports do not recalculate a different historical result. |
| Reports | `compute_monthly_report` and `compute_balance` aggregate raw posting amounts; report models lack currency | Add a target currency argument and currency to report models. Convert each posting using the transaction date (or the chosen explicit valuation date) before aggregation. Never sum native COP and USD `Decimal`s directly. |
| Historical reporting | No date-aware rate lookup | For a transaction dated `D`, use the rate effective for `D` and retain the API effective date. Define separately whether balance reports use transaction-date rates or an as-of valuation rate. |
| Default display currency | `Settings.default_currency` exists and defaults to COP, but reports ignore it | Use `FIN_DEFAULT_CURRENCY`/TOML as the report default; `--currency` must override it. Validate the setting at the boundary rather than trusting arbitrary config text. |
| CLI conversion | No command | Add `fin convert AMOUNT FROM TO`, with an optional `--date` for historical conversion. Use latest rate when no date is supplied. Output both source and target currency and the effective rate date. |
| CLI report flags | `report month` has only `--month`; `report balance` has only account filter | Add `--currency` to both commands. Keep account filtering behavior, but filter after conversion or clearly document the chosen semantics. |
| Failure handling | No network/cache behavior | Historical exact cached rate: use it without network. Missing historical rate: fetch, then cache. Latest/stale rate: either use cache within a defined TTL or fail clearly; do not silently use stale data unless an explicit policy/flag allows it. |
| Tests | Existing unit/integration/property/snapshot pyramid is strong | Add mocked `httpx` adapter tests, cache hit/miss/failure tests, Decimal conversion properties, historical/weekend tests, mixed-currency report integration tests, CLI `convert` tests, and migration/backward-compatibility tests. |

## Open questions for user decision

1. **Frankfurter version:** Accept v2 as the source of truth so COP works, even though the requested examples use v1-style endpoints? Recommendation: yes. Keep the v1 endpoint shape only as compatibility knowledge, not as the implementation contract.
2. **Persistent rate semantics:** Should the existing `rates` table be the durable cache and audit record? Recommendation: yes. Historical rows should not expire; latest rows should have a TTL (suggested 24 hours).
3. **Report valuation:** For a transaction on date `D`, should reports always convert at the rate effective on `D`, or should `balance --currency` mark foreign balances to the report’s `as_of` date? Recommendation for Wave 2: transaction-date conversion for deterministic historical reports; defer mark-to-market/revaluation.
4. **Cross-currency transaction currency:** What is the authoritative balancing currency? Options are (a) explicit transaction `functional_currency`, (b) account/config default currency, or (c) a per-transaction conversion table. Recommendation: make it explicit if cross-currency postings are kept; do not overload the currently non-persisted `Transaction.currency` silently.
5. **FX conversion posting:** Should the system create a synthetic `Equity:FXConversion` posting automatically? Recommendation: no automatic hidden posting in the first implementation. Require an explicit configured account/posting when a real conversion difference exists; otherwise an auto-generated posting can mask incorrect input and make audit trails unclear.
6. **Network failure:** If Frankfurter is unavailable, may a stale cached rate be used? Recommendation: exact historical cache is safe; stale latest cache should fail by default and require an explicit opt-in if later desired.
7. **Supported currencies and precision:** Should Wave 2 support only a curated set or all currencies returned by v2? Recommendation: curated currencies with explicit ISO minor units first. A dynamic all-201-currency mode requires a separate precision/unsupported-instrument policy.
8. **Provider selection:** Use the default blended v2 rate or pin ECB/another provider? Recommendation: default blended for personal reporting, but persist `source`/provider metadata so the policy can evolve.
9. **Rate direction and triangulation:** Is every requested pair guaranteed to be directly available, or may the adapter triangulate through EUR/USD? Recommendation: request direct pairs first; make any fallback explicit and testable rather than silently composing rates.
10. **Real transaction date input:** Wave 1 flag mode currently uses `date.today()` while REPL asks for a date. Do cross-currency flag transactions need `--date` now? Recommendation: yes if historical conversion is in scope; otherwise the `convert` command can expose `--date` first and posting history remains limited.

## Recommended scope for Wave 2

### Include in the first Wave 2 delivery

1. **Frankfurter v2 adapter** using `httpx`, with bounded timeout, normalized errors, `Decimal` parsing, effective-date handling, and no new dependency.
2. **Persistent rate cache** backed by the existing `rates` table. Add repository read/write functions, uniqueness/index coverage, and a TTL policy for latest rates. Cache historical responses by effective date.
3. **Pure Decimal conversion** with explicit source/target currencies, target precision, `ROUND_HALF_UP`, same-currency fast path, and properties for no float contamination.
4. **Curated multi-currency account support** including at least COP, USD, EUR, GBP, and JPY plus any additional currencies explicitly assigned minor-unit rules. Migrate the account currency constraint and validate at both CLI and repository boundaries.
5. **`fin convert`** for latest and historical pair conversion, showing the effective rate date and a clear network/cache error.
6. **Report display conversion**: `fin report month --currency X` and `fin report balance --currency X`, defaulting to configured COP. Convert using transaction-date rates; preserve native account currency in source data and report labels where useful.
7. **Mixed-currency account/report tests** proving that reports never add raw amounts from different currencies and that cache/network behavior is deterministic under mocked HTTP.

This is already an **L-sized** Wave 2. The original one-week estimate is optimistic once historical rates, cache semantics, migrations, and report determinism are included.

### Defer from the first Wave 2 slice

- Arbitrary multi-currency postings inside one transaction.
- Automatic synthetic `Equity:FXConversion` postings.
- Mark-to-market balance revaluation, unrealized FX gains/losses, and period-end revaluation entries.
- All 201 v2 symbols with dynamically inferred precision.
- Provider selection UI, bulk time-series synchronization, and offline/stale-rate override flags.

### If cross-currency postings are non-negotiable for Wave 2

Treat them as a separate **Wave 2.1 / chained L slice**, not as a small extension to single-currency validation. The minimum safe contract is:

- Each posting amount is in the currency of its account.
- The transaction declares an explicit functional/balancing currency.
- The exact rate/effective date used for every cross-currency posting is persisted with the transaction or conversion record.
- Validation converts each posting to the functional currency with target-currency quantization and requires the total to equal zero exactly.
- A non-zero rounding or real-world exchange difference is rejected unless the user supplies an explicit FX gain/loss/conversion posting.
- Reports use persisted transaction conversion context for ledger meaning and a separately defined rate policy for display conversion.

## Risks

| Risk | Severity | Why it matters | Mitigation |
|---|---|---|---|
| v1 does not support COP | High | The Wave 1 default currency cannot use the requested legacy API for COP conversion | Implement v2; test COP at startup/client boundary; document host/version. |
| “No rate limits” misconception | Medium | No quotas does not mean unlimited request frequency | Persistent cache, request timeout, and normalized rate-limit/network errors. |
| Weekend/holiday ambiguity | High | v1 rolls back to a working day while v2 may return a row for the requested date | Persist the API returned date and test both versions’ semantics; use v2 consistently. |
| Historical rate drift | High | Re-fetching a rate during a later report could change a previously balanced display | Persist fetched rates and applied transaction rates; make the report valuation policy explicit. |
| Currency precision | High | COP/JPY rounding differs from USD/EUR; v2 coverage is broader than current precision metadata | Curated allowlist with explicit minor-unit map; reject unsupported currencies. |
| Mixed-currency net worth | High | Current `compute_balance` sums native decimals directly | Convert before aggregation and add mixed-currency integration tests. |
| Cross-currency invariant | Critical | A raw sum of zero is not meaningful across currencies; rounding can create residuals | Explicit functional currency, persisted rate context, exact post-conversion invariant, no silent tolerance. |
| Hidden FX posting | High | Auto-created balancing postings can conceal user errors and make audit trails opaque | Require explicit FX account/posting or defer the feature. |
| Existing model/schema drift | Medium | `Transaction.currency` is not persisted and `Rate` is missing despite design text | Resolve fields in the Wave 2 design before writing migrations; add compatibility tests. |
| API failure in local-first CLI | Medium | Reports may need network access for every historical currency | Persistent cache, clear failure messages, and deterministic offline behavior. |
| Migration compatibility | Medium | Existing databases are at revision 0001 and contain only five-currency account checks | Add a forward migration; never rewrite 0001; test upgrade/downgrade and existing rows. |

## Estimated complexity

| Feature | Estimate | Notes |
|---|---:|---|
| Frankfurter v2 HTTP adapter and error normalization | M | Small API surface, but version-specific status/date behavior needs tests. |
| Persistent rate cache over existing `rates` table | M | Repository, TTL/effective-date policy, migration/index changes. |
| Pure Decimal conversion and precision metadata | M | Arithmetic is small; currency policy is the hard part. |
| Curated multi-currency account validation/migration | M | Python allowlist, SQLite constraint, account/posting boundary checks. |
| `fin convert` | S | Straightforward after the adapter/cache contract exists. |
| Monthly report `--currency` | L | Per-transaction dates, rate lookup, mixed-currency aggregation, snapshots. |
| Balance `--currency` | L | Net worth cannot be calculated by raw SQL once account currencies differ. |
| Cross-currency postings in one transaction | L (separate slice) | Requires a new accounting invariant and persisted conversion context; not safe as a patch to the current validator. |
| Wave 2 core without cross-currency postings | L | Recommended first delivery. |
| Wave 2 including cross-currency postings | Beyond one safe slice | Split into chained delivery with a separately approved accounting design. |

## Recommendation

Proceed with a v2-based Wave 2 focused on cached historical conversion, explicit precision, mixed-currency report display, and `fin convert`. Keep each account and posting in one native currency, and use transaction dates for display conversion. Defer arbitrary multi-currency transactions and automatic FX conversion postings until the functional-currency and persisted-rate model is explicitly approved; this is the only part likely to violate the core double-entry invariant if rushed.

**Ready for Proposal:** Yes, after the user answers the version, valuation-date, stale-cache, precision-allowlist, and cross-currency transaction questions. The proposal should split the recommended core from the deferred/high-risk FX-posting slice.
