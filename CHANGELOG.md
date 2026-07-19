# Changelog

## 0.1.0 (2026-07-19)


### ⚠ BREAKING CHANGES

* consolidate money into models, split reports tests ([#14](https://github.com/JuanSebastianGB/pyfintracker/issues/14))

### Features

* **A:** FX schema layer — Rate model, migration 0002, display_currency rename ([#7](https://github.com/JuanSebastianGB/pyfintracker/issues/7)) ([707d930](https://github.com/JuanSebastianGB/pyfintracker/commit/707d9304e17a8327f17b31e20154bda5c4391cea))
* **B:** FX client — Frankfurter v2, cache layer, get_rate fallback ([#8](https://github.com/JuanSebastianGB/pyfintracker/issues/8)) ([610943c](https://github.com/JuanSebastianGB/pyfintracker/commit/610943c6ca6fea0a221dae42461e6ef9dce610ce))
* bootstrap pyfintracker with Wave 1 (MVP Estricto) proposal ([144fa8e](https://github.com/JuanSebastianGB/pyfintracker/commit/144fa8e8e0ef52fdd47c161cc0efadf4a197d59c))
* **C+D+E:** FX convert + --currency flag + FX hardening ([#13](https://github.com/JuanSebastianGB/pyfintracker/issues/13)) ([40dc303](https://github.com/JuanSebastianGB/pyfintracker/commit/40dc3034028346cf8a9b4c96168276d4ba5d01c2))
* PR 1 — skeleton, db engine, migrations, config, CLI init/migrate/version/config-show ([119ce59](https://github.com/JuanSebastianGB/pyfintracker/commit/119ce594fb510bd0d39ac7e19b799c276f95e09c))
* PR 2 — account rules, validators, repository, CLI account new/list ([b35fb18](https://github.com/JuanSebastianGB/pyfintracker/commit/b35fb180d9c9d867d7182c181cab587bfe1e6ff8))
* PR 4 — transactions + double-entry (redo) ([#4](https://github.com/JuanSebastianGB/pyfintracker/issues/4)) ([8721180](https://github.com/JuanSebastianGB/pyfintracker/commit/8721180a6222b002f6045a7fa7828905355fe0b2))
* PR 5 — REPL transaction entry (contract e) ([#5](https://github.com/JuanSebastianGB/pyfintracker/issues/5)) ([1f620b5](https://github.com/JuanSebastianGB/pyfintracker/commit/1f620b52a8a526b5651b28335594ab59f030eafe))
* PR 6 — Monthly report and balance report (contract d) ([cc366a3](https://github.com/JuanSebastianGB/pyfintracker/commit/cc366a3952bbda73e9e1c806c5c710547d49ecd0))
* PR 7 — Hardening (acceptance tests, error UX, coverage gates, README) ([12a6f37](https://github.com/JuanSebastianGB/pyfintracker/commit/12a6f376e654a7f3ab0b223dff4f8f62ce0e3ba7))
* REPL unbalanced prompt guidance (T-5.12) ([5c643b8](https://github.com/JuanSebastianGB/pyfintracker/commit/5c643b89afd640e1c37ae40b06fd187d2c9a126e))
* **reports:** add MonthlyReport/BalanceReport models and compute functions ([04443cb](https://github.com/JuanSebastianGB/pyfintracker/commit/04443cb8d055b9289b3811d517f8b1552eddfe14))
* **reports:** add render functions for month/balance and CLI report commands ([724b762](https://github.com/JuanSebastianGB/pyfintracker/commit/724b7625942a3b229355d6b473cfb78b5ac10bf9))


### Code Refactoring

* consolidate money into models, split reports tests ([#14](https://github.com/JuanSebastianGB/pyfintracker/issues/14)) ([1ccc089](https://github.com/JuanSebastianGB/pyfintracker/commit/1ccc0892016016937fa5ab3e9a8f0ee412481c57))
