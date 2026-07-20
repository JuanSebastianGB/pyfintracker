# TUI prototype — Wave 3 F3 dashboard variants

`scripts/prototype_tui.py` is a throwaway spike for PR1 of Wave 3 (F3 TUI). It loads a single Textual app with **three structurally different dashboard variants** you can flip between with `1` / `2` / `3`. Run it with `uv run python scripts/prototype_tui.py` from the repo root — no DB, no real data, no `src/` imports; all money is hardcoded `Decimal` mock data (5 accounts, 10 recent txns, current-month summary). Variant A is the design default — a master/detail split (sidebar: accounts + recent txns; right pane: monthly summary card + selected txn). Variant B is the “single scrollable dashboard” — everything visible top to bottom (net-worth bar → monthly card → accounts → txns), one glance = full picture. Variant C is the modal/vim-style one — one focused view at a time, `gd`/`ga`/`gt`/`gs` switch between Dashboard / Accounts / Transactions / Search modes. Variant C mode-switch keys require the `g` prefix to be pressed, then the second key within ~1s. (Textual 8.x dropped native multi-key sequence support; the prototype implements the prefix manually.) **The feedback you’re being asked for:** which layout do you actually want — and what would you mix? Specifically: do you want the sidebar from A with the widget-grid-glance of B? Do you want C's mode-switching model for power users, but with the rich monthly card from B? Does B need a drill-down path at all (it currently has none — `Enter` is unwired)?

## Keys (also shown in the footer)

- `1` / `2` / `3` — switch variants (A / B / C)
- `q` — quit
- Variant A only: `Tab` cycles panel focus (left sidebar ↔ right detail)
- Variant C only: `gd` Dashboard · `ga` Accounts · `gt` Transactions · `gs` Search

## Things deliberately skipped

- No DB, no repo imports, no persistence — `Decimal` mock data only.
- No tests — it’s a prototype, polish lands in PR1 proper.
- No styling beyond a few borders/padding rules — the goal is layout comparison, not pixel polish.
- No `Enter`-to-drill, no `Esc`-to-go-back, no `/`-search — those are the questions being answered here, not assumed.
- `textual` is not yet in `pyproject.toml` — it lands in PR1 once we approve the design.

## After you’ve looked

Tell me one of:

1. “Ship A as the default for PR6.”
2. “Ship B as the default for PR6.”
3. “Ship C as the default for PR6.”
4. “Mix X from A with Y from B/C — here’s the screenshot.”